"""Deterministic temporal boundaries, with controlled model output. No provider and no rates."""

import pytest
from test_historical_snapshot_wording import EXACT, query
from test_normative_output import codes
from test_temporal_grounding import Store, chunk

from rag_baseline.agentic import AgenticRagService, classify_temporal_intent
from rag_baseline.prompts import V2_SYSTEM_PROMPT
from rag_baseline.router import NormativeRouter
from rag_baseline.service import RagService
from rag_baseline.versioning import NormativeRegistry, VersionFilter


class Provider:
    llm_model = "controlled"

    def __init__(self, body):
        self.body, self.payloads = body, []

    async def embed(self, texts):
        return [[0.0]]

    async def structured_chat(self, **kwargs):
        pytest.fail("A manual scope must not require the Router")

    async def chat(self, **kwargs):
        self.payloads.append(kwargs)
        return self.body


async def ask(question, chunks, scope, body="Conteúdo controlado."):
    provider = Provider(body)
    service = RagService(
        openrouter=provider,
        vector_store=Store(chunks),
        top_k=5,
        embedding_model="test",
        llm_model="test",
        system_prompt=V2_SYSTEM_PROMPT,
    )
    result = await AgenticRagService(
        service, NormativeRouter(provider), VersionFilter(NormativeRegistry.load())
    ).query(question, scope=scope)
    return result, provider


def test_temp_grad_002_state_is_preserved():
    intent = classify_temporal_intent(EXACT, registry=NormativeRegistry.load())
    assert intent.mode == "historical"
    assert intent.before_amendment is True
    assert intent.historical_wording is True
    assert intent.document_year == 2023
    assert intent.requested_year is None


@pytest.mark.parametrize(
    "body",
    [
        "A Resolução 177/2012 está vigente.",
        "Esta é a redação vigente do dispositivo.",
    ],
)
@pytest.mark.asyncio
async def test_undue_validity_claim_never_reaches_the_answer(body):
    result, provider = await query(EXACT, body)
    assert result.normative_output.status == "fallback"
    assert len(provider.payloads) == 2
    assert body not in result.answer


@pytest.mark.asyncio
async def test_wrong_article_is_not_attributed_to_the_norm():
    result, _ = await query(EXACT, "A regra consta do art. 999 da Resolução 177/2012.")
    assert result.normative_output.status == "fallback"
    assert "unallowed_article" in {v.code for v in result.output_audit.guard_violations}
    assert "art. 999" not in result.answer


@pytest.mark.asyncio
async def test_historical_question_keeps_the_previous_wording_and_labels_it():
    result, provider = await query(EXACT)
    prompt = provider.payloads[0]["user_prompt"]
    evidence = prompt.split("PERGUNTA:")[0]
    assert "docente efetivo escolhido entre os professores orientadores" in evidence
    assert "independentemente de seu vínculo" not in evidence
    assert result.normative_output.status == "accepted"
    assert {r.norm_id for r in result.normative_output.references} == {"ufpi-177-2012"}
    assert "redação histórica" in result.answer
    assert "não certifica sua vigência atual" in result.answer


@pytest.mark.asyncio
async def test_current_question_uses_the_amended_wording():
    result, provider = await query(
        "Qual é a regra vigente do art. 68, §4º da Resolução 177/2012?",
        "O coordenador pode ser designado conforme o edital específico.",
    )
    evidence = provider.payloads[0]["user_prompt"].split("PERGUNTA:")[0]
    assert "independentemente de seu vínculo" in evidence
    assert "REDAÇÃO APLICÁVEL" in evidence
    assert result.version_filter["amended_references"]
    assert result.normative_output.status == "accepted"
    assert "ufpi-177-2012" in {r.norm_id for r in result.normative_output.references}
    assert "O coordenador pode ser designado conforme o edital específico." in result.answer


@pytest.mark.parametrize(
    "question,mode",
    [
        (EXACT, "document"),
        ("A redação da versão de 2023 era aplicável em 2023?", "calendar"),
    ],
)
def test_document_year_is_not_applicability(question, mode):
    intent = classify_temporal_intent(question, registry=NormativeRegistry.load())
    if mode == "document":
        assert intent.document_year == 2023 and intent.requested_year is None
    else:
        assert intent.requested_year == 2023 and not intent.historical_wording


@pytest.mark.asyncio
async def test_calendar_applicability_without_evidence_does_not_generate():
    result, provider = await query("A redação da versão de 2023 era aplicável em 2023?")
    assert result.version_filter["insufficient_reason"] == "chronology_unresolved"
    assert not result.references and not provider.payloads
    assert result.generation_attempts == 0


@pytest.mark.parametrize(
    "body",
    [
        "A Resolução 658/2024 está vigente.",
        "A Resolução 658/2024 continua em vigor na pós-graduação.",
    ],
)
def test_revoked_norm_presented_as_current_is_detected(body):
    assert codes(body) & {
        "unsupported_current_validity",
        "unsupported_effectivity",
        "temporal_contradiction",
    }


@pytest.mark.asyncio
async def test_revoked_norm_as_current_does_not_reach_the_answer():
    body = "A Resolução 658/2024 está vigente."
    result, _ = await ask(
        "Segundo a Resolução 658/2024, como era a regra de defesa no mestrado?",
        [chunk("658-2024", "43")],
        "pos_graduacao",
        body,
    )
    assert result.normative_output.status == "fallback"
    assert body not in result.answer


@pytest.mark.asyncio
async def test_comparison_with_one_side_missing_does_not_generate():
    result, provider = await ask(
        "Qual era a regra de defesa na 658/2024 e qual é a regra atual na 956/2025 no mestrado?",
        [chunk("956-2025", "53")],
        "pos_graduacao",
    )
    assert result.version_filter["insufficient_reason"] == "comparison_evidence_missing"
    assert not provider.payloads and not result.references
