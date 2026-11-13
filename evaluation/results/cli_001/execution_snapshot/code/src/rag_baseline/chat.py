"""Terminal interface to the same RAG service used by the API."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from rag_baseline.config import BaselineSettings
from rag_baseline.dataset import load_questions
from rag_baseline.openrouter import OpenRouterClient, OpenRouterError
from rag_baseline.profiles import apply_profile, profile_names
from rag_baseline.service import CorpusNotIndexedError, RagService
from rag_baseline.vector_store import ChromaVectorStore


def create_service(settings: BaselineSettings) -> RagService:
    if not settings.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY não está configurada.")
    client = OpenRouterClient(
        api_key=settings.api_key_value(),
        base_url=settings.OPENROUTER_BASE_URL,
        embedding_model=settings.EMBEDDING_MODEL,
        llm_model=settings.LLM_MODEL,
        embedding_batch_size=settings.EMBEDDING_BATCH_SIZE,
        llm_temperature=settings.LLM_TEMPERATURE,
        llm_max_tokens=settings.LLM_MAX_TOKENS,
        timeout_seconds=settings.OPENROUTER_TIMEOUT_SECONDS,
        app_name=settings.OPENROUTER_APP_NAME,
        http_referer=settings.OPENROUTER_HTTP_REFERER,
    )
    return RagService(
        openrouter=client,
        vector_store=ChromaVectorStore(settings.CHROMA_PERSIST_DIR, settings.CHROMA_COLLECTION),
        top_k=settings.RETRIEVAL_TOP_K,
        embedding_model=settings.EMBEDDING_MODEL,
        llm_model=settings.LLM_MODEL,
    )


def _parser():
    parser = argparse.ArgumentParser(description="Consulta os regulamentos da UFPI pelo terminal.")
    parser.add_argument("question", nargs="?", help="Omitir para abrir o chat interativo.")
    parser.add_argument("--profile", choices=profile_names(), default="duas-regulacoes")
    parser.add_argument("--setor", choices=("graduacao", "pos_graduacao"))
    parser.add_argument(
        "--questions-file", type=Path, help="Lista numerada; envia somente as perguntas."
    )
    parser.add_argument(
        "--json", action="store_true", help="Saída JSON por pergunta, com referências."
    )
    parser.add_argument(
        "--output", type=Path, help="Salva JSONL em arquivo novo, sem sobrescrever."
    )
    return parser


async def _run(args, settings, output):
    service = create_service(settings)
    questions = (
        load_questions(args.questions_file)
        if args.questions_file
        else ([args.question] if args.question is not None else None)
    )
    errors = 0

    async def answer(question):
        nonlocal errors
        try:
            result = await service.query(question, sector=args.setor)
            payload = {
                "question": question,
                "collection": settings.CHROMA_COLLECTION,
                **result.model_dump(),
                "error": None,
            }
        except (OpenRouterError, CorpusNotIndexedError, ValueError) as exc:
            errors += 1
            payload = {
                "question": question,
                "collection": settings.CHROMA_COLLECTION,
                "answer": None,
                "references": [],
                "error": str(exc),
            }
        serialized = json.dumps(payload, ensure_ascii=False)
        if output:
            output.write(serialized + "\n")
            output.flush()
        if args.json:
            print(serialized, flush=True)
        elif payload["error"]:
            print(f"Falha: {payload['error']}", file=sys.stderr, flush=True)
        else:
            print(payload["answer"], flush=True)
            print("\nTrechos recuperados:", flush=True)
            for ref in payload["references"]:
                print(
                    f"- {ref['source']} — art. {ref['article_number']} ({ref.get('sector', 'desconhecido')})",
                    flush=True,
                )

    if questions is not None:
        for question in questions:
            await answer(question)
    else:
        print(
            "UFPI — graduação e pós-graduação. /sair encerra; /setor graduacao|pos_graduacao|limpar define seu contexto.",
            flush=True,
        )
        while True:
            try:
                question = input("Você: ").strip()
            except EOFError:
                break
            if question.casefold() in ("/sair", "sair", "exit", "quit"):
                break
            if question.startswith("/setor "):
                value = question.split(maxsplit=1)[1]
                if value in ("graduacao", "pos_graduacao", "limpar"):
                    args.setor = None if value == "limpar" else value
                    print(f"Setor informado: {args.setor or 'desconhecido'}", flush=True)
                else:
                    print(
                        "Use /setor graduacao, /setor pos_graduacao ou /setor limpar.", flush=True
                    )
                continue
            if question:
                await answer(question)
    return 1 if errors else 0


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    if args.question is not None and args.questions_file:
        parser.error("Use uma pergunta ou --questions-file, não ambos.")
    output = None
    try:
        settings = apply_profile(BaselineSettings(), args.profile)
        if args.output:
            output = args.output.open("x", encoding="utf-8")
        return asyncio.run(_run(args, settings, output))
    except (OSError, ValueError, OpenRouterError) as exc:
        print(f"Falha na CLI: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        if output:
            output.close()


if __name__ == "__main__":
    raise SystemExit(main())
