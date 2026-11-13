"""Candidate technical regressions, not validated legal gold.

Characterizations and the actual private-envelope generation replay are separated.
The provider boundary is controlled; filtering, grounding and guard remain real.
"""

import json

import pytest
from test_temporal_grounding import Store

from rag_baseline.agentic import AgenticRagService
from rag_baseline.models import RetrievedChunk
from rag_baseline.prompts import V2_SYSTEM_PROMPT
from rag_baseline.router import NormativeRouter
from rag_baseline.service import RagService
from rag_baseline.versioning import REGISTRY_PATH, NormativeRegistry, VersionFilter

ROOT = REGISTRY_PATH.parent.parent
TRACE = (
    ROOT
    / "evaluation/results/pre_freeze_explicit_sector_temporal_fallback_v1_001/before_traces.json"
)
RECORDED = json.loads(TRACE.read_text(encoding="utf-8"))["cases"][1]
DATASET = json.loads(
    (ROOT / "evaluation/datasets/temporal_graduacao_v1.json").read_text(encoding="utf-8")
)


class RecordedProvider:
    llm_model = "recorded-generation"

    def __init__(self, body):
        self.body, self.attempts = body, 0

    async def structured_chat(self, **kwargs):
        pytest.fail("These explicit graduação questions must not need a domain provider")

    async def embed(self, texts):
        return [[0.0]]

    async def chat(self, **kwargs):
        self.attempts += 1
        return self.body


async def replay(question, body):
    provider = RecordedProvider(body)
    chunks = [RetrievedChunk.model_validate(c) for c in RECORDED["versionfilter_input"]]
    service = RagService(
        openrouter=provider,
        vector_store=Store(chunks),
        top_k=5,
        embedding_model="recorded",
        llm_model="recorded",
        system_prompt=V2_SYSTEM_PROMPT,
    )
    result = await AgenticRagService(
        service, NormativeRouter(provider), VersionFilter(NormativeRegistry.load())
    ).query(question)
    return result, provider


@pytest.mark.asyncio
async def test_exact_case_b_recorded_generation_passes_existing_temporal_contract():
    result, provider = await replay(
        RECORDED["question"], RECORDED["generation_audit"]["raw_answer"]
    )
    assert result.normative_output.status == "accepted" and provider.attempts == 1
    assert result.output_audit.guard_violations == []
    refs = {(r.norm_id, r.article) for r in result.normative_output.references}
    assert ("ufpi-1056-2026", "1") in refs and ("ufpi-177-2012", "68") in refs
    relation = result.normative_output.temporal_provenance["known_relations"][0]
    assert (relation["source_norm"], relation["target_norm"]) == ("ufpi-177-2012", "ufpi-1056-2026")
    assert (relation["target_article"], relation["target_paragraph"]) == ("68", "4")
    permissions = result.output_audit.allowed_content_locators
    assert any(
        p.norm_id == "ufpi-177-2012"
        and p.article == "68"
        and p.subdivision_type == "paragraph"
        and p.subdivision_value == "4"
        for p in permissions
    )
    assert all(
        term in result.answer
        for term in ["programas institucionais", "edital específico", "independentemente"]
    )


@pytest.mark.parametrize("item", DATASET["items"], ids=lambda item: item["id"])
@pytest.mark.asyncio
async def test_five_temporal_candidates_keep_historical_or_amended_evidence_roles(item):
    historical = item["id"] == "TEMP-GRAD-002"
    body = (
        "Na redação histórica, o coordenador era docente efetivo escolhido entre os orientadores do estágio."
        if historical
        else "A regra geral prevê docente efetivo. A ressalva para cursos em políticas públicas ou programas "
        "institucionais com composição docente por seleção em edital específico permite designação "
        "entre os docentes selecionados, independentemente do vínculo com a UFPI. "
        "O ato alterador é a Resolução 1056/2026, art. 1. A norma-base é a Resolução 177/2012."
    )
    result, _ = await replay(item["question"], body)
    assert result.normative_output.status == "accepted", result.output_audit.guard_violations
    grounding = result.normative_output.temporal_provenance
    assert grounding["temporal_intent"] == (
        "historical"
        if historical
        else "current"
        if item["id"] in {"TEMP-GRAD-001", "TEMP-GRAD-005"}
        else "indeterminate"
    )
    assert any(e["source_norm"] == "ufpi-177-2012" for e in grounding["evidence_states"])
    if historical:
        assert all(e["temporal_role"] == "historical" for e in grounding["evidence_states"])
    else:
        assert any(e["source_norm"] == "ufpi-1056-2026" for e in grounding["evidence_states"])
    if historical:
        assert result.version_filter["insufficient_reason"] is None
        assert grounding["requested_time_context"]["historical_wording"] is True
        assert all(
            r["reason"] == "historical_incompatible"
            for r in result.version_filter["removed_references"]
        )
    else:
        assert result.version_filter["removed_references"] == []


@pytest.mark.asyncio
async def test_invalid_amending_act_locator_still_requires_fallback_after_retry():
    result, provider = await replay(
        RECORDED["question"], "A exceção está no art. 999 da Resolução 1056/2026."
    )
    assert result.normative_output.status == "fallback" and provider.attempts == 2
    assert "unallowed_article" in {v.code for v in result.output_audit.guard_violations}
    assert "unallowed_article" in {v.code for v in result.output_audit.second_guard_violations}


class RecordedValidityRetryProvider(RecordedProvider):
    def __init__(self, *, repeat_invalid=False):
        super().__init__(RECORDED["generation_audit"]["raw_answer"])
        path = TRACE.parent / "manual_case_b_private_audit.json"
        manual = json.loads(path.read_text(encoding="utf-8"))["relevant_cases"][0]
        self.failed = manual["matching_private_envelope_audit"]["output_audit"]
        self.repeat_invalid, self.repair = repeat_invalid, None

    async def chat(self, **kwargs):
        self.attempts += 1
        if self.attempts == 1:
            return self.failed["raw_answer"]
        prompt = kwargs["user_prompt"]
        if "[REGENERATION CONSTRAINTS]" in prompt:
            self.repair = json.loads(
                prompt.split("[REGENERATION CONSTRAINTS]", 1)[1].split(
                    "[/REGENERATION CONSTRAINTS]", 1
                )[0]
            )
        # Replay the observed invalid retry unless the caller provides the
        # violation-specific repair contract, rather than only a list of errors.
        if (
            self.repeat_invalid
            or not self.repair
            or self.repair.get("must_not_claim_current_validity") is not True
            or self.repair.get("must_preserve_supported_substantive_content") is not True
            or self.repair.get("documented_relation_does_not_certify_current_validity") is not True
            or self.repair.get("remove_unsupported_excerpts") != ["permanece em vigor"]
        ):
            return self.failed["regenerated_answer"]
        return self.body


async def replay_manual_failure(provider):
    chunks = [RetrievedChunk.model_validate(c) for c in RECORDED["versionfilter_input"]]
    service = RagService(
        openrouter=provider,
        vector_store=Store(chunks),
        top_k=5,
        embedding_model="recorded",
        llm_model="recorded",
        system_prompt=V2_SYSTEM_PROMPT,
    )
    return await AgenticRagService(
        service, NormativeRouter(provider), VersionFilter(NormativeRegistry.load())
    ).query(RECORDED["question"])


@pytest.mark.asyncio
async def test_manual_unsupported_validity_retry_repairs_claim_and_preserves_exception():
    provider = RecordedValidityRetryProvider()
    result = await replay_manual_failure(provider)
    assert result.normative_output.status == "regenerated"
    assert provider.attempts == 2
    assert [v.code for v in result.output_audit.guard_violations] == [
        "unsupported_current_validity"
    ]
    assert result.output_audit.second_guard_violations == []
    assert all(
        term in result.answer
        for term in ["programas institucionais", "edital específico", "independentemente"]
    )
    assert {(r.norm_id, r.article) for r in result.normative_output.references} >= {
        ("ufpi-1056-2026", "1"),
        ("ufpi-177-2012", "68"),
    }


@pytest.mark.asyncio
async def test_manual_retry_that_still_claims_validity_remains_blocked():
    provider = RecordedValidityRetryProvider(repeat_invalid=True)
    result = await replay_manual_failure(provider)
    assert result.normative_output.status == "fallback" and provider.attempts == 2
    assert [v.code for v in result.output_audit.second_guard_violations] == [
        "unsupported_current_validity"
    ]


class RecordedLocatorRetryProvider(RecordedValidityRetryProvider):
    async def chat(self, **kwargs):
        body = await super().chat(**kwargs)
        if self.attempts == 1:
            return body
        if (
            self.repair
            and self.repair.get("must_omit_body_citations") is True
            and self.repair.get("must_leave_temporal_relation_to_application") is True
        ):
            return (
                "A regra geral prevê docente efetivo. A ressalva permite designar um docente "
                "selecionado para o curso, independentemente de seu vínculo com a UFPI, "
                "quando o curso integra as políticas públicas ou programas institucionais "
                "previstos e seu corpo docente é composto por seleção em edital específico."
            )
        trace = json.loads((TRACE.parent / "live_retry_trace.json").read_text(encoding="utf-8"))
        return trace["cases"][0]["generation_audit"]["regenerated_answer"]


@pytest.mark.asyncio
async def test_validity_repair_does_not_introduce_ambiguous_amendment_locators():
    from rag_baseline.content_locators import locator_mentions

    provider = RecordedLocatorRetryProvider()
    result = await replay_manual_failure(provider)
    assert result.normative_output.status == "regenerated"
    assert result.output_audit.second_guard_violations == []
    assert locator_mentions(result.output_audit.regenerated_answer) == []
    assert {r.norm_id for r in result.normative_output.references} == {
        "ufpi-1056-2026",
        "ufpi-177-2012",
    }
    assert "regra geral" in result.answer and "edital específico" in result.answer
