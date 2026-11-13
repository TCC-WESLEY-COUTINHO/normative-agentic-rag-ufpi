"""Real HTTP/SSE projection with frozen integration graph and controlled providers."""

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import test_retrieval_strategies as retrieval_tests
from fastapi.testclient import TestClient
from langgraph.graph import END, START, StateGraph
from normative_facade_fixtures import answer_data, audit_data
from pydantic import ValidationError

import service.service as service_module
from agents import DEFAULT_AGENT
from client import AgentClient, AgentClientError
from rag_baseline.agent_graph import IntegratedAgentState, build_integrated_graph
from rag_baseline.tool_contracts import NormativeToolResult
from rag_baseline.tool_facade import NormativeRagFacade
from schema import ChatMessage
from service import app

registry = retrieval_tests.registry
runtime = retrieval_tests.runtime
AGENT = "chatbot_ufpi_integrated_v1"
TEXT = "  Ação acadêmica.\r\nPontuação!  \n"
PRIVATE_KEYS = {
    "internal_audit",
    "output_audit",
    "raw_answer",
    "regenerated_answer",
    "guard_violations",
    "prompt",
    "embedding",
    "provider_response",
    "api_key",
    "token",
    "secret",
}


def result(status="ANSWER", core_status="accepted"):
    if status == "ANSWER":
        data = answer_data()
        data.update(answer=TEXT, core_status=core_status, internal_audit=audit_data())
    else:
        data = dict(
            contract_version="1",
            core_version="structured_output_v2",
            status=status,
            retrieval_strategy="dense_vector",
            correlation_id=uuid4(),
        )
        if status == "CLARIFICATION":
            data.update(needs_clarification=True, clarification_question="Graduação ou pós?  \r\n")
        else:
            data.update(error_code="provider_error", safe_message="Falha segura.  \r\n")
    return NormativeToolResult(**data)


def content(value):
    return {
        "ANSWER": value.answer,
        "CLARIFICATION": value.clarification_question,
        "ERROR": value.safe_message,
    }[value.status]


def keys(value):
    if isinstance(value, dict):
        return set(value) | set().union(*(keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(keys(v) for v in value))
    return set()


class ControlledFacade:
    def __init__(self, delegate=None):
        self.delegate, self.status, self.core_status = delegate, "ANSWER", "accepted"
        self.calls, self.results = [], []

    async def query(self, **kwargs):
        self.calls.append(kwargs)
        await asyncio.sleep(0)
        if self.delegate:
            value = await self.delegate.query(**kwargs)
        else:
            data = result(self.status, self.core_status).model_dump()
            data.update(correlation_id=kwargs["correlation_id"], internal_audit=audit_data())
            value = NormativeToolResult(**data)
        self.results.append(value)
        return value


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setattr(service_module.settings, "AUTH_SECRET", None)
    monkeypatch.setattr(service_module.settings, "LANGFUSE_TRACING", False)
    facade = ControlledFacade()
    graph = build_integrated_graph(facade)
    monkeypatch.setattr(service_module, "get_agent", lambda agent_id: graph)
    web = TestClient(app)  # No lifespan: no saver/store, server or external service.
    client = AgentClient(get_info=False, base_url="http://test")
    client.update_agent(AGENT, verify=False)
    real_async_client = httpx.AsyncClient

    def local_post(url, **kwargs):
        kwargs.pop("timeout", None)
        return web.post(url, **kwargs)

    def local_stream(method, url, **kwargs):
        kwargs.pop("timeout", None)
        return web.stream(method, url, **kwargs)

    monkeypatch.setattr(httpx, "post", local_post)
    monkeypatch.setattr(httpx, "stream", local_stream)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(transport=httpx.ASGITransport(app=app), **kwargs),
    )
    return SimpleNamespace(facade=facade, graph=graph, web=web, client=client)


@pytest.mark.parametrize("status", ["ANSWER", "CLARIFICATION", "ERROR"])
def test_schema_roundtrip_retains_type_and_exact_content(status):
    value = result(status)
    message = ChatMessage(type="ai", content=content(value), normative_result=value)
    restored = ChatMessage.model_validate_json(message.model_dump_json())
    assert isinstance(restored.normative_result, NormativeToolResult)
    assert restored.normative_result.model_dump() == value.model_dump()
    assert restored.content.encode() == content(value).encode()
    assert not (keys(message.model_dump(mode="json")) & PRIVATE_KEYS)


def test_legacy_message_remains_valid():
    message = ChatMessage.model_validate({"type": "ai", "content": "legacy"})
    assert message.normative_result is None and message.content == "legacy"


@pytest.mark.parametrize("bad", [{}, "text", {"status": "ANSWER"}])
def test_malformed_normative_payload_is_not_silently_dropped(bad):
    with pytest.raises(ValidationError):
        ChatMessage(type="ai", content="ABC", normative_result=bad)


@pytest.mark.parametrize("private", sorted(PRIVATE_KEYS))
def test_private_keys_rejected_in_public_normative_input(private):
    data = result().model_dump(mode="json")
    data[private] = {"sensitive": "not public"}
    with pytest.raises(ValidationError):
        ChatMessage(type="ai", content=TEXT, normative_result=data)


def test_public_schema_excludes_private_audit():
    schema = ChatMessage.model_json_schema(mode="serialization")
    assert "internal_audit" not in json.dumps(schema)
    assert "normative_result" in schema["properties"]


def test_transport_rejects_content_mismatch():
    with pytest.raises(ValidationError):
        ChatMessage(type="ai", content="rewritten", normative_result=result())


@pytest.mark.parametrize("mode", ["invoke", "stream"])
@pytest.mark.parametrize(
    "status,core_status",
    [
        ("ANSWER", "accepted"),
        ("ANSWER", "regenerated"),
        ("ANSWER", "fallback"),
        ("CLARIFICATION", "accepted"),
        ("ERROR", "accepted"),
    ],
)
def test_sync_client_service_retains_authority(harness, mode, status, core_status):
    harness.facade.status, harness.facade.core_status = status, core_status
    if mode == "invoke":
        message = harness.client.invoke("Consulta normativa")
    else:
        messages = list(harness.client.stream("Consulta normativa", stream_tokens=True))
        assert len(messages) == 1 and isinstance(messages[0], ChatMessage)
        message = messages[0]
    original = harness.facade.results[-1]
    assert isinstance(message.normative_result, NormativeToolResult)
    assert message.normative_result.model_dump() == original.model_dump()
    assert message.content.encode() == content(original).encode()
    assert message.normative_result.internal_audit is None
    assert message.run_id and len(harness.facade.calls) == 1
    assert not (keys(message.model_dump(mode="json")) & PRIVATE_KEYS)


@pytest.mark.parametrize("mode", ["invoke", "stream"])
@pytest.mark.asyncio
async def test_async_client_service_retains_authority(harness, mode):
    if mode == "invoke":
        message = await harness.client.ainvoke("Consulta normativa")
    else:
        messages = [m async for m in harness.client.astream("Consulta normativa")]
        assert len(messages) == 1
        message = messages[0]
    assert isinstance(message.normative_result, NormativeToolResult)
    assert message.content == harness.facade.results[0].answer
    assert message.normative_result.model_dump() == harness.facade.results[0].model_dump()


@pytest.mark.parametrize("mode", ["invoke", "stream"])
def test_direct_over_http_has_no_normative_result(harness, mode):
    message = (
        harness.client.invoke("Oi") if mode == "invoke" else list(harness.client.stream("Oi"))[0]
    )
    assert message.content == "Olá!" and message.normative_result is None
    assert not harness.facade.calls


@pytest.mark.parametrize(
    "question,scope,strategy",
    [
        ("Como solicitar matrícula na graduação?", "graduacao", "dense_vector"),
        ("Art. 68 da 177/2012", "graduacao", "metadata_exact"),
        ("Na 956/2025, quais as regras de matrícula?", "pos_graduacao", "vector_filtered"),
    ],
)
def test_real_core_strategies_through_service_client(harness, runtime, question, scope, strategy):
    service, router, vf, provider, _ = runtime
    provider.scopes[question] = scope
    harness.facade.delegate = NormativeRagFacade(service, router, vf)
    message = harness.client.invoke(question)
    assert message.normative_result.retrieval_strategy == strategy
    assert message.normative_result.domain == scope
    assert message.normative_result.model_dump() == harness.facade.results[-1].model_dump()


@pytest.mark.parametrize("fallback", [False, True])
def test_raw_and_regeneration_never_exposed_on_sse(harness, runtime, fallback):
    service, router, vf, provider, _ = runtime
    question = "Art. 68 da 177/2012"
    provider.scopes[question] = "graduacao"
    raw = "Art. 999 da Resolução 177/2012. RAW_UNSUPPORTED_DRAFT."
    generations = []

    async def chat(**_):
        generations.append(1)
        return raw if fallback or len(generations) == 1 else "Conteúdo controlado."

    provider.chat = chat
    harness.facade.delegate = NormativeRagFacade(service, router, vf)
    response = harness.web.post(
        f"/{AGENT}/stream", json={"message": question, "stream_tokens": True}
    )
    assert response.status_code == 200
    assert "RAW_UNSUPPORTED_DRAFT" not in response.text
    assert "Art. 999" not in response.text
    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    assert len(events) == 1 and events[0]["type"] == "message"
    assert not (keys(events[0]["content"]) & PRIVATE_KEYS)
    message = ChatMessage.model_validate(events[0]["content"])
    assert message.normative_result.core_status == ("fallback" if fallback else "regenerated")
    assert message.normative_result.status == "ANSWER" and len(generations) == 2
    assert message.content == harness.facade.results[-1].answer


@pytest.mark.asyncio
async def test_simultaneous_stream_and_invoke_do_not_mix_result(harness, runtime):
    service, router, vf, provider, _ = runtime
    exact, filtered = "Art. 68 da 177/2012", "Na 956/2025, quais as regras de matrícula?"
    provider.scopes.update({exact: "graduacao", filtered: "pos_graduacao"})
    harness.facade.delegate = NormativeRagFacade(service, router, vf)

    async def streamed():
        return [m async for m in harness.client.astream(filtered)]

    a, stream_messages = await asyncio.gather(harness.client.ainvoke(exact), streamed())
    assert len(stream_messages) == 1
    b = stream_messages[0]
    assert a.normative_result.retrieval_strategy == "metadata_exact"
    assert b.normative_result.retrieval_strategy == "vector_filtered"
    assert a.normative_result.correlation_id != b.normative_result.correlation_id
    # The exact lookup of an amended article also brings the amending provision.
    assert {r.norm_id for r in a.normative_result.references} <= {
        "ufpi-177-2012",
        "ufpi-1056-2026",
    }
    assert all(r.norm_id == "ufpi-956-2025" for r in b.normative_result.references)


def test_legacy_token_remains_string_and_bad_client_payload_fails():
    client = AgentClient(get_info=False)
    assert client._parse_stream_line('data: {"type":"token","content":"legacy"}') == "legacy"
    payload = json.dumps(
        {"type": "message", "content": {"type": "ai", "content": "x", "normative_result": {}}}
    )
    with pytest.raises(AgentClientError):
        client._parse_stream_line("data: " + payload)


def test_default_is_preserved_and_integrated_registration_is_experimental():
    from agents.agents import agents

    assert DEFAULT_AGENT == "chatbot_ufpi_v2"
    assert AGENT in agents
    assert agents[AGENT].experimental
    assert (
        agents[AGENT].runtime_factory
        == "rag_baseline.integrated_runtime:build_integrated_agent_runtime"
    )


@pytest.mark.asyncio
async def test_same_gated_execution_agrees_across_invoke_and_stream(harness, monkeypatch):
    source = await harness.graph.ainvoke({"messages": [("human", "Consulta normativa")]})
    # Replay the same completed execution at the transport boundary. Separate
    # real invocations intentionally create distinct operation UUIDs.
    replay = StateGraph(IntegratedAgentState)
    replay.add_node("completed_execution", lambda state: source)
    replay.add_edge(START, "completed_execution")
    replay.add_edge("completed_execution", END)
    graph = replay.compile(name=AGENT)
    monkeypatch.setattr(service_module, "get_agent", lambda agent_id: graph)
    a = await harness.client.ainvoke("replay")
    streamed = [m async for m in harness.client.astream("replay")]
    assert len(streamed) == 1
    b = streamed[0]
    assert a.normative_result.model_dump() == b.normative_result.model_dump()
    assert a.content == b.content == source["normative_result"].answer
    assert str(a.normative_result.correlation_id) == source["normative_correlation_id"]


@pytest.mark.asyncio
async def test_real_router_clarification_correlation_survives_transport(harness, runtime):
    service, router, vf, provider, _ = runtime
    provider.scopes["Qual é o prazo?"] = None
    harness.facade.delegate = NormativeRagFacade(service, router, vf)
    message = await harness.client.ainvoke("Qual é o prazo?")
    original = harness.facade.results[-1]
    assert message.normative_result.status == "CLARIFICATION"
    assert message.normative_result.correlation_id == original.correlation_id
    assert message.content == original.clarification_question
    assert not provider.embeddings and not provider.prompts


@pytest.mark.asyncio
async def test_stream_does_not_emit_until_facade_and_gate_finish(harness):
    entered, release = asyncio.Event(), asyncio.Event()
    original = harness.facade.query

    async def blocked_query(**kwargs):
        entered.set()
        await release.wait()
        return await original(**kwargs)

    harness.facade.query = blocked_query
    iterator = service_module.message_generator(
        service_module.StreamInput(message="Consulta normativa"), AGENT
    )
    pending = asyncio.create_task(iterator.__anext__())
    await entered.wait()
    assert not pending.done()
    release.set()
    event = await pending
    payload = json.loads(event.removeprefix("data: ").strip())
    assert payload["type"] == "message"
    assert payload["content"]["content"] == harness.facade.results[-1].answer
    assert await iterator.__anext__() == "data: [DONE]\n\n"


@pytest.mark.parametrize("bad", ["incomplete_emission", "foreign_correlation", "rewritten_content"])
@pytest.mark.parametrize("mode", ["invoke", "stream"])
@pytest.mark.asyncio
async def test_incomplete_or_mismatched_terminal_state_is_not_published(
    harness, monkeypatch, bad, mode
):
    source = await harness.graph.ainvoke({"messages": [("human", "Consulta normativa")]})
    if bad == "incomplete_emission":
        source["turn_audit"] = replace(source["turn_audit"], authoritative_emission=False)
    elif bad == "foreign_correlation":
        source["normative_correlation_id"] = str(uuid4())
    else:
        source["messages"][-1].content = "RAW_UNSUPPORTED_DRAFT"
    replay = StateGraph(IntegratedAgentState)
    replay.add_node("invalid_terminal_fixture", lambda state: source)
    replay.add_edge(START, "invalid_terminal_fixture")
    replay.add_edge("invalid_terminal_fixture", END)
    monkeypatch.setattr(service_module, "get_agent", lambda agent_id: replay.compile(name=AGENT))
    async with httpx.AsyncClient() as web:
        response = await web.post(f"http://test/{AGENT}/{mode}", json={"message": "replay"})
    assert "RAW_UNSUPPORTED_DRAFT" not in response.text
    assert "normative_result" not in response.text
    if mode == "invoke":
        assert response.status_code == 500
    else:
        events = [
            json.loads(line[6:])
            for line in response.text.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"
        ]
        assert len(events) == 1 and events[0]["type"] == "error"
