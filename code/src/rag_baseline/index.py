"""Build an index from an explicit corpus profile.

For v3.4, pass --profile duas-regulacoes-v4. Without --profile, this entry point
uses the historical corpus/collection fields of BaselineSettings.
"""

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from rag_baseline.config import BaselineSettings, CorpusSource
from rag_baseline.corpus import CorpusError, build_embedding_text, load_corpus
from rag_baseline.openrouter import OpenRouterClient, OpenRouterError
from rag_baseline.profiles import ProfileError, apply_profile, profile_names
from rag_baseline.vector_store import ChromaVectorStore


class IndexingError(RuntimeError):
    pass


@dataclass(frozen=True)
class IndexSummary:
    loaded_chunks: int
    indexed_chunks: int
    collection: str
    embedding_model: str
    persist_dir: Path
    elapsed_seconds: float


async def index_corpus(
    settings: BaselineSettings,
    *,
    openrouter,
    vector_store,
    rebuild: bool,
) -> IndexSummary:
    started_at = time.perf_counter()
    sources = settings.CORPUS_SOURCES or (
        CorpusSource(
            path=settings.CORPUS_PATH,
            id_prefix=settings.CORPUS_ID_PREFIX,
            norm_name=settings.CORPUS_NAME,
        ),
    )
    chunks, embedding_texts = [], []
    for source in sources:
        current = load_corpus(source.path, id_prefix=source.id_prefix)
        chunks.extend(current)
        embedding_texts.extend(
            build_embedding_text(chunk, norm_name=source.norm_name) for chunk in current
        )
    if len({chunk.id for chunk in chunks}) != len(chunks):
        raise IndexingError("IDs repetidos entre corpora; use um prefixo distinto por norma.")
    embeddings = await openrouter.embed(embedding_texts)

    if rebuild:
        vector_store.reset()
    vector_store.synchronize(chunks, embeddings)
    indexed_chunks = vector_store.count()
    if indexed_chunks != len(chunks):
        raise IndexingError(
            "A contagem da coleção não corresponde ao corpus: "
            f"carregados={len(chunks)}, indexados={indexed_chunks}."
        )

    return IndexSummary(
        loaded_chunks=len(chunks),
        indexed_chunks=indexed_chunks,
        collection=settings.CHROMA_COLLECTION,
        embedding_model=settings.EMBEDDING_MODEL,
        persist_dir=settings.CHROMA_PERSIST_DIR,
        elapsed_seconds=time.perf_counter() - started_at,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Indexa os corpora do perfil em uma coleção própria."
    )
    parser.add_argument(
        "--profile",
        choices=profile_names(),
        help="Seleciona corpus, prefixo de IDs e coleção predefinidos.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Recria somente a coleção configurada para esta baseline.",
    )
    return parser


async def _run(settings: BaselineSettings, rebuild: bool) -> IndexSummary:
    openrouter = OpenRouterClient(
        api_key=settings.api_key_value(),
        base_url=settings.OPENROUTER_BASE_URL,
        embedding_model=settings.EMBEDDING_MODEL,
        embedding_batch_size=settings.EMBEDDING_BATCH_SIZE,
        llm_model=settings.LLM_MODEL,
        llm_temperature=settings.LLM_TEMPERATURE,
        llm_max_tokens=settings.LLM_MAX_TOKENS,
        timeout_seconds=settings.OPENROUTER_TIMEOUT_SECONDS,
        app_name=settings.OPENROUTER_APP_NAME,
        http_referer=settings.OPENROUTER_HTTP_REFERER,
    )
    vector_store = ChromaVectorStore(
        settings.CHROMA_PERSIST_DIR,
        settings.CHROMA_COLLECTION,
    )
    return await index_corpus(
        settings,
        openrouter=openrouter,
        vector_store=vector_store,
        rebuild=rebuild,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = BaselineSettings()
    if args.profile:
        settings = apply_profile(settings, args.profile)
    if not settings.OPENROUTER_API_KEY:
        print("OPENROUTER_API_KEY não está configurada.", file=sys.stderr)
        return 1

    try:
        summary = asyncio.run(_run(settings, args.rebuild))
    except (CorpusError, IndexingError, OpenRouterError, ProfileError, ValueError) as exc:
        print(f"Falha na indexação: {exc}", file=sys.stderr)
        return 1

    print(f"Chunks lidos: {summary.loaded_chunks}")
    print(f"Chunks indexados: {summary.indexed_chunks}")
    print(f"Coleção: {summary.collection}")
    print(f"Modelo de embedding: {summary.embedding_model}")
    print(f"Persistência: {summary.persist_dir}")
    print(f"Tempo total: {summary.elapsed_seconds:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
