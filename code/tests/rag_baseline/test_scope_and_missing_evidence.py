"""Out of domain, in domain without evidence, and in domain needing clarification stay distinct."""

import json

import pytest
from conversation_policy_fixtures import Probe

from rag_baseline.conversation_policy import OUT_OF_SCOPE_RESPONSE
from rag_baseline.scope_gate import SCOPE_GATE_PROMPT, NormativeScopeGate

Q09 = "No mestrado da UFPI, qual é o valor da taxa de emissão do diploma?"
NO_EVIDENCE = "Na graduação da UFPI, como solicitar o uso do nome social no registro acadêmico?"
NEEDS_LEVEL = "Posso cancelar uma disciplina?"
ABSTENTION = "As evidências recuperadas não tratam desse assunto."


@pytest.mark.asyncio
async def test_q09_out_of_scope_decision_stops_before_router_and_retrieval():
    probe = Probe()
    probe.scope_provider.decision = "OUT_OF_SCOPE"
    state = await probe.send(Q09)
    assert state["messages"][-1].content == OUT_OF_SCOPE_RESPONSE
    assert state["turn_audit"].conversation_action == "OUT_OF_SCOPE"
    assert probe.router_calls == [] and probe.retrieval_calls == []
    assert probe.provider.prompts == []
    assert "taxa" not in state["messages"][-1].content


@pytest.mark.asyncio
async def test_gate_receives_exactly_the_question():
    probe = Probe()
    probe.scope_provider.decision = "OUT_OF_SCOPE"
    await probe.send(Q09)
    assert probe.scope_provider.calls == [{"question": Q09}]


@pytest.mark.asyncio
async def test_in_scope_question_without_evidence_reaches_retrieval_and_abstains(monkeypatch):
    from rag_baseline.service import RagService

    async def empty(self, question, **kwargs):
        return []

    # Before the probe, which keeps a reference to the method it wraps.
    monkeypatch.setattr(RagService, "retrieve", empty)
    probe = Probe()
    probe.provider.scope = "graduacao"
    state = await probe.send(NO_EVIDENCE)
    assert probe.retrieval_calls == [NO_EVIDENCE]
    result = state["normative_result"]
    assert probe.scope_provider.calls == [{"question": NO_EVIDENCE}]
    assert probe.provider.prompts == []
    assert result.references == []
    assert result.status == "ANSWER" and result.core_status == "abstained"
    assert result.error_code is None and result.safe_message is None
    assert "suficientes" in result.answer
    assert state["messages"][-1].content == result.answer


@pytest.mark.asyncio
async def test_in_scope_question_with_unrelated_evidence_keeps_the_model_abstention():
    probe = Probe()
    probe.provider.scope = "graduacao"
    probe.provider.body = ABSTENTION
    state = await probe.send(NO_EVIDENCE)
    result = state["normative_result"]
    assert probe.retrieval_calls and probe.provider.prompts
    assert result.status == "ANSWER"
    assert ABSTENTION in result.answer
    # Presence in references is not support for a claim; this is the F5 limitation.
    assert result.references


@pytest.mark.asyncio
async def test_uncertain_decision_does_not_refuse_and_goes_to_clarification():
    probe = Probe()
    probe.scope_provider.decision = "UNCERTAIN"
    probe.provider.scope = None
    state = await probe.send(NEEDS_LEVEL)
    assert state["normative_result"].status == "CLARIFICATION"
    assert probe.retrieval_calls == []


@pytest.mark.parametrize("decision", ["IN_SCOPE_NORMATIVE", "UNCERTAIN", "OUT_OF_SCOPE"])
@pytest.mark.asyncio
async def test_gate_returns_the_provider_decision_unchanged(decision):
    class Provider:
        llm_model = "fake"

        async def structured_chat(self, **kwargs):
            return json.dumps({"decision": decision})

    result = await NormativeScopeGate(Provider()).classify(Q09)
    assert result.decision == decision and result.status == "classified"


def test_gate_prompt_keeps_both_boundaries():
    assert "inclusive serviços da UFPI" in SCOPE_GATE_PROMPT
    assert "não recuse uma consulta normativa incomum" in SCOPE_GATE_PROMPT
