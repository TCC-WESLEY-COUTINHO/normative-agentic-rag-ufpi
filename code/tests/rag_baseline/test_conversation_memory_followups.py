"""Private checkpoint authority, declared composite namespaces and bounded follow-ups."""

import asyncio
import importlib

import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from normative_facade_fixtures import answer_data, audit_data

from rag_baseline.agent_graph import build_integrated_graph
from rag_baseline.tool_contracts import NormativeToolResult
from schema import ChatMessage


@pytest.fixture
def conversation():
    module = "rag_baseline.conversation_graph"
    if importlib.util.find_spec(module) is None:

        class Missing:
            def __getattr__(self, name):
                pytest.fail("Conversation memory boundary is not implemented")

        return Missing()
    return importlib.import_module(module)


def stamp(c, **changes):
    return c.NormativeMemoryCompatibilityStamp(
        **{
            **dict(
                memory_version="1",
                contract_version="1",
                core_version="structured_output_v2",
                corpus_fingerprint="a" * 64,
                registry_fingerprint="b" * 64,
            ),
            **changes,
        }
    )


def identity(c, user="A", agent="integrated", thread="X"):
    return c.ConversationIdentity(user_id=user, agent_id=agent, thread_id=thread)


def config(who):
    return {"configurable": {"thread_id": who.storage_key()}}


async def turn(graph, who, text):
    return await graph.ainvoke(
        {"messages": [("human", text)], "conversation_identity": who}, config(who)
    )


class Facade:
    def __init__(self):
        self.calls, self.results = [], []
        self.status = "ANSWER"
        self.core_status = "accepted"
        self.error = None

    async def query(self, **kwargs):
        self.calls.append(kwargs)
        await asyncio.sleep(0)
        if self.error:
            raise self.error
        if self.status == "ANSWER":
            data = answer_data()
            data.update(
                answer="Resposta anterior autorizada.\r\nArt. 68 da Resolução 177/2012.",
                core_status=self.core_status,
                internal_audit=audit_data(),
            )
        else:
            data = dict(
                contract_version="1",
                core_version="structured_output_v2",
                status=self.status,
                retrieval_strategy="dense_vector",
            )
            if self.status == "CLARIFICATION":
                data.update(needs_clarification=True, clarification_question="Graduação ou pós?")
            else:
                data.update(error_code="provider_error", safe_message="Falha segura.")
        data["correlation_id"] = kwargs["correlation_id"]
        result = NormativeToolResult(**data)
        self.results.append(result)
        return result


class Provider:
    def __init__(self, text="Apresentação mais curta."):
        self.calls, self.text, self.error = [], text, None

    async def transform(self, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return self.text


def build(c, saver, facade, provider=None, current=None):
    transformer = c.GroundedFollowUpTransformer(provider) if provider is not None else None
    return build_integrated_graph(
        facade, checkpointer=saver, memory_stamp=current or stamp(c), transformer=transformer
    )


def source(state):
    return NormativeToolResult.from_persistence(
        state["conversation_memory"].last_normative_result_persistence
    )


def test_composite_storage_key_is_stable_and_unambiguous(conversation):
    c = conversation
    a = identity(c)
    assert a.storage_key() == identity(c).storage_key()
    assert len(a.storage_key()) == 64 and "A" not in a.storage_key()
    variants = [identity(c, user="B"), identity(c, agent="other"), identity(c, thread="Y")]
    assert len({a.storage_key(), *(v.storage_key() for v in variants)}) == 4
    assert (
        identity(c, user="a|b", agent="c").storage_key()
        != identity(c, user="a", agent="b|c").storage_key()
    )


@pytest.mark.asyncio
async def test_sqlite_reopen_preserves_private_envelope_and_repeat(conversation, tmp_path):
    c, facade = conversation, Facade()
    who = identity(c)
    path = str(tmp_path / "memory.sqlite")
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        first = await turn(build(c, saver, facade), who, "Qual o prazo na graduação?")
        original = source(first)
        assert original.internal_audit == facade.results[0].internal_audit
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        second = await turn(build(c, saver, facade), who, "Repita.")
        derived = second["grounded_followup_result"]
        assert second["normative_result"] is None
        assert derived.kind == "REPEAT" and derived.content == original.answer
        assert derived.source_correlation_id == original.correlation_id
        assert derived.references == original.references
        assert derived.temporal_provenance == original.temporal_provenance
        assert source(second).internal_audit == original.internal_audit
        assert len(facade.calls) == 1


@pytest.mark.parametrize("dimension", ["user", "agent", "thread"])
@pytest.mark.asyncio
async def test_foreign_namespace_cannot_reuse_last_result_or_pending(
    conversation, tmp_path, dimension
):
    c, facade = conversation, Facade()
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "isolation.sqlite")) as saver:
        graph = build(c, saver, facade)
        await turn(graph, identity(c), "Qual o prazo?")
        facade.status = "CLARIFICATION"
        await turn(graph, identity(c), "Outra pergunta ambígua")
        other = identity(c, **{dimension: "other"})
        state = await turn(graph, other, "Repita")
        assert state["grounded_followup_result"] is None
        assert state["normative_result"] is None
        assert state["conversation_memory"] is None
        assert len(facade.calls) == 2


@pytest.mark.asyncio
async def test_pending_survives_reopen_social_and_repeated_clarification(conversation, tmp_path):
    c, facade, who = conversation, Facade(), identity(conversation)
    facade.status = "CLARIFICATION"
    path = str(tmp_path / "pending.sqlite")
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        first = await turn(build(c, saver, facade), who, "Posso cancelar uma disciplina?")
        pending = first["conversation_memory"].pending_clarification
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        graph = build(c, saver, facade)
        social = await turn(graph, who, "Obrigado.")
        assert social["conversation_memory"].pending_clarification == pending
        assert len(facade.calls) == 1
        # Only a closed domain reply resumes this operation; the controlled
        # facade can still report that its clarification was unresolved.
        again = await turn(graph, who, "pós")
        assert (
            again["conversation_memory"].pending_clarification.correlation_id
            == pending.correlation_id
        )
        facade.status = "ANSWER"
        answered = await turn(graph, who, "graduação")
        assert answered["conversation_memory"].pending_clarification is None
        assert source(answered).correlation_id == pending.correlation_id
        assert answered["conversation_memory"].last_normative_question == pending.original_question
        assert facade.calls[-1] == dict(
            question=pending.original_question,
            clarification="graduação",
            correlation_id=pending.correlation_id,
        )


@pytest.mark.parametrize("command", ["cancelar", "cancele", "esquece", "deixa pra lá", "Cancele."])
@pytest.mark.asyncio
async def test_cancel_preserves_last_answer_and_clears_pending(conversation, tmp_path, command):
    c, facade, who = conversation, Facade(), identity(conversation)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "cancel.sqlite")) as saver:
        graph = build(c, saver, facade)
        first = await turn(graph, who, "Pergunta original")
        facade.status = "CLARIFICATION"
        await turn(graph, who, "Nova pergunta ambígua")
        state = await turn(graph, who, command)
        assert state["conversation_memory"].pending_clarification is None
        assert source(state).model_dump() == source(first).model_dump()
        assert len(facade.calls) == 2


@pytest.mark.asyncio
async def test_terminal_error_clears_pending_and_preserves_previous_answer(conversation, tmp_path):
    c, facade, who = conversation, Facade(), identity(conversation)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "error.sqlite")) as saver:
        graph = build(c, saver, facade)
        first = await turn(graph, who, "Primeira pergunta")
        facade.status = "CLARIFICATION"
        await turn(graph, who, "Segunda pergunta")
        facade.status = "ERROR"
        state = await turn(graph, who, "graduação")
        assert state["conversation_memory"].pending_clarification is None
        assert source(state).model_dump() == source(first).model_dump()
        assert state["grounded_followup_result"] is None


@pytest.mark.parametrize(
    "utterance,kind",
    [
        ("Explique melhor.", "REPHRASE"),
        ("Explique mais simples", "REPHRASE"),
        ("Em outras palavras", "REPHRASE"),
        ("Resuma", "SUMMARY"),
        ("Resuma isso", "SUMMARY"),
    ],
)
@pytest.mark.asyncio
async def test_transform_has_only_public_source_and_zero_new_facade(
    conversation, tmp_path, utterance, kind
):
    c, facade, provider = conversation, Facade(), Provider()
    who = identity(c)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "transform.sqlite")) as saver:
        graph = build(c, saver, facade, provider)
        first = await turn(graph, who, "Qual o prazo na graduação?")
        original = source(first)
        state = await turn(graph, who, utterance)
        value = state["grounded_followup_result"]
        assert value.kind == kind and value.content == provider.text
        assert value.source_correlation_id == original.correlation_id
        assert (
            value.references == original.references
            and value.temporal_provenance == original.temporal_provenance
        )
        assert (
            state["normative_result"] is None
            and len(facade.calls) == 1
            and len(provider.calls) == 1
        )
        assert "UNSAFE RAW" not in provider.calls[0].model_dump_json()
        assert not (
            {"messages", "chunks", "internal_audit", "corpus"} & set(provider.calls[0].model_dump())
        )
        assert source(state).answer == original.answer
        msg = ChatMessage(type="ai", content=value.content, grounded_followup_result=value)
        restored = ChatMessage.model_validate_json(msg.model_dump_json())
        assert isinstance(restored.grounded_followup_result, c.GroundedFollowUpResult)


@pytest.mark.parametrize(
    "expanded",
    [
        "Art. 99 da Resolução 177/2012.",
        "Resolução 956/2025.",
        "ufpi-956-2025",
        "§ 5º",
        "inciso VI",
        "alínea b",
        "caput",
        "18 de dezembro de 2025",
        "Desde 2024.",
        "A norma está vigente.",
        "Foi publicada e produz efeitos imediatos.",
        "Cancelamento em 10 dias.",
    ],
)
@pytest.mark.asyncio
async def test_expansion_falls_back_to_source_without_retry(conversation, tmp_path, expanded):
    c, facade, provider = conversation, Facade(), Provider(expanded)
    who = identity(c)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "guard.sqlite")) as saver:
        graph = build(c, saver, facade, provider)
        first = await turn(graph, who, "Pergunta normativa")
        state = await turn(graph, who, "Resuma")
        assert state["grounded_followup_result"].guard_status == "FALLBACK_TO_SOURCE"
        assert state["messages"][-1].content == source(first).answer
        assert len(provider.calls) == 1 and len(facade.calls) == 1


@pytest.mark.parametrize("why", ["provider_error", "core_fallback"])
@pytest.mark.asyncio
async def test_transform_failure_or_core_fallback_uses_source(conversation, tmp_path, why):
    c, facade, provider = conversation, Facade(), Provider()
    if why == "provider_error":
        provider.error = RuntimeError("private provider body")
    else:
        facade.core_status = "fallback"
    who = identity(c)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "fallback.sqlite")) as saver:
        graph = build(c, saver, facade, provider)
        first = await turn(graph, who, "Pergunta")
        state = await turn(graph, who, "Explique melhor")
        assert state["messages"][-1].content == source(first).answer
        assert len(provider.calls) == (1 if why == "provider_error" else 0)
        assert len(facade.calls) == 1


@pytest.mark.parametrize(
    "field,new",
    [
        ("core_version", "old"),
        ("contract_version", "old"),
        ("corpus_fingerprint", "c" * 64),
        ("registry_fingerprint", "d" * 64),
        ("memory_version", "0"),
    ],
)
@pytest.mark.asyncio
async def test_stale_rejected_for_transform_but_new_question_refreshes(
    conversation, tmp_path, field, new
):
    c, facade, provider = conversation, Facade(), Provider()
    who = identity(c)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "stale.sqlite")) as saver:
        old_graph = build(c, saver, facade, provider, current=stamp(c, **{field: new}))
        await turn(old_graph, who, "Pergunta antiga")
        graph = build(c, saver, facade, provider)
        rejected = await turn(graph, who, "Explique melhor")
        assert rejected["normative_result"] is None and rejected["grounded_followup_result"] is None
        assert rejected["turn_audit"].memory_status == "STALE"
        assert not provider.calls and len(facade.calls) == 1
        fresh = await turn(graph, who, "Nova pergunta normativa completa")
        assert fresh["conversation_memory"].compatibility_stamp == stamp(c)
        assert len(facade.calls) == 2


@pytest.mark.parametrize("bad", ["identity", "envelope"])
@pytest.mark.asyncio
async def test_corrupt_memory_not_reused(conversation, tmp_path, bad):
    c, facade, who = conversation, Facade(), identity(conversation)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "corrupt.sqlite")) as saver:
        graph = build(c, saver, facade)
        state = await turn(graph, who, "Pergunta original")
        data = state["conversation_memory"].model_dump(mode="json")
        if bad == "identity":
            data["conversation_identity"]["user_id"] = "foreign"
        else:
            data["last_normative_result_persistence"] = {"invalid": "envelope"}
        await graph.aupdate_state(config(who), {"conversation_memory": data})
        rejected = await turn(graph, who, "Repita")
        assert rejected["grounded_followup_result"] is None
        assert rejected["turn_audit"].memory_status == "INVALID"
        assert len(facade.calls) == 1


@pytest.mark.parametrize(
    "followup,target",
    [
        ("E na pós?", "pós-graduação"),
        ("E na graduação?", "graduação"),
        ("E para ambos?", "graduação e na pós-graduação"),
    ],
)
@pytest.mark.asyncio
async def test_domain_shift_reenters_facade_without_manual_scope(
    conversation, tmp_path, followup, target
):
    c, facade, who = conversation, Facade(), identity(conversation)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "domain.sqlite")) as saver:
        graph = build(c, saver, facade)
        first = await turn(graph, who, "Qual o prazo para cancelamento na graduação?")
        shifted = await turn(graph, who, followup)
        assert len(facade.calls) == 2
        sent = facade.calls[-1]
        assert target in sent["question"] and "cancelamento" in sent["question"]
        assert set(sent) == {"question", "clarification", "correlation_id"}
        assert (
            shifted["normative_result"].correlation_id != first["normative_result"].correlation_id
        )


@pytest.mark.asyncio
async def test_new_topic_and_mixed_transform_require_fresh_rag(conversation, tmp_path):
    c, facade, who = conversation, Facade(), identity(conversation)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "new-topic.sqlite")) as saver:
        graph = build(c, saver, facade)
        await turn(graph, who, "Pergunta A")
        await turn(graph, who, "E como funciona trancamento do curso?")
        await turn(graph, who, "Resuma e acrescente o prazo atual")
        assert len(facade.calls) == 3


@pytest.mark.asyncio
async def test_concurrent_identities_restore_separate_sources(conversation, tmp_path):
    c, facade = conversation, Facade()
    who = [identity(c), identity(c, user="B"), identity(c, thread="Y")]
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "concurrency.sqlite")) as saver:
        graph = build(c, saver, facade)
        first = await asyncio.gather(*(turn(graph, i, f"Pergunta {n}") for n, i in enumerate(who)))
        second = await asyncio.gather(*(turn(graph, i, "Repita") for i in who))
        assert len(facade.calls) == 3
        assert len({s["grounded_followup_result"].source_correlation_id for s in second}) == 3
        for a, b in zip(first, second, strict=True):
            assert (
                b["grounded_followup_result"].source_correlation_id
                == a["normative_result"].correlation_id
            )


def test_fingerprint_factory_uses_actual_collection_and_registry(conversation, tmp_path):
    c = conversation
    from test_retrieval_strategies import registry, runtime

    service, _, _, _, _ = runtime.__wrapped__(tmp_path, registry.__wrapped__())
    actual = c.build_memory_stamp(service.vector_store)
    assert len(actual.corpus_fingerprint) == len(actual.registry_fingerprint) == 64
    assert actual.core_version == "structured_output_v2"


def test_transport_rejects_simultaneous_normative_and_derived(conversation):
    c = conversation
    value = NormativeToolResult(**answer_data())
    derived = c.GroundedFollowUpTransformer().repeat(value)
    with pytest.raises(ValueError):
        ChatMessage(
            type="ai",
            content=value.answer,
            normative_result=value,
            grounded_followup_result=derived,
        )


@pytest.mark.asyncio
async def test_messages_do_not_replace_private_normative_authority(conversation, tmp_path):
    from langchain_core.messages import AIMessage

    c, facade = conversation, Facade()
    who = identity(c)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "authority.sqlite")) as saver:
        graph = build(c, saver, facade)
        first = await turn(graph, who, "Qual o prazo na graduação?")
        await graph.aupdate_state(
            config(who), {"messages": [AIMessage(content="Regra inventada em 2099.")]}
        )
        final = await turn(graph, who, "Repita")
        assert final["grounded_followup_result"].content == source(first).answer
        assert "2099" not in final["grounded_followup_result"].content


@pytest.mark.asyncio
async def test_cancelled_query_does_not_replace_saved_authority(conversation, tmp_path):
    c, facade = conversation, Facade()
    who = identity(c)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "cancelled.sqlite")) as saver:
        graph = build(c, saver, facade)
        first = await turn(graph, who, "Qual o prazo?")
        facade.error = asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):
            await turn(graph, who, "Outra pergunta completa")
        facade.error = None
        final = await turn(graph, who, "Repita")
        assert (
            final["grounded_followup_result"].source_correlation_id == source(first).correlation_id
        )


@pytest.mark.asyncio
async def test_storage_identity_mismatch_is_refused_before_facade(conversation, tmp_path):
    c, facade = conversation, Facade()
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "mismatch.sqlite")) as saver:
        graph = build(c, saver, facade)
        with pytest.raises(ValueError, match="namespace"):
            await graph.ainvoke(
                {"messages": [("human", "Pergunta")], "conversation_identity": identity(c)},
                config(identity(c, user="B")),
            )
        assert not facade.calls


@pytest.mark.asyncio
async def test_pending_continuation_and_foreign_fresh_query_are_concurrent(conversation, tmp_path):
    c, facade = conversation, Facade()
    a, b = identity(c), identity(c, user="B")
    async with AsyncSqliteSaver.from_conn_string(
        str(tmp_path / "pending-concurrent.sqlite")
    ) as saver:
        graph = build(c, saver, facade)
        facade.status = "CLARIFICATION"
        pending = await turn(graph, a, "Pergunta original de A")
        facade.status = "ANSWER"
        continued, fresh = await asyncio.gather(
            turn(graph, a, "graduação"), turn(graph, b, "Nova pergunta de B")
        )
        assert (
            continued["normative_result"].correlation_id
            == pending["normative_result"].correlation_id
        )
        assert (
            fresh["normative_result"].correlation_id != pending["normative_result"].correlation_id
        )
        assert continued["conversation_memory"].last_normative_question == "Pergunta original de A"
        assert fresh["conversation_memory"].last_normative_question == "Nova pergunta de B"
        assert facade.calls[-2]["clarification"] == "graduação"
        assert facade.calls[-1]["clarification"] is None


@pytest.mark.asyncio
async def test_transient_results_are_cleared_while_memory_survives(conversation, tmp_path):
    c, facade = conversation, Facade()
    who = identity(c)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "transients.sqlite")) as saver:
        graph = build(c, saver, facade)
        first = await turn(graph, who, "Pergunta completa")
        repeated = await turn(graph, who, "Repita")
        assert repeated["normative_result"] is None
        social = await turn(graph, who, "Obrigado")
        assert social["normative_result"] is None
        assert social["grounded_followup_result"] is None
        assert social["normative_correlation_id"] == ""
        assert source(social) == source(first)
        assert social["turn_audit"].facade_calls == 0
