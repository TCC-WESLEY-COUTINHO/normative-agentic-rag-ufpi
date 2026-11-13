"""Indexed-corpus framing uses structured intent; temporal authority remains unchanged."""

import pytest
import test_normative_output as previous

from rag_baseline.agentic import classify_temporal_intent
from rag_baseline.service import RagService


@pytest.mark.parametrize(
    "question",
    [
        "Essa resolução ainda está vigente?",
        "Essa regra ainda vale hoje?",
        "Essa norma foi revogada?",
        "Essa norma está vigente?",
        "Essa resolução está em vigor?",
    ],
)
def test_explicit_validity_questions_share_the_existing_validity_state(question):
    assert classify_temporal_intent(question).mode == "validity"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["indeterminate", "current"])
async def test_ordinary_answer_uses_neutral_scope_without_mutating_temporal_facts(mode):
    _, chunks, grounding = previous.case("G_unknown")
    grounding = grounding.model_copy(update={"temporal_intent": mode})
    before = grounding.model_dump()
    provider = previous.SequenceClient(["O texto descreve os procedimentos de ajuste de turmas."])
    result = await RagService(
        openrouter=provider,
        vector_store=None,
        top_k=5,
        embedding_model="controlled",
        llm_model="controlled",
    ).generate("como funciona ajuste de turmas?", chunks, temporal_grounding=grounding)
    assert result.answer.startswith("Com base nas normas indexadas no sistema:")
    assert "não permite certificar a vigência atual" not in result.answer
    assert any(
        f.kind == "STATUS_UNKNOWN" for f in result.normative_output.allowed_temporal_facts.items
    )
    assert grounding.model_dump() == before
    assert result.normative_output.temporal_provenance == before


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["validity", "historical", "comparison"])
async def test_explicit_temporal_queries_keep_the_existing_uncertainty_and_roles(mode):
    _, chunks, grounding = previous.case("G_unknown")
    grounding = grounding.model_copy(update={"temporal_intent": mode})
    provider = previous.SequenceClient(["Os trechos fornecidos descrevem essa regra."])
    result = await RagService(
        openrouter=provider,
        vector_store=None,
        top_k=5,
        embedding_model="controlled",
        llm_model="controlled",
    ).generate("Consulta temporal.", chunks, temporal_grounding=grounding)
    assert "não permite certificar a vigência atual" in result.answer
    assert result.normative_output.temporal_provenance["temporal_intent"] == mode


@pytest.mark.asyncio
async def test_neutral_framing_does_not_accept_unknown_as_current():
    _, chunks, grounding = previous.case("G_unknown")
    provider = previous.SequenceClient(["A norma está vigente."] * 2)
    result = await RagService(
        openrouter=provider,
        vector_store=None,
        top_k=5,
        embedding_model="controlled",
        llm_model="controlled",
    ).generate("como funciona ajuste de turmas?", chunks, temporal_grounding=grounding)
    assert result.normative_output.status == "fallback"
    assert any(
        v.code == "unsupported_current_validity"
        for v in result.output_audit.second_guard_violations
    )


@pytest.mark.parametrize(
    "question,expected",
    [
        ("como funciona ajuste de turmas hoje?", "current"),
        ("como funciona ajuste de turmas?", "indeterminate"),
        ("ainda vale a pena fazer o curso?", "indeterminate"),
    ],
)
def test_ordinary_temporal_wording_does_not_become_validity(question, expected):
    assert classify_temporal_intent(question).mode == expected
