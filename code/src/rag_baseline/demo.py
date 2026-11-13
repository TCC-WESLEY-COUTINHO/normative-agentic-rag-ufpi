from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO, cast

import httpx
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from rag_baseline.dataset import load_questions

DEFAULT_API_URL = "http://127.0.0.1:8080"
START_API_COMMAND = "uv run uvicorn rag_baseline.api:app --host 127.0.0.1 --port 8080"


def _configure_utf8(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    encoding = getattr(stream, "encoding", None)
    if callable(reconfigure) and isinstance(encoding, str) and encoding.lower() != "utf-8":
        reconfigure(encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Demo em terminal do RAG normativo da UFPI.")
    questions = parser.add_mutually_exclusive_group()
    questions.add_argument("--question")
    questions.add_argument("--questions-file", type=Path)
    parser.add_argument("--setor", choices=("graduacao", "pos_graduacao", "ambos", "automatico"))
    parser.add_argument(
        "--output", type=Path, help="Salva respostas em JSONL novo; não sobrescreve."
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    return parser


def _show_banner(console: Console) -> None:
    console.print(
        Panel.fit(
            "[bold]Assistente Normativo UFPI[/bold]\nGraduação e Pós-graduação\nBaseline RAG",
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
    table = Table(title="REFERÊNCIAS UTILIZADAS")
    table.add_column("Rank", justify="right")
    table.add_column("Artigo")
    table.add_column("Setor")
    table.add_column("Fonte")
    table.add_column("Localização")
    table.add_column("Distância", justify="right")
    for reference in references:
        distance = reference.get("distance")
        formatted_distance = f"{distance:.4f}" if isinstance(distance, int | float) else "—"
        table.add_row(
            str(reference.get("rank") or "—"),
            str(reference.get("article_number") or "—"),
            str(reference.get("sector") or "desconhecido"),
            str(reference.get("source") or "—"),
            _location(reference),
            formatted_distance,
        )
    console.print(table)


def _show_chunks(console: Console, references: list[dict[str, object]]) -> None:
    for position, reference in enumerate(references, start=1):
        details: list[Text] = [
            Text(f"Setor: {reference.get('sector') or 'desconhecido'}", style="dim"),
            Text(f"Fonte: {reference.get('source') or 'desconhecida'}", style="dim"),
        ]
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


def _choose_scope(console: Console, read_input: Callable[[str], str]) -> str | None:
    console.print(
        "\n[bold]Escopo da recuperação[/bold]: 1 — Graduação · 2 — Pós-graduação · "
        "3 — Ambas · 4 — Automático / Router"
    )
    choices = {"1": "graduacao", "2": "pos_graduacao", "3": "ambos", "4": "automatico"}
    while True:
        value = read_input("Escopo [1/2/3/4; sair encerra]: ").strip().lower()
        if value in {"sair", "exit", "quit"}:
            return None
        if value in choices:
            return choices[value]
        if value in choices.values():
            return value
        console.print("[yellow]Selecione 1, 2, 3 ou 4.[/yellow]")


def _run_query(
    console: Console,
    client: httpx.Client,
    question: str,
    *,
    verbose: bool,
    sector: str,
    output: TextIO | None = None,
    read_clarification: Callable[[str], str] | None = None,
    clarification: str | None = None,
) -> bool:
    started = time.perf_counter()
    record: dict[str, object] = {"question": question, "sector": sector}
    if clarification is not None:
        record["clarification"] = clarification

    def save(result: dict[str, object], error: str | None = None) -> None:
        if output is not None:
            payload = {
                **record,
                **result,
                "error": error if error is not None else result.get("error"),
                "elapsed_seconds": time.perf_counter() - started,
            }
            output.write(json.dumps(payload, ensure_ascii=False) + "\n")
            output.flush()

    try:
        response = client.post("/query", json=record)
        response.raise_for_status()
    except httpx.RequestError:
        _show_api_unavailable(console)
        save({}, "Não foi possível conectar à API.")
        return False
    except httpx.HTTPStatusError as exc:
        message = _response_error(exc.response)
        _show_error(console, message)
        save({}, message)
        return False
    try:
        result = response.json()
    except ValueError:
        _show_error(console, "A API retornou JSON inválido.")
        save({}, "A API retornou JSON inválido.")
        return False
    if not isinstance(result, dict):
        _show_error(console, "A API retornou JSON inválido.")
        save({}, "A API retornou JSON inválido.")
        return False
    references = result.get("references")
    if not isinstance(references, list) or not all(
        isinstance(reference, dict) for reference in references
    ):
        _show_error(console, "A API retornou JSON inválido.")
        save({}, "A API retornou JSON inválido.")
        return False
    typed_references = cast(list[dict[str, object]], references)
    selected = result.get("selected_scope") if sector == "automatico" else sector
    if selected in ("graduacao", "pos_graduacao") and any(
        ref.get("sector") != selected for ref in typed_references
    ):
        message = (
            "A API retornou referência fora do escopo selecionado; confira a versão do servidor."
        )
        _show_error(console, message)
        save(result, message)
        return False
    elapsed = time.perf_counter() - started
    save(result)

    if result.get("error"):
        _show_error(console, "Não foi possível concluir a consulta. Tente novamente.")
        return False

    if sector == "automatico":
        labels = {"graduacao": "Graduação", "pos_graduacao": "Pós-graduação", "ambas": "Ambas"}
        console.print(
            Panel(labels.get(selected, "Preciso de esclarecimento"), title="ROTA AUTOMÁTICA")
        )
        if result.get("needs_clarification") and read_clarification and clarification is None:
            console.print(str(result.get("clarification_question") or result.get("answer", "")))
            reply = read_clarification("Esclarecimento (uma rodada): ").strip()
            return _run_query(
                console,
                client,
                question,
                verbose=verbose,
                sector=sector,
                output=output,
                clarification=reply or "Não informado",
            )

    console.print(Panel(Markdown(str(result.get("answer", ""))), title="Resposta"))
    _show_references(console, typed_references)
    if verbose:
        audit = result.get("version_filter")
        if isinstance(audit, dict):
            console.print(
                Panel(
                    f"Candidatos: {len(audit.get('pre_filter_references', []))}\n"
                    f"Removidos após retrieval: {len(audit.get('removed_references', []))}\n"
                    f"Normas excluídas antes do top 5: {audit.get('prefilter_excluded_norm_ids', [])}\n"
                    f"Contextos faltantes para top 5: {audit.get('shortfall', 0)}",
                    title="VIGÊNCIA",
                )
            )
            for removed in audit.get("removed_references", []):
                console.print(
                    Text(
                        f"Removido: {removed['norm_id']} · {removed['reason']}\n"
                        f"Base: {removed['legal_basis']['text']}"
                    )
                )
            for excluded in audit.get("prefilter_exclusions", []):
                basis = excluded.get("legal_basis") or {}
                console.print(
                    Text(
                        f"Exclusão prévia: {excluded['norm_id']} · {excluded['status']}\n"
                        f"Base: {basis.get('source', '')}, art. {basis.get('article', '')}"
                    )
                )
            for applied in audit.get("amended_references", []):
                amendment = applied["amendment"]
                target = amendment["target"]
                console.print(
                    Panel(
                        Text(
                            f"NORMA BASE: {applied['norm_id']}\n"
                            f"DISPOSITIVO: Art. {target['article']}, §{target['paragraph']}\n"
                            f"ALTERAÇÃO: {amendment['amended_by']}\n"
                            f"PRECEDÊNCIA: {applied['precedence_rule']}\n"
                            f"CONTEXTO APLICÁVEL: {amendment['effective_text']}"
                        ),
                        title="ALTERAÇÃO PARCIAL",
                    )
                )
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
    saved_output: TextIO | None = None

    try:
        if args.output is not None:
            saved_output = args.output.open("x", encoding="utf-8")
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

        if args.question is not None or args.questions_file is not None:
            sector = args.setor or _choose_scope(output, read_input)
            if sector is None:
                return 0
            output.print(f"Escopo selecionado: {sector} (somente recuperação).")
            questions = (
                load_questions(args.questions_file) if args.questions_file else [args.question]
            )
            failed = False
            for question in questions:
                if not _run_query(
                    output,
                    http_client,
                    question,
                    verbose=args.verbose,
                    sector=sector,
                    output=saved_output,
                ):
                    failed = True
            return 1 if failed else 0
        else:
            sector = args.setor or _choose_scope(output, read_input)
            if sector is None:
                return 0
            output.print(
                '\nDigite sua pergunta. Digite "voltar" para trocar o escopo '
                'ou "sair" para encerrar.'
            )
            while True:
                output.print(f"Escopo selecionado: {sector} (somente recuperação).")
                question = read_input("\nPergunta:\n> ").strip()
                if question.lower() in {"sair", "exit", "quit"}:
                    return 0
                if question.lower() == "voltar":
                    sector = _choose_scope(output, read_input)
                    if sector is None:
                        return 0
                    continue
                if not question:
                    continue
                _run_query(
                    output,
                    http_client,
                    question,
                    verbose=args.verbose,
                    sector=sector,
                    output=saved_output,
                    read_clarification=read_input,
                )
        return 0
    except (EOFError, KeyboardInterrupt):
        output.print("\n[dim]Encerrado.[/dim]")
        return 130 if args.question is not None or args.questions_file is not None else 0
    except (OSError, ValueError) as exc:
        _show_error(output, str(exc))
        return 1
    finally:
        if saved_output is not None:
            saved_output.close()
        if owned_client:
            http_client.close()


def main() -> None:
    _configure_utf8(sys.stdout)
    _configure_utf8(sys.stderr)
    raise SystemExit(run())


if __name__ == "__main__":
    main()
