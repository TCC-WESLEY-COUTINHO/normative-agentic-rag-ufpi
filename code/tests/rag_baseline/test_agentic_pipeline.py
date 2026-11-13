import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from rich.console import Console

from rag_baseline.agentic import AgenticRagService, build_graph
from rag_baseline.api import create_app
from rag_baseline.config import BaselineSettings
from rag_baseline.corpus import normalize_chunk
from rag_baseline.demo import run
from rag_baseline.models import RetrievedChunk
from rag_baseline.router import NormativeRouter
from rag_baseline.service import RagService
from rag_baseline.vector_store import ChromaVectorStore
from rag_baseline.versioning import NormativeRegistry, VersionFilter


def decision(scope):
    return dict(
        scope=scope,
        needs_clarification=scope is None,
        clarification_question="Qual nível?" if scope is None else None,
        reason_code={
            None: "insufficient_scope_signal",
            "graduacao": "explicit_graduacao",
            "pos_graduacao": "explicit_pos",
            "ambas": "cross_norm_comparison",
        }[scope],
    )


class Remote:
    llm_model = "test"

    def __init__(self, scopes):
        self.scopes = iter(scopes)
        self.routes, self.prompts, self.embeddings = [], [], []

    async def structured_chat(self, **payload):
        self.routes.append(json.loads(payload["user_prompt"]))
        return json.dumps(decision(next(self.scopes)))

    async def embed(self, texts):
        self.embeddings.extend(texts)
        return [[1.0, 0.0]]

    async def chat(self, **payload):
        self.prompts.append(payload)
        return "Resposta com evidência."


def runtime(tmp_path, scopes):
    store = ChromaVectorStore(tmp_path, "agentic_test")
    chunks = [
        normalize_chunk(
            dict(
                conteudo=f"Content {norm}",
                metadados=dict(fonte=norm, setor=sector, artigo_numero=str(i)),
            ),
            i,
            id_prefix=norm,
        )
        for i, norm, sector in [
            (1, "old", "pos_graduacao"),
            *[(i, f"pos{i}", "pos_graduacao") for i in range(2, 7)],
            (7, "grad", "graduacao"),
        ]
    ]
    store.upsert(chunks, [[1.0, i / 10] for i in range(len(chunks))])
    registry = NormativeRegistry(
        norms=[
            dict(
                norm_id="old",
                sector="pos_graduacao",
                sources=["old"],
                status="revogada",
                legal_basis=dict(
                    source="fixture", article="62", text="Explicit revocation fixture"
                ),
            )
        ]
    )
    remote = Remote(scopes)
    service = RagService(
        openrouter=remote, vector_store=store, top_k=5, embedding_model="test", llm_model="test"
    )
    agent = AgenticRagService(service, NormativeRouter(remote), VersionFilter(registry))
    return service, remote, agent


@pytest.mark.asyncio
async def test_prefilter_preserves_five_eligible_contexts_and_never_generates_obsolete(tmp_path):
    service, remote, agent = runtime(tmp_path, ["pos_graduacao"])
    result = await agent.query("Requisitos da pós?")
    assert len(result.references) == 5
    assert {r.sector for r in result.references} == {"pos_graduacao"}
    assert all(r.source != "old" for r in result.references)
    assert "Content old" not in remote.prompts[0]["user_prompt"]
    assert result.version_filter["prefilter_excluded_norm_ids"] == ["old"]
    assert result.version_filter["shortfall"] == 0
    assert len(remote.embeddings) == 1


@pytest.mark.asyncio
async def test_batch_clarification_does_not_retrieve_or_generate_or_impute_scope(tmp_path):
    _, remote, agent = runtime(tmp_path, [None])
    result = await agent.query("Posso cancelar?")
    assert result.needs_clarification
    assert result.selected_scope is None
    assert result.references == []
    assert remote.embeddings == remote.prompts == []


@pytest.mark.asyncio
async def test_graph_interrupt_resumes_original_question_once(tmp_path):
    service, remote, agent = runtime(tmp_path, [None, "pos_graduacao"])
    graph = build_graph(
        service, agent.router, agent.version_filter, interactive=True, checkpointer=InMemorySaver()
    )
    config = {"configurable": {"thread_id": "test"}}
    paused = await graph.ainvoke({"question": "Posso cancelar?"}, config)
    assert paused["__interrupt__"]
    assert remote.embeddings == []
    completed = await graph.ainvoke(Command(resume="Pós-graduação"), config)
    assert completed["result"].selected_scope == "pos_graduacao"
    assert remote.routes[-1] == {"question": "Posso cancelar?", "clarification": "Pós-graduação"}
    assert "Posso cancelar?" in remote.prompts[0]["user_prompt"]


@pytest.mark.asyncio
async def test_unresolved_second_scope_ends_without_second_interrupt(tmp_path):
    service, remote, agent = runtime(tmp_path, [None, None])
    graph = build_graph(
        service, agent.router, agent.version_filter, interactive=True, checkpointer=InMemorySaver()
    )
    config = {"configurable": {"thread_id": "unresolved"}}
    await graph.ainvoke({"question": "Posso cancelar?"}, config)
    completed = await graph.ainvoke(Command(resume="Não sei"), config)
    assert not completed.get("__interrupt__")
    assert completed["result"].needs_clarification
    assert completed["result"].references == []
    assert len(remote.routes) == 2
    assert remote.prompts == []


def test_manual_api_never_calls_router_and_keeps_existing_contract(tmp_path):
    service, remote, agent = runtime(tmp_path, [])
    client = TestClient(
        create_app(
            BaselineSettings(_env_file=None),
            service=service,
            agentic_service=agent,
            vector_store=service.vector_store,
        )
    )
    for sector in ("graduacao", "pos_graduacao", "ambos"):
        result = client.post("/query", json={"question": "Posso cancelar?", "sector": sector})
        assert result.status_code == 200
        assert "route" not in result.json()
    assert remote.routes == []


def test_automatic_api_supports_one_stateless_clarification_and_batch_stop(tmp_path):
    service, remote, agent = runtime(tmp_path, [None, "pos_graduacao"])
    client = TestClient(
        create_app(
            BaselineSettings(_env_file=None),
            service=service,
            agentic_service=agent,
            vector_store=service.vector_store,
        )
    )
    first = client.post("/query", json={"question": "Posso cancelar?", "sector": "automatico"})
    assert first.status_code == 200
    assert first.json()["needs_clarification"]
    assert remote.prompts == []
    final = client.post(
        "/query",
        json={
            "question": "Posso cancelar?",
            "sector": "automatico",
            "clarification": "Pós-graduação",
        },
    )
    assert final.status_code == 200
    assert final.json()["selected_scope"] == "pos_graduacao"


@pytest.mark.asyncio
async def test_defensive_filter_removes_obsolete_from_references_and_generator(tmp_path):
    service, remote, agent = runtime(tmp_path, ["pos_graduacao"])

    async def corrupt_retriever(*args, **kwargs):
        return [
            RetrievedChunk(
                id="old-art-1-idx-0",
                content="OLD SECRET CONTENT",
                source="old",
                sector="pos_graduacao",
                article_number="1",
                article_label="Art. 1",
                original_index=0,
                rank=1,
                distance=0.1,
            )
        ]

    service.retrieve = corrupt_retriever
    result = await agent.query("Dúvida da pós")
    assert result.references == []
    assert remote.prompts == []
    assert result.version_filter["removed_references"][0]["reason"] == "revogada"
    assert result.version_filter["shortfall"] == 5


@pytest.mark.asyncio
async def test_filter_disabled_preserves_manual_service_generation(tmp_path):
    service, remote, _ = runtime(tmp_path, ["pos_graduacao"])

    async def old_only(*args, **kwargs):
        return [
            RetrievedChunk(
                id="old-art-1-idx-0",
                content="OLD CONTENT",
                source="old",
                sector="pos_graduacao",
                article_number="1",
                article_label="Art. 1",
                original_index=0,
                rank=1,
                distance=0.1,
            )
        ]

    service.retrieve = old_only
    result = await service.query("Minha dúvida")
    assert result.references[0].source == "old"
    assert "OLD CONTENT" in remote.prompts[0]["user_prompt"]


def test_terminal_automatic_clarifies_once_and_batch_never_reads_answer(tmp_path):
    requests = []

    def transport(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        data = json.loads(request.content)
        requests.append(data)
        return httpx.Response(
            200,
            json={
                "answer": "Qual nível?",
                "references": [],
                "needs_clarification": True,
                "clarification_question": "Qual nível?",
                "route": decision(None),
            },
        )

    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(transport)) as client:
        entries = iter(["Posso cancelar?", "Não sei", "sair"])
        assert (
            run(
                ["--setor", "automatico"],
                client=client,
                console=Console(file=io.StringIO()),
                read_input=lambda _: next(entries),
            )
            == 0
        )
        assert len(requests) == 2
        assert requests[-1]["clarification"] == "Não sei"
        requests.clear()

        def no_input(_):
            pytest.fail("Batch cannot invent clarification")

        assert (
            run(
                ["--setor", "automatico", "--question", "Posso cancelar?"],
                client=client,
                console=Console(file=io.StringIO()),
                read_input=no_input,
            )
            == 0
        )
        assert len(requests) == 1


@pytest.mark.asyncio
async def test_registered_graph_routes_each_new_human_question_in_same_thread(tmp_path):
    service, remote, agent = runtime(tmp_path, [None, "pos_graduacao", None])
    graph = build_graph(
        service, agent.router, agent.version_filter, interactive=True, checkpointer=InMemorySaver()
    )
    config = {"configurable": {"thread_id": "multi-turn"}}
    first = await graph.ainvoke({"messages": [HumanMessage(content="Graduação?")]}, config)
    assert first["result"].selected_scope == "graduacao"
    assert remote.routes == []
    paused = await graph.ainvoke({"messages": [HumanMessage(content="Posso cancelar?")]}, config)
    assert paused["__interrupt__"]
    final = await graph.ainvoke(Command(resume="Pós-graduação"), config)
    assert final["result"].selected_scope == "pos_graduacao"
    again = await graph.ainvoke({"messages": [HumanMessage(content="Posso trancar?")]}, config)
    assert again["__interrupt__"]
    assert remote.routes[-1] == {"question": "Posso trancar?"}


@pytest.mark.asyncio
async def test_historical_context_has_warning_and_retains_obsolete_reference(tmp_path):
    _, remote, agent = runtime(tmp_path, ["pos_graduacao"])
    result = await agent.query("Como era a regra antiga na pós-graduação?")
    assert any(r.source == "old" for r in result.references)
    assert "CONSULTA HISTÓRICA" in remote.prompts[0]["user_prompt"]
    assert "revogada" in remote.prompts[0]["user_prompt"]
    assert result.version_filter["historical"]


def test_current_question_takes_precedence_over_historical_mention():
    from rag_baseline.agentic import is_historical_question

    assert not is_historical_question("A regra antiga é aplicável atualmente na pós-graduação?")


@pytest.mark.asyncio
async def test_current_intent_in_stateless_clarification_overrides_original_history(tmp_path):
    _, remote, agent = runtime(tmp_path, ["pos_graduacao"])
    result = await agent.query(
        "Como era a regra antiga?", clarification="Quero a regra vigente agora na pós-graduação"
    )
    assert not result.version_filter["historical"]
    assert all(r.source != "old" for r in result.references)
    assert "CONSULTA HISTÓRICA" not in remote.prompts[0]["user_prompt"]


@pytest.mark.asyncio
async def test_current_intent_in_resumed_clarification_overrides_original_history(tmp_path):
    service, _, agent = runtime(tmp_path, [None, "pos_graduacao"])
    graph = build_graph(
        service, agent.router, agent.version_filter, interactive=True, checkpointer=InMemorySaver()
    )
    config = {"configurable": {"thread_id": "temporal-intent"}}
    await graph.ainvoke({"question": "Como era a regra antiga?"}, config)
    result = (
        await graph.ainvoke(Command(resume="Quero a regra vigente agora na pós-graduação"), config)
    )["result"]
    assert not result.version_filter["historical"]
    assert all(r.source != "old" for r in result.references)


@pytest.mark.asyncio
async def test_new_direct_graph_question_never_inherits_previous_clarification(tmp_path):
    service, remote, agent = runtime(tmp_path, [None, "pos_graduacao", None])
    graph = build_graph(
        service, agent.router, agent.version_filter, interactive=True, checkpointer=InMemorySaver()
    )
    config = {"configurable": {"thread_id": "direct-question"}}
    await graph.ainvoke({"question": "Posso cancelar?"}, config)
    await graph.ainvoke(Command(resume="Pós-graduação"), config)
    result = await graph.ainvoke({"question": "Posso trancar?"}, config)
    assert result["__interrupt__"]
    assert remote.routes[-1] == {"question": "Posso trancar?"}
