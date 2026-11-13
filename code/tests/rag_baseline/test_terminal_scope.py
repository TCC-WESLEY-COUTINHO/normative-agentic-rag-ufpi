import hashlib
import importlib
import io
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from rich.console import Console

from rag_baseline import api
from rag_baseline.config import BaselineSettings
from rag_baseline.corpus import normalize_chunk
from rag_baseline.service import RagService
from rag_baseline.vector_store import ChromaVectorStore


class Remote:
    def __init__(self):
        self.inputs = []
        self.calls = []

    async def embed(self, texts):
        self.inputs.extend(texts)
        return [[1.0, 0.0] for _ in texts]

    async def chat(self, **payload):
        self.calls.append(payload)
        return "Por exemplo: a regra vale para cada componente."


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    store = ChromaVectorStore(tmp_path, "explicit_scope")
    chunks = [
        normalize_chunk(
            {
                "conteudo": "Regra original.",
                "metadados": {
                    "fonte": source,
                    "setor": sector,
                    "artigo_numero": "20",
                },
            },
            0,
            id_prefix=prefix,
        )
        for sector, source, prefix in (
            ("graduacao", "Resolução 177/2012", "ufpi-177-2012"),
            ("pos_graduacao", "Resolução 956/2025", "ufpi-956-2025"),
        )
    ]
    store.upsert(chunks, [[1.0, 0.0], [0.0, 1.0]])
    remote = Remote()
    monkeypatch.setattr(api.OpenRouterClient, "embed", lambda self, texts: remote.embed(texts))
    monkeypatch.setattr(
        api.OpenRouterClient, "chat", lambda self, **payload: remote.chat(**payload)
    )
    settings = BaselineSettings(
        _env_file=None,
        CHROMA_PERSIST_DIR=tmp_path,
        CHROMA_COLLECTION="explicit_scope",
        OPENROUTER_API_KEY="test",
    )
    client = TestClient(api.create_app(settings))
    return client, remote, store


@pytest.mark.parametrize(
    "sector,expected",
    [
        ("graduacao", {"graduacao"}),
        ("pos_graduacao", {"pos_graduacao"}),
        ("ambos", {"graduacao", "pos_graduacao"}),
    ],
)
def test_explicit_scope_only_filters_retrieval_even_when_question_mentions_other_level(
    runtime,
    sector,
    expected,
):
    client, remote, _ = runtime
    question = "Qual é o prazo do mestrado?"
    response = client.post("/query", json={"question": question, "sector": sector})
    assert response.status_code == 200
    result = response.json()
    assert {r["sector"] for r in result["references"]} == expected
    assert remote.inputs == [question]
    assert len(remote.calls) == 1
    assert remote.calls[0]["user_prompt"].endswith("PERGUNTA:\n" + question)
    assert "SETOR INFORMADO PELO USUÁRIO" not in remote.calls[0]["user_prompt"]
    assert "Por exemplo: a regra vale para cada componente." in result["answer"]
    assert "Fontes:" not in result["answer"]
    assert result["normative_output"]["references"]
    assert result["normative_output"]["status"] == "accepted"


def test_all_three_scopes_share_citation_revision_without_changing_frozen_pilot(runtime):
    client, remote, _ = runtime
    for sector in ("graduacao", "pos_graduacao", "ambos"):
        result = client.post("/query", json={"question": "Posso cancelar?", "sector": sector})
        assert result.status_code == 200
    assert len(remote.calls) == 3
    prompts = {p["system_prompt"] for p in remote.calls}
    assert len(prompts) == 1
    from rag_baseline.normative_output import BODY_SYSTEM_INSTRUCTION

    common_prompt = prompts.pop()
    assert common_prompt.endswith(BODY_SYSTEM_INSTRUCTION)
    assert hashlib.sha256(
        common_prompt.removesuffix(BODY_SYSTEM_INSTRUCTION).encode()
    ).hexdigest() == ("588476666e1c9fdd3740aae5e0e13a51a975e208f3a5570ac99b6c7eae016ae4")
    from rag_baseline.experiment_v2 import PROMPT

    assert hashlib.sha256(PROMPT.encode()).hexdigest() == (
        "dbe2b931d08dfa564bab82e8528b3dbaf5e15c1a737b09087fc61a40496fde4d"
    )


def test_missing_scope_does_not_infer_sector_from_mestrado(runtime):
    client, _, _ = runtime
    result = client.post("/query", json={"question": "Qual é o prazo do mestrado?"})
    assert result.status_code == 200
    assert {r["sector"] for r in result.json()["references"]} == {
        "graduacao",
        "pos_graduacao",
    }


def test_invalid_scope_is_rejected_before_embedding(runtime):
    client, remote, _ = runtime
    response = client.post("/query", json={"question": "Pergunta?", "sector": "setor_invalido"})
    assert response.status_code == 422
    assert remote.inputs == []


@pytest.mark.asyncio
async def test_direct_service_respects_explicit_filter_for_comparison(runtime):
    _, remote, store = runtime
    service = RagService(
        openrouter=remote,
        vector_store=store,
        top_k=5,
        embedding_model="test",
        llm_model="test",
    )
    result = await service.query("Compare graduação e mestrado.", sector="graduacao")
    assert {r.sector for r in result.references} == {"graduacao"}
    assert len(remote.calls) == 1


def test_terminal_keeps_initial_scope_until_user_returns_to_menu():
    demo = importlib.import_module("rag_baseline.demo")
    events, requests = [], []
    entries = iter(
        [
            "1",
            "Posso cancelar?",
            "Qual meu IRA?",
            "voltar",
            "2",
            "Qual o prazo?",
            "voltar",
            "3",
            "Compare as regras.",
            "sair",
        ]
    )

    def read_input(prompt):
        events.append(prompt)
        return next(entries)

    def transport(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "indexed_chunks": 438})
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"answer": "Resposta original.", "references": []})

    output = io.StringIO()
    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(transport)) as client:
        result = demo.run([], client=client, console=Console(file=output), read_input=read_input)
    assert result == 0
    assert requests == [
        {"question": "Posso cancelar?", "sector": "graduacao"},
        {"question": "Qual meu IRA?", "sector": "graduacao"},
        {"question": "Qual o prazo?", "sector": "pos_graduacao"},
        {"question": "Compare as regras.", "sector": "ambos"},
    ]
    assert "escopo" in events[0].lower()
    assert "pergunta" in events[1].lower()
    assert sum("escopo" in prompt.lower() for prompt in events) == 3


@pytest.mark.parametrize("mode", ["blank", "failed_request"])
def test_terminal_keeps_scope_after_blank_input_or_request_error(mode):
    demo = importlib.import_module("rag_baseline.demo")
    requests, prompts = [], []
    inputs = ["2", "Primeira?", "Segunda?", "sair"]
    if mode == "blank":
        inputs.insert(1, "")
    entries = iter(inputs)

    def read_input(prompt):
        prompts.append(prompt)
        return next(entries)

    def transport(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "indexed_chunks": 438})
        requests.append(json.loads(request.content))
        if mode == "failed_request" and len(requests) == 1:
            return httpx.Response(503, json={"detail": "Falha temporária."})
        return httpx.Response(200, json={"answer": "Resposta.", "references": []})

    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(transport)) as client:
        result = demo.run(
            [], client=client, console=Console(file=io.StringIO()), read_input=read_input
        )
    assert result == 0
    assert requests == [
        {"question": "Primeira?", "sector": "pos_graduacao"},
        {"question": "Segunda?", "sector": "pos_graduacao"},
    ]
    assert sum("escopo" in prompt.lower() for prompt in prompts) == 1


def test_terminal_can_change_scope_initially_selected_by_flag(tmp_path):
    demo = importlib.import_module("rag_baseline.demo")
    requests = []
    entries = iter(["Primeira?", "voltar", "1", "Segunda?", "Terceira?", "sair"])

    def transport(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "indexed_chunks": 438})
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"answer": "Resposta.", "references": []})

    target = tmp_path / "session.jsonl"
    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(transport)) as client:
        result = demo.run(
            ["--setor", "pos_graduacao", "--output", str(target)],
            client=client,
            console=Console(file=io.StringIO()),
            read_input=lambda prompt: next(entries),
        )
    assert result == 0
    assert requests == [
        {"question": "Primeira?", "sector": "pos_graduacao"},
        {"question": "Segunda?", "sector": "graduacao"},
        {"question": "Terceira?", "sector": "graduacao"},
    ]
    rows = [json.loads(line) for line in target.read_text("utf-8").splitlines()]
    assert [r["sector"] for r in rows] == ["pos_graduacao", "graduacao", "graduacao"]


def test_terminal_question_flag_requires_explicit_scope_before_post():
    demo = importlib.import_module("rag_baseline.demo")
    events, requests = [], []

    def read_input(prompt):
        events.append(prompt)
        return "2"

    def transport(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "indexed_chunks": 438})
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"answer": "Resposta.", "references": []})

    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(transport)) as client:
        result = demo.run(
            ["--question", "Posso cancelar?"],
            client=client,
            console=Console(file=io.StringIO()),
            read_input=read_input,
        )
    assert result == 0
    assert len(events) == 1
    assert requests == [{"question": "Posso cancelar?", "sector": "pos_graduacao"}]


def test_plain_post_gold_uses_known_scope_and_preserves_first_sixteen_v2_items():
    from rag_baseline.dataset import load_questions, render_gold

    gold = json.loads(Path("../evaluation/datasets/pos_graduacao_v2.json").read_text("utf-8"))
    target = Path("../data/questoes_para_avaliar_o_agente_pos_graduacao.md")
    questions = load_questions(target)
    assert len(questions) == 20
    assert questions[:18] == [item["question"] for item in gold["items"][:18]]
    assert questions[18:] == [
        "Já cancelei essa mesma matéria uma vez. Posso cancelar de novo?",
        "Minha nota final foi 6,5 e tenho 80% de presença. Já estou aprovado?",
    ]
    text = target.read_text("utf-8")
    assert text.split("17. ")[0] == render_gold(gold["items"][:16])
    tail = text.split("17. ")[1]
    assert "Você está falando de um curso" not in tail
    for fact in (
        "Duas reprovações na mesma disciplina",
        "desligamento do programa de pós-graduação",
        "até 12 meses",
        "não entra na contagem do prazo de conclusão",
        "exceto por doença comprovada pela Perícia Médica",
        "parecer favorável do orientador",
        "aprovação do Colegiado Simples",
        "nota mínima sete e frequência mínima de 75%",
        "art. 21, I",
        "art. 38",
        "art. 37",
        "art. 20, § 3º",
    ):
        assert fact in tail


def test_terminal_batch_logs_explicit_scope_and_never_sends_gold(tmp_path):
    demo = importlib.import_module("rag_baseline.demo")
    path, target = tmp_path / "gold.md", tmp_path / "answers.jsonl"
    path.write_text("1. Posso cancelar?\n   SECRET_GOLD\n", encoding="utf-8")
    requests = []

    def transport(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "indexed_chunks": 438})
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"answer": "Resposta original.", "references": []})

    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(transport)) as client:
        result = demo.run(
            ["--questions-file", str(path), "--setor", "ambos", "--output", str(target)],
            client=client,
            console=Console(file=io.StringIO()),
        )
    assert result == 0
    assert requests == [{"question": "Posso cancelar?", "sector": "ambos"}]
    rows = [json.loads(line) for line in target.read_text("utf-8").splitlines()]
    assert rows[0]["sector"] == "ambos"
    assert rows[0]["question"] == "Posso cancelar?"
    assert rows[0]["answer"] == "Resposta original."
    assert rows[0]["error"] is None


def test_terminal_refuses_overwrite_before_contacting_api(tmp_path):
    demo = importlib.import_module("rag_baseline.demo")
    target = tmp_path / "previous.jsonl"
    target.write_text("previous", encoding="utf-8")

    def forbidden(request):
        raise AssertionError("Must refuse an existing output before accessing API")

    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(forbidden)) as client:
        result = demo.run(
            ["--question", "Pergunta?", "--setor", "ambos", "--output", str(target)],
            client=client,
            console=Console(file=io.StringIO()),
        )
    assert result == 1
    assert target.read_text("utf-8") == "previous"


def test_interrupted_batch_returns_nonzero_and_preserves_partial_output(tmp_path):
    demo = importlib.import_module("rag_baseline.demo")
    path, target = tmp_path / "gold.md", tmp_path / "answers.jsonl"
    path.write_text("1. Primeira?\n   gold\n2. Segunda?\n   gold\n", encoding="utf-8")
    queries = []

    def transport(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "indexed_chunks": 438})
        queries.append(json.loads(request.content))
        if len(queries) > 1:
            raise KeyboardInterrupt
        return httpx.Response(200, json={"answer": "Resposta.", "references": []})

    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(transport)) as client:
        result = demo.run(
            ["--questions-file", str(path), "--setor", "ambos", "--output", str(target)],
            client=client,
            console=Console(file=io.StringIO()),
        )
    assert result == 130
    assert len(target.read_text("utf-8").splitlines()) == 1


def test_terminal_rejects_response_from_server_ignoring_explicit_scope(tmp_path):
    demo = importlib.import_module("rag_baseline.demo")
    target = tmp_path / "wrong_scope.jsonl"

    def transport(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "indexed_chunks": 438})
        return httpx.Response(
            200,
            json={
                "answer": "Não entregar esta resposta.",
                "references": [
                    {"sector": "graduacao", "source": "Graduação", "article_number": "20"},
                ],
            },
        )

    output = io.StringIO()
    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(transport)) as client:
        result = demo.run(
            ["--question", "Pergunta?", "--setor", "pos_graduacao", "--output", str(target)],
            client=client,
            console=Console(file=output),
        )
    assert result == 1
    row = json.loads(target.read_text("utf-8"))
    assert "escopo" in row["error"]
    assert row["references"][0]["sector"] == "graduacao"
    assert "Não entregar esta resposta." not in output.getvalue()
