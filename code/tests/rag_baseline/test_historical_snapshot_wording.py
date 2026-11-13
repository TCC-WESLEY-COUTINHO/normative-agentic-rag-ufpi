"""Document wording is not calendar-date legal validity; candidate regressions only."""

import json

import pytest
from test_temporal_grounding import Store, chunk

from rag_baseline.agentic import AgenticRagService, classify_temporal_intent
from rag_baseline.prompts import V2_SYSTEM_PROMPT
from rag_baseline.router import NormativeRouter
from rag_baseline.service import RagService
from rag_baseline.versioning import REGISTRY_PATH, NormativeRegistry, VersionFilter

DATA = json.loads(
    (REGISTRY_PATH.parent.parent / "evaluation/datasets/temporal_graduacao_v1.json").read_text(
        encoding="utf-8"
    )
)
EXACT = DATA["items"][1]["question"]
HISTORICAL_BODY = (
    "No texto histórico do regulamento, o coordenador de estágio era docente efetivo "
    "escolhido entre os professores orientadores do estágio, designado por portaria da "
    "unidade acadêmica quando o colegiado entendesse necessária a coordenação. "
    "A ressalva de programas institucionais e vínculo pertence à alteração posterior."
)


class Provider:
    llm_model = "controlled-boundary"

    def __init__(self, body):
        self.body, self.payloads = body, []

    async def embed(self, texts):
        return [[0.0]]

    async def structured_chat(self, **kwargs):
        pytest.fail("Explicit graduation or manual scope must not require Router inference")

    async def chat(self, **kwargs):
        self.payloads.append(kwargs)
        return self.body


async def query(question, body=HISTORICAL_BODY):
    provider = Provider(body)
    service = RagService(
        openrouter=provider,
        vector_store=Store([chunk("177-2012", "68"), chunk("1056-2026", "1", 2)]),
        top_k=5,
        embedding_model="test",
        llm_model="test",
        system_prompt=V2_SYSTEM_PROMPT,
    )
    result = await AgenticRagService(
        service, NormativeRouter(provider), VersionFilter(NormativeRegistry.load())
    ).query(question, scope="graduacao")
    return result, provider


@pytest.mark.asyncio
async def test_temp_grad_002_keeps_snapshot_text_and_generates_without_calendar_certification():
    result, provider = await query(EXACT)
    assert result.version_filter["insufficient_reason"] is None
    assert result.normative_output.status == "accepted"
    assert result.generation_attempts == 1
    assert {r.norm_id for r in result.normative_output.references} == {"ufpi-177-2012"}
    assert result.references[0].content == chunk("177-2012", "68").content
    grounding = result.normative_output.temporal_provenance
    assert grounding["temporal_intent"] == "historical"
    assert grounding["requested_time_context"]["requested_year"] is None
    assert grounding["requested_time_context"]["document_year"] == 2023
    assert grounding["requested_time_context"]["historical_wording"] is True
    assert grounding["generation_constraints"]["must_not_claim_current_validity"]
    assert all(e["temporal_role"] == "historical" for e in grounding["evidence_states"])
    assert "independentemente de seu vínculo" not in provider.payloads[0]["user_prompt"]
    assert "docente efetivo" in result.answer and "portaria" in result.answer
    assert "ressalva" in result.answer and "posterior" in result.answer


@pytest.mark.parametrize(
    "question,document_year",
    [
        (EXACT, 2023),
        (
            "Como era a redação do art. 68 antes da alteração feita em 2026?",
            None,
        ),
        ("Qual era o texto da versão de 2021 antes da alteração?", 2021),
        ("Como era a redação no regulamento atualizado em 2022?", 2022),
    ],
)
def test_wording_moves_document_year_out_of_calendar_validity(question, document_year):
    intent = classify_temporal_intent(question)
    assert intent.needs_history
    assert intent.requested_year is None
    assert intent.model_dump().get("historical_wording") is True
    assert intent.model_dump().get("document_year") == document_year


@pytest.mark.parametrize(
    "question",
    [
        "Essa resolução estava vigente em 2023?",
        "Qual regra valia em 2023?",
        "Qual era a reda\u00e7\u00e3o v\u00e1lida em 2023?",
        "Qual texto do regulamento se aplicou em 2023?",
        "Qual era a reda\u00e7\u00e3o que valeu em 2023?",
        "Qual era a vers\u00e3o com for\u00e7a de lei em 2023?",
        "Qual era o texto da vers\u00e3o de 2023 que se aplicou em 2023?",
        "Qual era a reda\u00e7\u00e3o v\u00e1lida no regulamento atualizado em 2023, antes da altera\u00e7\u00e3o?",
        "Qual norma estava vigente em 2023?",
        "A redação do regulamento atualizado em 2023 estava vigente em 2023?",
        "A redação da versão de 2023 era aplicável em 2023?",
    ],
)
@pytest.mark.asyncio
async def test_calendar_validity_still_requires_chronology(question):
    result, provider = await query(question)
    assert result.version_filter["temporal_intent"]["requested_year"] == 2023
    assert not result.version_filter["temporal_intent"].get("historical_wording", False)
    assert result.version_filter["insufficient_reason"] == "chronology_unresolved"
    assert not result.references and not provider.payloads


@pytest.mark.asyncio
async def test_snapshot_without_document_year_keeps_historical_text():
    result, _ = await query("Como era a redação do art. 68, §4º antes da alteração feita em 2026?")
    assert result.normative_output.status == "accepted"
    assert result.version_filter["temporal_intent"]["requested_year"] is None
    assert {r.norm_id for r in result.normative_output.references} == {"ufpi-177-2012"}


@pytest.mark.asyncio
async def test_current_wording_still_applies_amendment():
    result, provider = await query(
        "Qual é a redação atual do art. 68, §4º?",
        "A regra geral prevê docente efetivo; a ressalva dos cursos e seleção previstos permite docentes selecionados independentemente do vínculo.",
    )
    assert result.normative_output.status == "accepted"
    assert result.version_filter["amended_references"]
    assert "independentemente de seu vínculo" in provider.payloads[0]["user_prompt"]
    assert not result.version_filter["temporal_intent"].get("historical_wording", False)


@pytest.mark.parametrize(
    "body,code",
    [
        ("A norma entrou em vigor em 2023.", "unsupported_effectivity"),
        ("A norma está vigente.", "unsupported_current_validity"),
        ("A regra tem efeitos desde 2023.", "unsupported_chronology"),
        ("A regra consta do art. 999 da Resolução 177/2012.", "unallowed_article"),
    ],
)
@pytest.mark.asyncio
async def test_snapshot_does_not_authorize_temporal_or_locator_claims(body, code):
    result, _ = await query(EXACT, body)
    assert result.normative_output.status == "fallback"
    assert code in {v.code for v in result.output_audit.second_guard_violations}


@pytest.mark.parametrize(
    "body",
    [
        "Essa reda\u00e7\u00e3o estava em vigor no contexto documental de 2023.",
        "A norma-base permaneceu vigente em parte.",
        "A regra vigorava em 2023.",
        "O regulamento vigente antes da altera\u00e7\u00e3o previa docente efetivo.",
        "A reda\u00e7\u00e3o v\u00e1lida em 2023 previa docente efetivo.",
        "Essa regra aplicava-se em 2023.",
    ],
)
@pytest.mark.asyncio
async def test_document_wording_cannot_certify_historical_validity(body):
    result, _ = await query(EXACT, body)
    assert result.normative_output.status == "fallback"
    assert "unsupported_historical_validity" in {
        v.code for v in result.output_audit.second_guard_violations
    }


@pytest.mark.asyncio
async def test_actual_local_retry_cannot_turn_snapshot_into_validity_certification():
    path = (
        REGISTRY_PATH.parent.parent
        / "evaluation/results/pre_freeze_historical_snapshot_local_runtime_v1_001/local_smokes.json"
    )
    record = json.loads(path.read_text(encoding="utf-8"))["cases"][-1]
    result, _ = await query(EXACT, record["generation_audit"]["regenerated_answer"])
    assert result.normative_output.status == "fallback"
    assert "unsupported_historical_validity" in {
        v.code for v in result.output_audit.guard_violations
    }


@pytest.mark.asyncio
async def test_document_wording_can_deny_certifying_past_validity():
    result, _ = await query(
        EXACT,
        HISTORICAL_BODY + " N\u00e3o \u00e9 poss\u00edvel afirmar que estava em vigor em 2023.",
    )
    assert result.normative_output.status == "accepted"


class HistoricalRepairProvider(Provider):
    async def chat(self, **kwargs):
        self.payloads.append(kwargs)
        return (
            "Essa reda\u00e7\u00e3o estava em vigor em 2023."
            if len(self.payloads) == 1
            else HISTORICAL_BODY
        )


@pytest.mark.asyncio
async def test_historical_validity_retry_preserves_wording_without_certification():
    provider = HistoricalRepairProvider(HISTORICAL_BODY)
    service = RagService(
        openrouter=provider,
        vector_store=Store([chunk("177-2012", "68")]),
        top_k=5,
        embedding_model="test",
        llm_model="test",
        system_prompt=V2_SYSTEM_PROMPT,
    )
    result = await AgenticRagService(
        service, NormativeRouter(provider), VersionFilter(NormativeRegistry.load())
    ).query(EXACT, scope="graduacao")
    assert result.normative_output.status == "regenerated"
    assert result.output_audit.second_guard_violations == []
    assert "docente efetivo" in result.answer and "portaria" in result.answer
    repair = json.loads(
        provider.payloads[1]["user_prompt"]
        .split("[REGENERATION CONSTRAINTS]", 1)[1]
        .split("[/REGENERATION CONSTRAINTS]", 1)[0]
    )
    assert repair["must_not_claim_historical_validity"] is True
    assert {r.norm_id for r in result.normative_output.references} == {"ufpi-177-2012"}


class RecordedCitationThenValidityProvider(Provider):
    def __init__(self, first_article="68"):
        super().__init__(HISTORICAL_BODY)
        self.first_article = first_article
        path = (
            REGISTRY_PATH.parent.parent
            / "evaluation/results/pre_freeze_historical_snapshot_local_runtime_v1_001/local_smokes_final.json"
        )
        self.record = json.loads(path.read_text(encoding="utf-8"))["cases"][-1]["generation_audit"]

    async def chat(self, **kwargs):
        self.payloads.append(kwargs)
        if len(self.payloads) == 1:
            return self.record["raw_answer"].replace(
                "art. 68, parágrafo 4", f"art. {self.first_article}, parágrafo 4"
            )
        prompt = kwargs["user_prompt"]
        if "[REGENERATION CONSTRAINTS]" in prompt:
            repair = json.loads(
                prompt.split("[REGENERATION CONSTRAINTS]", 1)[1].split(
                    "[/REGENERATION CONSTRAINTS]", 1
                )[0]
            )
            if repair.get("must_not_claim_historical_validity") and repair.get(
                "must_omit_body_citations"
            ):
                return HISTORICAL_BODY
        return self.record["regenerated_answer"]


@pytest.mark.asyncio
async def test_recorded_amendment_sentence_is_not_a_locator_error():
    provider = RecordedCitationThenValidityProvider()
    service = RagService(
        openrouter=provider,
        vector_store=Store([chunk("177-2012", "68")]),
        top_k=5,
        embedding_model="test",
        llm_model="test",
        system_prompt=V2_SYSTEM_PROMPT,
    )
    result = await AgenticRagService(
        service, NormativeRouter(provider), VersionFilter(NormativeRegistry.load())
    ).query(EXACT, scope="graduacao")
    assert (
        "art. 68, parágrafo 4, e foi alterada pela Resolução 1056/2026"
        in (provider.record["raw_answer"])
    )
    assert result.output_audit.guard_violations == []
    assert result.normative_output.status == "accepted"
    assert len(provider.payloads) == 1


@pytest.mark.asyncio
async def test_snapshot_retry_keeps_entire_wording_contract_after_locator_error():
    provider = RecordedCitationThenValidityProvider(first_article="69")
    service = RagService(
        openrouter=provider,
        vector_store=Store([chunk("177-2012", "68")]),
        top_k=5,
        embedding_model="test",
        llm_model="test",
        system_prompt=V2_SYSTEM_PROMPT,
    )
    result = await AgenticRagService(
        service, NormativeRouter(provider), VersionFilter(NormativeRegistry.load())
    ).query(EXACT, scope="graduacao")
    assert {v.code for v in result.output_audit.guard_violations} == {
        "unallowed_article",
        "unvalidated_subdivision",
    }
    assert "art. 69" in {v.excerpt for v in result.output_audit.guard_violations}
    assert {r.article for r in result.normative_output.references} == {"68"}
    assert len(provider.payloads) == 2
    prompt = provider.payloads[1]["user_prompt"]
    repair = json.loads(
        prompt.split("[REGENERATION CONSTRAINTS]", 1)[1].split("[/REGENERATION CONSTRAINTS]", 1)[0]
    )
    assert repair["must_not_claim_current_validity"] is True
    assert repair["must_not_claim_historical_validity"] is True
    assert repair["must_preserve_supported_substantive_content"] is True
    assert repair["must_omit_body_citations"] is True
    assert "REDAÇÃO DOCUMENTAL" in prompt
    assert result.normative_output.status == "regenerated"
    assert result.output_audit.second_guard_violations == []
    assert "docente efetivo" in result.answer and "portaria" in result.answer
