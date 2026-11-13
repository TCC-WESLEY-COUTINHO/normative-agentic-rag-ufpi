"""Closed deterministic actions and clarification grammar on the real integrated path."""

import pytest
from conversation_policy_fixtures import (
    ABOUT,
    EXPLICIT_POST_QUESTIONS,
    EXTERNAL,
    NEW_QUERY,
    NORMATIVE,
    Probe,
)

from rag_baseline.conversation_policy import ConversationFollowUpPolicy


@pytest.mark.parametrize(
    "question", ABOUT + ["  QUEM   É  VOCÊ?! ", " COMO você pode   me ajudar!!! "]
)
@pytest.mark.asyncio
async def test_about_has_no_normative_or_provider_side_effects(question):
    probe = Probe()
    state = await probe.send(question)
    assert probe.counts() == (0, 0, 0)
    assert not probe.scope_provider.calls
    assert state["turn_audit"].conversation_action == "ABOUT_ASSISTANT"
    assert state["normative_result"] is None and probe.pending() is None
    assert "UFPI" in state["messages"][-1].content


@pytest.mark.parametrize(
    "question", [EXTERNAL, "  QUANTOS ANOS tem a cidade mais antiga do PIAUI!!! "]
)
@pytest.mark.asyncio
async def test_external_geography_has_zero_normative_router_retrieval_provider(question):
    probe = Probe()
    probe.scope_provider.decision = "OUT_OF_SCOPE"
    state = await probe.send(question)
    assert probe.counts() == (0, 0, 0)
    assert len(probe.scope_provider.calls) == 1
    assert state["turn_audit"].conversation_action == "OUT_OF_SCOPE"
    assert "UFPI" in state["messages"][-1].content
    assert probe.pending() is None


@pytest.mark.parametrize(
    "question",
    NORMATIVE
    + [
        NEW_QUERY,
        "Você pode explicar a resolução da UFPI?",
        "quantos anos tem a cidade mais antiga do piauí e como faço matrícula na UFPI?",
        "Quais condições para mobilidade acadêmica?",
        "Como você pode me ajudar com o trancamento?",
    ],
)
@pytest.mark.asyncio
async def test_normative_queries_reach_core_and_unknown_queries_keep_router(question):
    probe = Probe()
    state = await probe.send(question)
    assert state["turn_audit"].conversation_action == "NORMATIVE_RAG"
    if question in EXPLICIT_POST_QUESTIONS:
        assert probe.counts() == (0, 1, 2)
        assert state["normative_result"].domain == "pos_graduacao"
        assert state["normative_result"].status == "ANSWER"
    else:
        assert probe.counts() == (1, 0, 1)
        assert state["normative_result"].status == "CLARIFICATION"


@pytest.mark.parametrize(
    "reply",
    [
        "graduação",
        "graduacao",
        "na graduação",
        "pós",
        "pos",
        "pós-graduação",
        "pos-graduacao",
        "na pós",
        "ambas",
        "os dois",
        "as duas",
        "  NA   PÓS?!  ",
    ],
)
@pytest.mark.asyncio
async def test_only_short_domain_replies_continue_original_operation(reply):
    probe = Probe()
    await probe.send("Posso cancelar uma disciplina?")
    pending = probe.pending()
    probe.provider.scope = "pos_graduacao"
    state = await probe.send(reply)
    assert state["turn_audit"].conversation_action == "CONTINUE_CLARIFICATION"
    assert probe.router_calls[-1]["question"] == "Posso cancelar uma disciplina?"
    assert probe.router_calls[-1]["clarification"] is not None
    assert str(state["normative_result"].correlation_id) == pending["correlation_id"]
    assert probe.pending() is None
    assert probe.counts()[1] == 1


@pytest.mark.parametrize(
    "question",
    [
        NEW_QUERY,
        "Quero cancelar uma disciplina na pós.",
        "graduação e como funciona o ajuste?",
        "não sei",
    ],
)
@pytest.mark.asyncio
async def test_non_domain_reply_starts_new_operation_without_stale_question(question):
    probe = Probe()
    await probe.send("Posso cancelar uma disciplina?")
    pending = probe.pending()
    before_router = len(probe.router_calls)
    probe.provider.scope = "pos_graduacao"
    state = await probe.send(question)
    assert state["turn_audit"].conversation_action == "NORMATIVE_RAG"
    # Router normalization may expand a standalone cue; the core original stays exact.
    assert probe.retrieval_calls[-1] == question
    if question == "não sei":
        assert probe.router_calls[-1] == dict(question=question, clarification=None)
    else:
        assert len(probe.router_calls) == before_router
    assert str(state["normative_result"].correlation_id) != pending["correlation_id"]
    assert state["conversation_memory"].last_normative_question == question
    assert probe.pending() is None


@pytest.mark.parametrize(
    "question, action",
    [("obrigado", "SAFE_DIRECT"), ("quem é você?", "ABOUT_ASSISTANT"), (EXTERNAL, "OUT_OF_SCOPE")],
)
@pytest.mark.asyncio
async def test_safe_interruptions_preserve_pending_and_allow_later_domain_reply(question, action):
    probe = Probe()
    await probe.send("Posso cancelar uma disciplina?")
    pending, before = probe.pending(), probe.counts()
    if action == "OUT_OF_SCOPE":
        probe.scope_provider.decision = "OUT_OF_SCOPE"
    state = await probe.send(question)
    assert probe.counts() == before
    assert state["turn_audit"].conversation_action == action
    assert probe.pending() == pending
    probe.scope_provider.decision = "IN_SCOPE_NORMATIVE"
    probe.provider.scope = "pos_graduacao"
    answered = await probe.send("pós")
    assert str(answered["normative_result"].correlation_id) == pending["correlation_id"]
    assert probe.pending() is None


@pytest.mark.asyncio
async def test_existing_cancel_clears_pending_without_invoking_normative_flow():
    probe = Probe()
    await probe.send("Posso cancelar uma disciplina?")
    before = probe.counts()
    state = await probe.send("cancele")
    assert state["turn_audit"].conversation_action == "CLEAR_PENDING"
    assert probe.counts() == before and probe.pending() is None
    assert state["normative_result"] is None


@pytest.mark.parametrize(
    "question, action",
    [
        ("2+2", "CALCULATOR"),
        ("repita", "GROUNDED_TRANSFORM"),
        ("e na pós?", "CONTEXTUAL_NORMATIVE_RAG"),
    ],
)
def test_other_existing_actions_keep_their_classification(question, action):
    assert ConversationFollowUpPolicy().decide(question).action == action


@pytest.mark.parametrize(
    "question, action",
    [
        ("quem é você…", "ABOUT_ASSISTANT"),
        ("quantos anos tem a cidade mais antiga do piauí…", "NORMATIVE_RAG"),
        ("graduação…", "CONTINUE_CLARIFICATION"),
    ],
)
def test_unicode_terminal_punctuation_is_normalized_before_closed_matching(question, action):
    assert ConversationFollowUpPolicy().decide(question, pending=True).action == action
