import json
from io import BytesIO, TextIOWrapper

import httpx
import pytest
from rich.console import Console


def _console() -> Console:
    return Console(record=True, force_terminal=False, color_system=None, width=120)


def _client(handler) -> httpx.Client:
    return httpx.Client(
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
    )


def _health() -> dict[str, object]:
    return {
        "status": "ok",
        "indexed_chunks": 376,
        "collection": "ufpi_graduacao_177_2012",
        "embedding_model": "openai/text-embedding-3-small",
        "llm_model": "qwen/test",
        "openrouter_configured": True,
    }


def _query_result(*, references: list[dict[str, object]]) -> dict[str, object]:
    return {
        "answer": "Resposta normativa.",
        "references": references,
        "llm_model": "qwen/test",
        "embedding_model": "openai/test",
    }


def test_successful_health_is_presented_without_raw_json() -> None:
    from rag_baseline.demo import run

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(
            200,
            json=_health(),
        )

    console = _console()
    with _client(handler) as client:
        exit_code = run([], client=client, console=console, read_input=lambda _: "sair")

    output = console.export_text()
    assert exit_code == 0
    assert "API: conectada" in output
    assert "Corpus: 376 chunks" in output
    assert "ufpi_graduacao_177_2012" in output
    assert "openai/text-embedding-3-small" in output
    assert "qwen/test" in output
    assert '"indexed_chunks"' not in output


def test_query_answer_is_rendered_as_markdown() -> None:
    from rag_baseline.demo import run

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=_health())
        return httpx.Response(
            200,
            json={
                "answer": "A **frequência mínima** é de 75%.\n\n- Item normativo",
                "references": [],
                "llm_model": "qwen/test",
                "embedding_model": "openai/test",
            },
        )

    console = _console()
    with _client(handler) as client:
        exit_code = run(["--question", "Qual é a frequência?"], client=client, console=console)

    output = console.export_text()
    assert exit_code == 0
    assert "Resposta" in output
    assert "A frequência mínima é de 75%." in output
    assert "• Item normativo" in output


def test_empty_references_still_show_the_truthful_empty_table() -> None:
    from rag_baseline.demo import run

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=_health())
        return httpx.Response(200, json=_query_result(references=[]))

    console = _console()
    with _client(handler) as client:
        run(["--question", "Pergunta"], client=client, console=console)

    output = console.export_text()
    assert "REFERÊNCIAS RECUPERADAS" in output
    assert "Rank" in output
    assert "Artigo" in output


def test_references_are_formatted_by_rank_article_location_and_distance() -> None:
    from rag_baseline.demo import run

    references = [
        {
            "rank": 1,
            "article_number": "115",
            "chapter_number": "I",
            "chapter_title": "Do Ensino",
            "section_number": "VI",
            "section_title": "Da Frequência",
            "subsection_number": None,
            "subsection_title": None,
            "source": "Resolução 177/2012",
            "content": "Trecho do artigo 115.",
            "distance": 0.4067,
        },
        {
            "rank": 2,
            "article_number": "112",
            "chapter_number": "I",
            "chapter_title": None,
            "section_number": None,
            "section_title": None,
            "subsection_number": None,
            "subsection_title": None,
            "source": "Resolução 177/2012",
            "content": "Trecho do artigo 112.",
            "distance": 0.4187,
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=_health())
        return httpx.Response(200, json=_query_result(references=references))

    console = _console()
    with _client(handler) as client:
        run(["--question", "Pergunta"], client=client, console=console)

    output = console.export_text()
    assert "REFERÊNCIAS RECUPERADAS" in output
    assert "Rank" in output
    assert "Artigo" in output
    assert "Localização" in output
    assert "Distância" in output
    assert "1" in output and "115" in output and "Cap. I · Seção VI" in output
    assert "0.4067" in output
    assert "2" in output and "112" in output and "0.4187" in output
    assert "None" not in output


def test_verbose_mode_includes_full_retrieved_chunk() -> None:
    from rag_baseline.demo import run

    reference = {
        "rank": 1,
        "article_number": "115",
        "chapter_number": "I",
        "chapter_title": "Do Ensino",
        "section_number": "VI",
        "section_title": "Da Frequência",
        "subsection_number": None,
        "subsection_title": None,
        "source": "Resolução 177/2012",
        "content": "CONTEÚDO COMPLETO E EXCLUSIVO DO CHUNK.",
        "distance": 0.4067,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=_health())
        return httpx.Response(200, json=_query_result(references=[reference]))

    console = _console()
    with _client(handler) as client:
        run(["--verbose", "--question", "Pergunta"], client=client, console=console)

    output = console.export_text()
    assert "Trecho 1 · Art. 115" in output
    assert "Capítulo: I — Do Ensino" in output
    assert "Seção: VI — Da Frequência" in output
    assert "CONTEÚDO COMPLETO E EXCLUSIVO DO CHUNK." in output


def test_normal_mode_does_not_include_full_retrieved_chunk() -> None:
    from rag_baseline.demo import run

    reference = {
        "rank": 1,
        "article_number": "115",
        "chapter_number": None,
        "chapter_title": None,
        "section_number": None,
        "section_title": None,
        "subsection_number": None,
        "subsection_title": None,
        "source": "Resolução 177/2012",
        "content": "CONTEÚDO QUE DEVE FICAR OCULTO.",
        "distance": 0.4067,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=_health())
        return httpx.Response(200, json=_query_result(references=[reference]))

    console = _console()
    with _client(handler) as client:
        run(["--question", "Pergunta"], client=client, console=console)

    assert "CONTEÚDO QUE DEVE FICAR OCULTO." not in console.export_text()


def test_missing_hierarchy_fields_never_render_none() -> None:
    from rag_baseline.demo import run

    reference = {
        "rank": 1,
        "article_number": "115",
        "chapter_number": None,
        "chapter_title": None,
        "section_number": None,
        "section_title": None,
        "subsection_number": None,
        "subsection_title": None,
        "source": "Resolução 177/2012",
        "content": "Trecho.",
        "distance": 0.4,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=_health())
        return httpx.Response(200, json=_query_result(references=[reference]))

    console = _console()
    with _client(handler) as client:
        run(["--question", "Pergunta"], client=client, console=console)

    assert "None" not in console.export_text()


def test_unavailable_api_shows_friendly_start_command() -> None:
    from rag_baseline.demo import run

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    console = _console()
    with _client(handler) as client:
        exit_code = run([], client=client, console=console, read_input=lambda _: "sair")

    output = console.export_text()
    assert exit_code == 1
    assert "API não disponível" in output
    assert "uv run uvicorn rag_baseline.api:app --host 127.0.0.1 --port 8080" in output


def test_http_503_shows_friendly_error_without_traceback() -> None:
    from rag_baseline.demo import run

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=_health())
        return httpx.Response(503, json={"detail": "Corpus não indexado."})

    console = _console()
    with _client(handler) as client:
        exit_code = run(["--question", "Pergunta"], client=client, console=console)

    output = console.export_text()
    assert exit_code == 1
    assert "Erro" in output
    assert "Corpus não indexado." in output
    assert "Traceback" not in output


def test_unicode_remains_correct() -> None:
    from rag_baseline.demo import run

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=_health())
        result = _query_result(references=[])
        result["answer"] = "A frequência na graduação consta na seção de avaliação."
        return httpx.Response(200, json=result)

    console = _console()
    with _client(handler) as client:
        run(["--question", "Pergunta"], client=client, console=console)

    output = console.export_text()
    assert "frequência" in output
    assert "graduação" in output
    assert "seção" in output
    assert "avaliação" in output
    assert "frequÃªncia" not in output


def test_non_utf8_output_stream_is_safely_reconfigured() -> None:
    from rag_baseline.demo import _configure_utf8

    buffer = BytesIO()
    stream = TextIOWrapper(buffer, encoding="cp1252")

    _configure_utf8(stream)
    stream.write("frequência · graduação · seção · avaliação")
    stream.flush()

    assert buffer.getvalue().decode("utf-8") == "frequência · graduação · seção · avaliação"


def test_question_argument_performs_exactly_one_query() -> None:
    from rag_baseline.demo import run

    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path == "/health":
            return httpx.Response(200, json=_health())
        assert json.loads(request.content) == {"question": "Pergunta unica"}
        return httpx.Response(200, json=_query_result(references=[]))

    with _client(handler) as client:
        exit_code = run(
            ["--question", "Pergunta unica"],
            client=client,
            console=_console(),
            read_input=lambda _: (_ for _ in ()).throw(AssertionError("prompt inesperado")),
        )

    assert exit_code == 0
    assert requests == [("GET", "/health"), ("POST", "/query")]


def test_articles_in_reference_table_come_only_from_references() -> None:
    from rag_baseline.demo import run

    reference = {
        "rank": 1,
        "article_number": "115",
        "chapter_number": None,
        "chapter_title": None,
        "section_number": None,
        "section_title": None,
        "subsection_number": None,
        "subsection_title": None,
        "source": "Resolução 177/2012",
        "content": "Trecho.",
        "distance": 0.4,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=_health())
        result = _query_result(references=[reference])
        result["answer"] = "O art. 999 foi mencionado pelo modelo."
        return httpx.Response(200, json=result)

    console = _console()
    with _client(handler) as client:
        run(["--question", "Pergunta"], client=client, console=console)

    output = console.export_text()
    references_output = output.split("REFERÊNCIAS RECUPERADAS", maxsplit=1)[1]
    assert "115" in references_output
    assert "999" not in references_output


def test_interactive_mode_queries_until_exit_command() -> None:
    from rag_baseline.demo import run

    query_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal query_count
        if request.url.path == "/health":
            return httpx.Response(200, json=_health())
        query_count += 1
        return httpx.Response(200, json=_query_result(references=[]))

    answers = iter(["Minha pergunta", "sair"])
    console = _console()
    with _client(handler) as client:
        exit_code = run([], client=client, console=console, read_input=lambda _: next(answers))

    assert exit_code == 0
    assert query_count == 1
    assert "Resposta normativa." in console.export_text()


def test_non_ok_health_status_shows_clear_warning() -> None:
    from rag_baseline.demo import run

    health = _health()
    health["status"] = "indexing_required"
    health["indexed_chunks"] = 0

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=health)

    console = _console()
    with _client(handler) as client:
        run([], client=client, console=console, read_input=lambda _: "sair")

    output = console.export_text()
    assert "Atenção" in output
    assert "indexing_required" in output


def test_invalid_query_json_shows_friendly_error() -> None:
    from rag_baseline.demo import run

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=_health())
        return httpx.Response(200, text="isto não é JSON")

    console = _console()
    with _client(handler) as client:
        exit_code = run(["--question", "Pergunta"], client=client, console=console)

    output = console.export_text()
    assert exit_code == 1
    assert "JSON inválido" in output
    assert "Traceback" not in output


def test_malformed_reference_entry_shows_friendly_error() -> None:
    from rag_baseline.demo import run

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=_health())
        return httpx.Response(
            200,
            json={
                "answer": "Resposta.",
                "references": ["referência inválida"],
                "llm_model": "qwen/test",
                "embedding_model": "openai/test",
            },
        )

    console = _console()
    with _client(handler) as client:
        exit_code = run(["--question", "Pergunta"], client=client, console=console)

    output = console.export_text()
    assert exit_code == 1
    assert "JSON inválido" in output
    assert "Traceback" not in output


def test_invalid_health_json_shows_friendly_error() -> None:
    from rag_baseline.demo import run

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="health inválido")

    console = _console()
    with _client(handler) as client:
        exit_code = run([], client=client, console=console, read_input=lambda _: "sair")

    output = console.export_text()
    assert exit_code == 1
    assert "JSON inválido" in output
    assert "Traceback" not in output


def test_ctrl_c_ends_interactive_mode_without_traceback() -> None:
    from rag_baseline.demo import run

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_health())

    def interrupt(_: str) -> str:
        raise KeyboardInterrupt

    console = _console()
    with _client(handler) as client:
        exit_code = run([], client=client, console=console, read_input=interrupt)

    output = console.export_text()
    assert exit_code == 0
    assert "Encerrado" in output
    assert "Traceback" not in output


def test_end_of_input_ends_interactive_mode_without_traceback() -> None:
    from rag_baseline.demo import run

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_health())

    def end_of_input(_: str) -> str:
        raise EOFError

    console = _console()
    with _client(handler) as client:
        exit_code = run([], client=client, console=console, read_input=end_of_input)

    output = console.export_text()
    assert exit_code == 0
    assert "Encerrado" in output
    assert "Traceback" not in output


def test_health_http_error_is_friendly() -> None:
    from rag_baseline.demo import run

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "Serviço em inicialização."})

    console = _console()
    with _client(handler) as client:
        exit_code = run([], client=client, console=console, read_input=lambda _: "sair")

    output = console.export_text()
    assert exit_code == 1
    assert "Serviço em inicialização." in output
    assert "Traceback" not in output


@pytest.mark.parametrize(
    ("status_code", "detail"),
    [
        (422, "A pergunta não pode estar vazia."),
        (502, "O provedor do modelo falhou."),
    ],
)
def test_query_http_errors_are_friendly(status_code: int, detail: str) -> None:
    from rag_baseline.demo import run

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=_health())
        return httpx.Response(status_code, json={"detail": detail})

    console = _console()
    with _client(handler) as client:
        exit_code = run(["--question", "Pergunta"], client=client, console=console)

    output = console.export_text()
    assert exit_code == 1
    assert detail in output
    assert "Traceback" not in output


def test_query_timeout_shows_api_unavailable() -> None:
    from rag_baseline.demo import run

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=_health())
        raise httpx.ReadTimeout("timeout", request=request)

    console = _console()
    with _client(handler) as client:
        exit_code = run(["--question", "Pergunta"], client=client, console=console)

    output = console.export_text()
    assert exit_code == 1
    assert "API não disponível" in output
    assert "Traceback" not in output


@pytest.mark.parametrize("failure_path", ["/health", "/query"])
def test_other_httpx_transport_errors_are_friendly(failure_path: str) -> None:
    from rag_baseline.demo import run

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == failure_path:
            raise httpx.RemoteProtocolError("peer disconnected", request=request)
        return httpx.Response(200, json=_health())

    console = _console()
    with _client(handler) as client:
        exit_code = run(["--question", "Pergunta"], client=client, console=console)

    output = console.export_text()
    assert exit_code == 1
    assert "API não disponível" in output
    assert "Traceback" not in output


def test_query_metadata_shows_time_and_models() -> None:
    from rag_baseline.demo import run

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=_health())
        result = _query_result(references=[])
        result["llm_model"] = "qwen/modelo-da-consulta"
        result["embedding_model"] = "openai/embedding-da-consulta"
        return httpx.Response(200, json=result)

    console = _console()
    with _client(handler) as client:
        run(["--question", "Pergunta"], client=client, console=console)

    output = console.export_text()
    assert "Tempo:" in output
    assert "LLM: qwen/modelo-da-consulta" in output
    assert "Embedding: openai/embedding-da-consulta" in output
