import argparse
import asyncio
import json
import sys
from typing import Any

from rag_baseline.config import BaselineSettings
from rag_baseline.openrouter import OpenRouterClient, OpenRouterError
from rag_baseline.profiles import ProfileError, apply_profile, profile_names
from rag_baseline.vector_store import ChromaVectorStore


class RetrievalError(RuntimeError):
    pass


async def retrieve_chunks(
    question: str,
    *,
    openrouter: Any,
    vector_store: Any,
    top_k: int,
) -> list[Any]:
    question = question.strip()
    if not question:
        raise RetrievalError("A pergunta não pode estar vazia.")
    if top_k < 1:
        raise RetrievalError("top_k deve ser maior que zero.")
    if vector_store.count() == 0:
        raise RetrievalError("Corpus não indexado na coleção selecionada.")

    embedding = (await openrouter.embed([question]))[0]
    return vector_store.query(embedding, top_k=top_k)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recupera trechos do corpus sem gerar resposta com LLM."
    )
    parser.add_argument("question", help="Pergunta usada na busca semântica.")
    parser.add_argument(
        "--profile",
        choices=profile_names(),
        help="Seleciona a coleção predefinida a consultar.",
    )
    parser.add_argument("--top-k", type=int, help="Quantidade de trechos retornados.")
    return parser


async def _run(settings: BaselineSettings, question: str, top_k: int) -> list[Any]:
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
    return await retrieve_chunks(
        question,
        openrouter=openrouter,
        vector_store=vector_store,
        top_k=top_k,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = BaselineSettings()
    if args.profile:
        settings = apply_profile(settings, args.profile)
    if not settings.OPENROUTER_API_KEY:
        print("OPENROUTER_API_KEY não está configurada.", file=sys.stderr)
        return 1

    top_k = args.top_k if args.top_k is not None else settings.RETRIEVAL_TOP_K

    try:
        chunks = asyncio.run(_run(settings, args.question, top_k))
    except (OpenRouterError, ProfileError, RetrievalError, ValueError) as exc:
        print(f"Falha na recuperação: {exc}", file=sys.stderr)
        return 1

    payload = [chunk.model_dump() for chunk in chunks]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
