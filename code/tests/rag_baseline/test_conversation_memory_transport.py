"""Composed identity and derived presentation through real ASGI endpoints/client."""

import httpx
import pytest
import test_conversation_memory_followups as memory_tests
import test_typed_normative_transport as transport_tests
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from schema import UserInput
from service.service import _handle_input

conversation = memory_tests.conversation
harness = transport_tests.harness
registry = transport_tests.registry
runtime = transport_tests.runtime


@pytest.mark.asyncio
async def test_service_derives_namespace_from_path_and_declared_identity(
    conversation, harness, tmp_path
):
    c = conversation
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "service.sqlite")) as saver:
        graph = memory_tests.build(c, saver, harness.facade)
        request = UserInput(message="Oi", user_id="A", thread_id="X")
        kwargs, _ = await _handle_input(request, graph, agent_id=transport_tests.AGENT)
        who = c.ConversationIdentity(user_id="A", agent_id=transport_tests.AGENT, thread_id="X")
        assert kwargs["config"]["configurable"]["thread_id"] == who.storage_key()
        assert kwargs["input"]["conversation_identity"] == who
        assert request.thread_id == "X"


@pytest.mark.parametrize("mode", ["invoke", "stream"])
@pytest.mark.asyncio
async def test_http_clarification_and_derived_transport(
    conversation, harness, monkeypatch, tmp_path, mode
):
    c, provider = conversation, memory_tests.Provider()
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "http.sqlite")) as saver:
        graph = memory_tests.build(c, saver, harness.facade, provider)
        monkeypatch.setattr(transport_tests.service_module, "get_agent", lambda agent_id: graph)
        harness.facade.status = "CLARIFICATION"
        first = await harness.client.ainvoke(
            "Posso cancelar uma disciplina?", user_id="A", thread_id="X"
        )
        correlation = first.normative_result.correlation_id
        harness.facade.status = "ANSWER"
        second = await harness.client.ainvoke("graduação", user_id="A", thread_id="X")
        assert second.normative_result.correlation_id == correlation
        assert harness.facade.calls[-1]["question"] == "Posso cancelar uma disciplina?"
        assert harness.facade.calls[-1]["clarification"] == "graduação"
        if mode == "invoke":
            third = await harness.client.ainvoke("Resuma", user_id="A", thread_id="X")
        else:
            messages = [
                m async for m in harness.client.astream("Resuma", user_id="A", thread_id="X")
            ]
            assert len(messages) == 1
            third = messages[0]
        assert third.normative_result is None
        assert isinstance(third.grounded_followup_result, c.GroundedFollowUpResult)
        assert third.grounded_followup_result.source_correlation_id == correlation
        assert third.grounded_followup_result.references == second.normative_result.references
        assert (
            third.grounded_followup_result.temporal_provenance
            == second.normative_result.temporal_provenance
        )
        assert third.content == provider.text and len(harness.facade.calls) == 2
        forbidden = {
            "conversation_memory",
            "last_normative_result_persistence",
            "compatibility_stamp",
            "storage_key",
            "internal_audit",
        }
        assert not (transport_tests.keys(third.model_dump(mode="json")) & forbidden)


@pytest.mark.parametrize("dimension", ["user", "thread", "agent"])
@pytest.mark.asyncio
async def test_http_other_namespace_does_not_continue_pending(
    conversation, harness, monkeypatch, tmp_path, dimension
):
    """A foreign level declaration cannot consume or inherit the original pending turn."""
    c = conversation
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "http-isolate.sqlite")) as saver:
        graph = memory_tests.build(c, saver, harness.facade)
        monkeypatch.setattr(transport_tests.service_module, "get_agent", lambda agent_id: graph)
        harness.facade.status = "CLARIFICATION"
        first = await harness.client.ainvoke("Pergunta de A", user_id="A", thread_id="X")
        original = memory_tests.identity(c, agent=transport_tests.AGENT)
        before = await graph.aget_state(memory_tests.config(original))
        pending = before.values["conversation_memory"].pending_clarification
        assert pending is not None
        assert pending.original_question == "Pergunta de A"
        assert pending.correlation_id == first.normative_result.correlation_id
        calls_before = list(harness.facade.calls)
        other = memory_tests.identity(
            c,
            user="B" if dimension == "user" else "A",
            agent="other-agent" if dimension == "agent" else transport_tests.AGENT,
            thread="Y" if dimension == "thread" else "X",
        )
        if dimension == "agent":
            harness.client.update_agent("other-agent", verify=False)
        declared = await harness.client.ainvoke(
            "graduação",
            user_id=other.user_id,
            thread_id=other.thread_id,
        )
        # R2 handles this as a direct declaration, with no facade call at all:
        # neither the original question nor its correlation crosses namespaces.
        assert harness.facade.calls == calls_before
        assert declared.normative_result is None
        other_state = await graph.aget_state(memory_tests.config(other))
        assert other_state.values["turn_audit"].conversation_action == "DECLARE_LEVEL"
        assert other_state.values["turn_audit"].final_source == "direct_response"
        other_memory = other_state.values["conversation_memory"]
        assert other_memory.declared_level == "graduacao"
        assert other_memory.declared_level_source == "explicit_declaration"
        assert other_memory.pending_clarification is None

        original_state = await graph.aget_state(memory_tests.config(original))
        original_memory = original_state.values["conversation_memory"]
        assert original_memory.pending_clarification == pending
        assert original_memory.declared_level is None
        assert original_memory.declared_level_source is None

        harness.client.update_agent(transport_tests.AGENT, verify=False)
        harness.facade.status = "ANSWER"
        resumed = await harness.client.ainvoke("graduação", user_id="A", thread_id="X")
        assert len(harness.facade.calls) == len(calls_before) + 1
        assert harness.facade.calls[-1] == dict(
            question="Pergunta de A",
            clarification="graduação",
            correlation_id=first.normative_result.correlation_id,
        )
        assert resumed.normative_result.status == "ANSWER"
        assert resumed.normative_result.correlation_id == first.normative_result.correlation_id


@pytest.mark.asyncio
async def test_request_body_cannot_replace_path_agent(conversation, harness, monkeypatch, tmp_path):
    c = conversation
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "path.sqlite")) as saver:
        graph = memory_tests.build(c, saver, harness.facade)
        monkeypatch.setattr(transport_tests.service_module, "get_agent", lambda agent_id: graph)
        async with httpx.AsyncClient() as web:
            response = await web.post(
                f"http://test/{transport_tests.AGENT}/invoke",
                json={
                    "message": "Pergunta",
                    "user_id": "A",
                    "thread_id": "X",
                    "agent_id": "attacker-body-agent",
                },
            )
        assert response.status_code == 200
        who = c.ConversationIdentity(user_id="A", agent_id=transport_tests.AGENT, thread_id="X")
        snapshot = await graph.aget_state(memory_tests.config(who))
        assert snapshot.values["conversation_memory"].conversation_identity == who
        assert who.storage_key() not in response.text


@pytest.mark.parametrize(
    "candidate",
    [
        "Art. 68, VI",
        "parágrafo único",
        "§ único",
        "incisos VI e VII",
        "alíneas a e b",
        "Artigos 68 e 177",
        "Em 2012, o prazo mudou.",
        "A regra vale imediatamente.",
    ],
)
def test_guard_detects_compact_subdivision_and_identifier_year_expansion(conversation, candidate):
    from normative_facade_fixtures import answer_data

    from rag_baseline.conversation_transform import GroundedTransformGuard
    from rag_baseline.tool_contracts import NormativeToolResult

    value = NormativeToolResult(**answer_data())
    assert GroundedTransformGuard().check(value, candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        "alínea “b”",
        "inciso (VI)",
        "Art. nº 177",
        "Artigo n. 177",
        "As normas estão vigentes.",
        "A regra já vigorou.",
        "As disposições são válidas.",
    ],
)
def test_guard_handles_quoted_locators_and_temporal_inflections(conversation, candidate):
    from normative_facade_fixtures import answer_data

    from rag_baseline.conversation_transform import GroundedTransformGuard
    from rag_baseline.tool_contracts import NormativeToolResult

    assert GroundedTransformGuard().check(NormativeToolResult(**answer_data()), candidate)


@pytest.mark.parametrize(
    "field",
    ["checkpoint_id", "checkpoint_ns", "checkpoint_map", "storage_key", "conversation_identity"],
)
@pytest.mark.asyncio
async def test_client_cannot_choose_private_checkpoint_configuration(
    conversation, harness, monkeypatch, tmp_path, field
):
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "private-config.sqlite")) as saver:
        graph = memory_tests.build(conversation, saver, harness.facade)
        monkeypatch.setattr(transport_tests.service_module, "get_agent", lambda agent_id: graph)
        async with httpx.AsyncClient() as web:
            response = await web.post(
                f"http://test/{transport_tests.AGENT}/invoke",
                json={
                    "message": "Oi",
                    "user_id": "A",
                    "thread_id": "X",
                    "agent_config": {field: "external-override"},
                },
            )
        assert response.status_code == 422


@pytest.mark.parametrize(
    "candidate",
    ["Resolução 68.", "A norma passa a valer hoje.", "A norma se aplica a partir de hoje."],
)
def test_review_expansion_regressions(conversation, candidate):
    from normative_facade_fixtures import answer_data

    from rag_baseline.conversation_transform import GroundedTransformGuard
    from rag_baseline.tool_contracts import NormativeToolResult

    assert GroundedTransformGuard().check(NormativeToolResult(**answer_data()), candidate)


@pytest.mark.asyncio
async def test_explicit_domain_shift_reenters_core_without_domain_inference(
    conversation, runtime, tmp_path
):
    from rag_baseline.tool_facade import NormativeRagFacade

    service, router, version_filter, provider, _ = runtime
    facade = NormativeRagFacade(service, router, version_filter=version_filter)
    question = "Posso cancelar uma disciplina na graduação?"
    resolved = conversation.ContextualNormativeQueryResolver().resolve(
        "E na pós?", question, "graduacao"
    )
    provider.scopes.update({question: "graduacao", resolved: "pos_graduacao"})
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "domain-core.sqlite")) as saver:
        graph = memory_tests.build(conversation, saver, facade)
        who = memory_tests.identity(conversation)
        first = await memory_tests.turn(graph, who, question)
        second = await memory_tests.turn(graph, who, "E na pós?")
        assert second["normative_result"].domain == "pos_graduacao"
        assert provider.routes == []
        assert second["normative_result"].correlation_id != first["normative_result"].correlation_id
        assert all(r.norm_id != "ufpi-177-2012" for r in second["normative_result"].references)


@pytest.mark.asyncio
async def test_real_router_receives_original_question_and_clarification(
    conversation, runtime, tmp_path
):
    from rag_baseline.tool_facade import NormativeRagFacade

    service, router, version_filter, provider, _ = runtime
    facade = NormativeRagFacade(service, router, version_filter=version_filter)
    question = "Posso cancelar uma disciplina?"
    provider.scopes[question] = None
    async with AsyncSqliteSaver.from_conn_string(
        str(tmp_path / "clarification-core.sqlite")
    ) as saver:
        graph = memory_tests.build(conversation, saver, facade)
        who = memory_tests.identity(conversation)
        first = await memory_tests.turn(graph, who, question)
        assert first["normative_result"].status == "CLARIFICATION"
        assert not provider.embeddings and not provider.prompts
        provider.scopes[question] = "graduacao"
        second = await memory_tests.turn(graph, who, "graduação")
        assert second["normative_result"].status == "ANSWER"
        assert second["normative_result"].correlation_id == first["normative_result"].correlation_id
        assert provider.routes[-1]["question"] == question
        assert provider.routes[-1]["clarification"] == "graduação"


@pytest.mark.parametrize("mode", ["invoke", "stream"])
def test_sync_client_restores_typed_derived_result(conversation, monkeypatch, mode):
    import json

    from normative_facade_fixtures import answer_data

    from client import AgentClient
    from rag_baseline.tool_contracts import NormativeToolResult
    from schema import ChatMessage

    source = NormativeToolResult(**answer_data())
    derived = conversation.GroundedFollowUpTransformer().repeat(source)
    payload = ChatMessage(
        type="ai", content=derived.content, grounded_followup_result=derived
    ).model_dump(mode="json")

    def respond(request):
        if request.url.path.endswith("/stream"):
            return httpx.Response(
                200,
                text="data: "
                + json.dumps({"type": "message", "content": payload})
                + "\n\ndata: [DONE]\n\n",
            )
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(
        httpx.HTTPTransport, "handle_request", lambda _transport, request: respond(request)
    )
    client = AgentClient("http://test", get_info=False)
    client.update_agent(transport_tests.AGENT, verify=False)
    result = client.invoke("repita") if mode == "invoke" else list(client.stream("repita"))[0]
    assert isinstance(result.grounded_followup_result, conversation.GroundedFollowUpResult)
    assert result.grounded_followup_result == derived


@pytest.mark.parametrize(
    "candidate", ["Art. n.º 177", "Resolução n.º 68", "A norma valerá futuramente."]
)
def test_review_number_marker_and_future_inflections(conversation, candidate):
    from normative_facade_fixtures import answer_data

    from rag_baseline.conversation_transform import GroundedTransformGuard
    from rag_baseline.tool_contracts import NormativeToolResult

    assert GroundedTransformGuard().check(NormativeToolResult(**answer_data()), candidate)
