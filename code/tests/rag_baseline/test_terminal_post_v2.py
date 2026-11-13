"""High precision terminal postgraduate noun phrases and clean conversational sequence."""

import pytest
import test_pre_freeze_defects as previous

from rag_baseline.routing_normalization import routing_question

registry = previous.registry
runtime = previous.runtime
integrated = previous.integrated
POSITIVE = [
    "como trancar a pós",
    "como funciona a pós?",
    "quero fazer a pós",
    "posso trancar a pós?",
]
NEGATIVE = [
    "regra pós-alteração",
    "pós-2025",
    "efeito pós recurso",
    "situação pós defesa",
    "como trancar a pós-alteração",
    "como funciona a pós defesa",
]


@pytest.mark.parametrize("question", POSITIVE)
def test_terminal_post_noun_phrase_is_canonicalized(question):
    assert routing_question(question) == question.replace("pós", "pós-graduação")


@pytest.mark.parametrize("question", NEGATIVE)
def test_temporal_post_is_not_a_postgraduate_cue(question):
    assert routing_question(question) == question


@pytest.mark.asyncio
async def test_trancar_post_then_ira_is_a_new_post_question_without_pending(integrated):
    turn, provider, _ = integrated
    provider.scopes["como trancar a pós-graduação"] = "pos_graduacao"
    provider.scopes["precisa de ira pra passar na pós-graduação"] = "pos_graduacao"
    first = await turn("como trancar a pós")
    assert first["normative_result"].status == "ANSWER"
    assert first["normative_result"].domain == "pos_graduacao"
    assert first["conversation_memory"].pending_clarification is None
    second = await turn("precisa de ira pra passar na pós")
    assert second["normative_result"].status == "ANSWER"
    assert second["normative_result"].domain == "pos_graduacao"
    assert second["conversation_memory"].pending_clarification is None
    assert second["turn_audit"].conversation_action == "NORMATIVE_RAG"
    assert (
        second["conversation_memory"].last_normative_question == "precisa de ira pra passar na pós"
    )
    assert provider.routes == []
    assert first["normative_result"].correlation_id != second["normative_result"].correlation_id


@pytest.mark.asyncio
async def test_router_input_makes_explicit_level_take_priority_over_implicit_terms():
    import json

    from rag_baseline.router import NormativeRouter

    class Recorder:
        llm_model = "controlled"
        payload = None

        async def structured_chat(self, **payload):
            self.payload = payload
            return json.dumps(
                dict(
                    scope="pos_graduacao",
                    needs_clarification=False,
                    clarification_question=None,
                    reason_code="explicit_pos",
                )
            )

    provider = Recorder()
    await NormativeRouter(provider).route("precisa de ira pra passar na pós-graduação")
    assert "O nível explícito prevalece sobre pistas temáticas" in provider.payload["system_prompt"]
    assert "somente na ausência de nível explícito" in provider.payload["system_prompt"]
