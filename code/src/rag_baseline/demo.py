from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Sequence
from typing import TextIO, cast

import httpx
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

DEFAULT_API_URL = "http://127.0.0.1:8080"
START_API_COMMAND = "uv run uvicorn rag_baseline.api:app --host 127.0.0.1 --port 8080"


def _configure_utf8(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    encoding = getattr(stream, "encoding", None)
    if callable(reconfigure) and isinstance(encoding, str) and encoding.lower() != "utf-8":
        reconfigure(encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Demo em terminal do RAG normativo da UFPI.")
    parser.add_argument("--question")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    return parser


def _show_banner(console: Console) -> None:
    console.print(
        Panel.fit(
            "[bold]Assistente Normativo UFPI[/bold]\nResolução 177/2012\nBaseline RAG",
            border_style="cyan",
        )
    )


def _show_api_unavailable(console: Console) -> None:
    console.print(
        Panel(
            f"API não disponível.\n\nInicie a API com:\n[bold]{START_API_COMMAND}[/bold]",
            title="API indisponível",
            border_style="red",
        )
    )


def _show_error(console: Console, message: str) -> None:
    console.print(Panel(message, title="Erro", border_style="red"))


def _response_error(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"A API retornou HTTP {response.status_code}."
    if isinstance(body, dict) and isinstance(body.get("detail"), str):
        return body["detail"]
    return f"A API retornou HTTP {response.status_code}."


def _show_health(console: Console, health: dict[str, object]) -> None:
    console.print("[green]API: conectada[/green]")
    console.print(f"Corpus: {health.get('indexed_chunks', 0)} chunks")

    details = Table(show_header=False, box=None, padding=(0, 1))
    details.add_column(style="dim")
    details.add_column()
    details.add_row("Status", str(health.get("status", "desconhecido")))
    details.add_row("Coleção", str(health.get("collection", "—")))
    details.add_row("Embedding", str(health.get("embedding_model", "—")))
    details.add_row("LLM", str(health.get("llm_model", "—")))
    console.print(details)
    status = str(health.get("status", "desconhecido"))
    if status != "ok":
        console.print(
            Panel(
                f'A API informou o status "{status}".',
                title="Atenção",
                border_style="yellow",
            )
        )


def _location(reference: dict[str, object]) -> str:
    parts: list[str] = []
    for short_label, number_key, title_key in (
        ("Cap.", "chapter_number", "chapter_title"),
        ("Seção", "section_number", "section_title"),
        ("Subseção", "subsection_number", "subsection_title"),
    ):
        value = reference.get(number_key) or reference.get(title_key)
        if value:
            parts.append(f"{short_label} {value}")
    return " · ".join(parts) or "—"


def _show_references(console: Console, references: list[dict[str, object]]) -> None:
    table = Table(title="REFERÊNCIAS RECUPERADAS")
    table.add_column("Rank", justify="right")
    table.add_column("Artigo")
    table.add_column("Localização")
    table.add_column("Distância", justify="right")
    for reference in references:
        distance = reference.get("distance")
        formatted_distance = f"{distance:.4f}" if isinstance(distance, int | float) else "—"
        table.add_row(
            str(reference.get("rank") or "—"),
            str(reference.get("article_number") or "—"),
            _location(reference),
            formatted_distance,
        )
    console.print(table)


def _show_chunks(console: Console, references: list[dict[str, object]]) -> None:
    for position, reference in enumerate(references, start=1):
        details: list[Text] = []
        for label, number_key, title_key in (
            ("Capítulo", "chapter_number", "chapter_title"),
            ("Seção", "section_number", "section_title"),
            ("Subseção", "subsection_number", "subsection_title"),
        ):
            number = reference.get(number_key)
            title = reference.get(title_key)
            if number or title:
                value = " — ".join(str(item) for item in (number, title) if item)
                details.append(Text(f"{label}: {value}", style="dim"))
        if details:
            details.append(Text())
        details.append(Text(str(reference.get("content") or "")))
        article = reference.get("article_number") or "—"
        console.print(
            Panel(Group(*details), title=f"Trecho {position} · Art. {article}", border_style="dim")
        )


def _run_query(console: Console, client: httpx.Client, question: str, *, verbose: bool) -> bool:
    started = time.perf_counter()
    try:
        response = client.post("/query", json={"question": question})
        response.raise_for_status()
    except httpx.RequestError:
        _show_api_unavailable(console)
        return False
    except httpx.HTTPStatusError as exc:
        _show_error(console, _response_error(exc.response))
        return False
    try:
        result = response.json()
    except ValueError:
        _show_error(console, "A API retornou JSON inválido.")
        return False
    if not isinstance(result, dict):
        _show_error(console, "A API retornou JSON inválido.")
        return False
    references = result.get("references")
    if not isinstance(references, list) or not all(
        isinstance(reference, dict) for reference in references
    ):
        _show_error(console, "A API retornou JSON inválido.")
        return False
    typed_references = cast(list[dict[str, object]], references)
    elapsed = time.perf_counter() - started

    console.print(Panel(Markdown(str(result.get("answer", ""))), title="Resposta"))
    _show_references(console, typed_references)
    if verbose:
        _show_chunks(console, typed_references)
    console.print(
        f"[dim]Tempo: {elapsed:.1f} s · LLM: {result.get('llm_model', '—')} · "
        f"Embedding: {result.get('embedding_model', '—')}[/dim]"
    )
    return True


def run(
    argv: Sequence[str] | None = None,
    *,
    client: httpx.Client | None = None,
    console: Console | None = None,
    read_input: Callable[[str], str] = input,
) -> int:
    args = _parser().parse_args(argv)
    output = console or Console()
    owned_client = client is None
    http_client = client or httpx.Client(base_url=args.api_url, timeout=30.0)

    try:
        _show_banner(output)
        try:
            response = http_client.get("/health")
            response.raise_for_status()
        except httpx.RequestError:
            _show_api_unavailable(output)
            return 1
        except httpx.HTTPStatusError as exc:
            _show_error(output, _response_error(exc.response))
            return 1
        try:
            health = response.json()
        except ValueError:
            _show_error(output, "A API retornou JSON inválido.")
            return 1
        if not isinstance(health, dict):
            _show_error(output, "A API retornou JSON inválido.")
            return 1
        _show_health(output, health)

        if args.question is not None:
            if not _run_query(output, http_client, args.question, verbose=args.verbose):
                return 1
        else:
            output.print('\nDigite sua pergunta. Digite "sair" para encerrar.')
            while True:
                question = read_input("\nPergunta:\n> ").strip()
                if question.lower() in {"sair", "exit", "quit"}:
                    return 0
                if not question:
                    continue
                _run_query(output, http_client, question, verbose=args.verbose)
        return 0
    except (EOFError, KeyboardInterrupt):
        output.print("\n[dim]Encerrado.[/dim]")
        return 0
    finally:
        if owned_client:
            http_client.close()


def main() -> None:
    _configure_utf8(sys.stdout)
    _configure_utf8(sys.stderr)
    raise SystemExit(run())


if __name__ == "__main__":
    main()
