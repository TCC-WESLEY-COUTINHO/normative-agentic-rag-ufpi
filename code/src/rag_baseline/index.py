import argparse
import asyncio
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from rag_baseline.config import BaselineSettings
from rag_baseline.corpus import CorpusError, build_embedding_text, load_corpus
from rag_baseline.openrouter import OpenRouterClient, OpenRouterError
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
    chunks = load_corpus(settings.CORPUS_PATH)
    embedding_texts = [build_embedding_text(chunk) for chunk in chunks]
    embeddings = await openrouter.embed(embedding_texts)

    if rebuild:
        vector_store.reset()
    vector_store.upsert(chunks, embeddings)
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
    parser = argparse.ArgumentParser(description="Indexa a baseline da Resolução nº 177/2012.")
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
    if not settings.OPENROUTER_API_KEY:
        print("OPENROUTER_API_KEY não está configurada.", file=sys.stderr)
        return 1

    try:
        summary = asyncio.run(_run(settings, args.rebuild))
    except (CorpusError, IndexingError, OpenRouterError, ValueError) as exc:
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
