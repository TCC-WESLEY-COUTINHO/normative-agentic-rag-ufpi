"""Append-only indexing and JSON-safe evidence that existing Chroma rows were preserved."""

import argparse
import asyncio
import hashlib
import json
import math
import struct
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from rag_baseline.config import BaselineSettings, CorpusSource
from rag_baseline.corpus import build_embedding_text, load_corpus
from rag_baseline.index import IndexingError
from rag_baseline.openrouter import OpenRouterError
from rag_baseline.profiles import apply_profile, profile_names
from rag_baseline.vector_store import ChromaVectorStore


@dataclass(frozen=True)
class IncrementalIndexSummary:
    loaded_chunks: int
    added_chunks: int
    skipped_chunks: int
    indexed_chunks: int
    added_ids: list[str]
    unchanged_ids: list[str]
    before_snapshot: dict
    after_snapshot: dict
    collection: str
    embedding_model: str
    persist_dir: Path
    elapsed_seconds: float


def _canonical_json(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _embedding_sha256(embedding) -> str:
    # Chroma stores float32; explicit little-endian encoding makes artifacts portable.
    return hashlib.sha256(struct.pack(f"<{len(embedding)}f", *embedding)).hexdigest()


def snapshot_collection(collection) -> dict:
    """Hash documents, canonical metadata and float32 vectors without exporting their content.

    Metadata remains available as canonical JSON for scientific provenance. Document text
    and vector coordinates are represented only by hashes. No collection is created here.
    """
    rows = collection.get(include=["documents", "metadatas", "embeddings"])
    ids = rows["ids"]
    documents = rows["documents"]
    metadatas = rows["metadatas"]
    embeddings = rows["embeddings"]
    if len(set(ids)) != len(ids):
        raise IndexingError("A coleção retornou IDs repetidos no snapshot.")
    if not ids:
        documents, metadatas, embeddings = [], [], []
    if any(
        column is None or len(column) != len(ids) for column in (documents, metadatas, embeddings)
    ):
        raise IndexingError("O snapshot não contém documentos, metadados e embeddings completos.")

    records = []
    for chunk_id, document, metadata, embedding in zip(
        ids, documents, metadatas, embeddings, strict=True
    ):
        metadata_json = _canonical_json(metadata)
        records.append(
            {
                "id": chunk_id,
                "source": metadata.get("source") if metadata is not None else None,
                "norm_id": metadata.get("norm_id") if metadata is not None else None,
                "document_sha256": _sha256_text(document) if document is not None else None,
                "metadata_json": metadata_json,
                "metadata_sha256": _sha256_text(metadata_json),
                "embedding_float32_sha256": _embedding_sha256(embedding),
                "embedding_dimensions": len(embedding),
            }
        )
    records.sort(key=lambda record: record["id"])
    if collection.count() != len(records):
        raise IndexingError("A contagem da coleção mudou durante o snapshot.")
    return {
        "count": len(records),
        "ids": [record["id"] for record in records],
        "records": records,
        "sha256": _sha256_text(_canonical_json(records)),
    }


async def incremental_index(
    settings: BaselineSettings,
    *,
    openrouter,
    vector_store,
) -> IncrementalIndexSummary:
    """Add only missing IDs from explicit new corpus sources; never synchronize old rows.

    A matching ID is skipped only when its text and metadata match exactly. A collision
    rejects the entire input before embedding or writing. Before/after snapshots prove
    that every prior row, including its stored embedding, remains unchanged.

    Run with exclusive write access to the collection. Snapshot checks detect concurrent
    changes, but Chroma does not expose a transaction spanning external API requests.
    """
    started_at = time.perf_counter()
    if not settings.CORPUS_SOURCES:
        raise IndexingError("Defina CORPUS_SOURCES explicitamente com apenas os novos corpora.")

    chunks, embedding_texts = [], []
    for source in settings.CORPUS_SOURCES:
        current = load_corpus(source.path, id_prefix=source.id_prefix)
        chunks.extend(current)
        embedding_texts.extend(
            build_embedding_text(chunk, norm_name=source.norm_name) for chunk in current
        )
    if len({chunk.id for chunk in chunks}) != len(chunks):
        raise IndexingError("IDs repetidos entre os novos corpora; use prefixos distintos.")

    collection = vector_store.collection
    before = snapshot_collection(collection)
    prior_rows = {row["id"]: row for row in before["records"]}
    missing_chunks, missing_texts, missing_metadata = [], [], []
    for chunk, text in zip(chunks, embedding_texts, strict=True):
        metadata = ChromaVectorStore._metadata(chunk)
        existing = prior_rows.get(chunk.id)
        if existing is None:
            missing_chunks.append(chunk)
            missing_texts.append(text)
            missing_metadata.append(metadata)
        elif existing["document_sha256"] != _sha256_text(chunk.content) or existing[
            "metadata_json"
        ] != _canonical_json(metadata):
            raise IndexingError(f"Há colisão de ID com texto ou metadados diferentes: {chunk.id}")

    if missing_chunks:
        embeddings = await openrouter.embed(missing_texts)
        if len(embeddings) != len(missing_chunks):
            raise IndexingError("Cada novo chunk deve possuir exatamente um embedding.")
        dimensions = {row["embedding_dimensions"] for row in before["records"]}
        try:
            dimensions.update(len(embedding) for embedding in embeddings)
            if len(dimensions) != 1 or 0 in dimensions:
                raise ValueError("dimensões incompatíveis")
            for embedding in embeddings:
                if not all(math.isfinite(value) for value in embedding):
                    raise ValueError("valores não finitos")
                _embedding_sha256(embedding)
        except (TypeError, ValueError, OverflowError, struct.error) as exc:
            raise IndexingError("A resposta contém embeddings inválidos para a coleção.") from exc
        if snapshot_collection(collection) != before:
            raise IndexingError(
                "A coleção mudou durante a geração dos embeddings; adição cancelada."
            )
        collection.add(
            ids=[chunk.id for chunk in missing_chunks],
            documents=[chunk.content for chunk in missing_chunks],
            metadatas=missing_metadata,
            embeddings=embeddings,
        )

    after = snapshot_collection(collection)
    after_rows = {row["id"]: row for row in after["records"]}
    if any(after_rows.get(chunk_id) != row for chunk_id, row in prior_rows.items()):
        raise IndexingError(
            "Registros anteriores foram alterados; confira os snapshots da coleção."
        )
    added_ids = sorted(chunk.id for chunk in missing_chunks)
    if after["count"] != before["count"] + len(added_ids) or set(after_rows) - set(
        prior_rows
    ) != set(added_ids):
        raise IndexingError(
            "A contagem ou os IDs da coleção não correspondem às adições esperadas."
        )

    return IncrementalIndexSummary(
        loaded_chunks=len(chunks),
        added_chunks=len(added_ids),
        skipped_chunks=len(chunks) - len(added_ids),
        indexed_chunks=after["count"],
        added_ids=added_ids,
        unchanged_ids=before["ids"],
        before_snapshot=before,
        after_snapshot=after,
        collection=settings.CHROMA_COLLECTION,
        embedding_model=settings.EMBEDDING_MODEL,
        persist_dir=settings.CHROMA_PERSIST_DIR,
        elapsed_seconds=time.perf_counter() - started_at,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Adiciona somente novos corpora ao índice existente."
    )
    parser.add_argument(
        "--source",
        nargs=3,
        action="append",
        required=True,
        metavar=("CORPUS", "NORM_ID", "NORM_NAME"),
        help="Corpus novo, prefixo de IDs da norma e nome; repita para cada corpus novo.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Novo diretório de evidências.")
    parser.add_argument("--profile", choices=profile_names(), default="duas-regulacoes")
    return parser


def _write_json(path: Path, value) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text)


async def _run_cli(settings: BaselineSettings):
    # Import only when executing: --help and output refusal never initialize the client.
    from rag_baseline.experiment import client_for

    client = client_for(settings)
    store = ChromaVectorStore(settings.CHROMA_PERSIST_DIR, settings.CHROMA_COLLECTION)
    summary = await incremental_index(settings, openrouter=client, vector_store=store)
    return summary, client.receipts


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = args.output
    if output.exists():
        print(f"O diretório de saída já existe: {output}", file=sys.stderr)
        return 1

    try:
        settings = apply_profile(BaselineSettings(), args.profile).model_copy(
            update={
                "CORPUS_SOURCES": tuple(
                    CorpusSource(path=path, id_prefix=norm_id, norm_name=norm_name)
                    for path, norm_id, norm_name in args.source
                )
            }
        )
        if not settings.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY não está configurada.")
        output.mkdir(parents=True, exist_ok=False)
        summary, receipts = asyncio.run(_run_cli(settings))
        _write_json(output / "summary.json", asdict(summary))
        _write_json(output / "receipts.json", receipts)
    except (IndexingError, OpenRouterError, OSError, ValueError) as exc:
        print(f"Falha na indexação incremental: {exc}", file=sys.stderr)
        return 1

    print(f"Chunks adicionados: {summary.added_chunks}")
    print(f"Chunks preservados: {len(summary.unchanged_ids)}")
    print(f"Evidências: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
