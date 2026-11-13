"""Structured presentation contracts; fixed previous outputs, never provider calls."""

import json
from pathlib import Path

import pytest

from rag_baseline.grounding import TemporalGroundingContext, build_temporal_grounding
from rag_baseline.models import RetrievedChunk
from rag_baseline.service import RagService
from rag_baseline.versioning import NormativeRegistry, VersionAudit

ROOT = Path(__file__).resolve().parents[3]
PREVIOUS = ROOT / "evaluation/results/temporal_generation_grounding_v1_001"


def case(case_id="E_validity"):
    item = next(
        c
        for c in json.loads((PREVIOUS / "frozen_contexts.json").read_text("utf-8"))
        if c["id"] == case_id
    )
    chunks = [RetrievedChunk.model_validate(c) for c in item["raw_context"]]
    grounding = build_temporal_grounding(
        chunks, VersionAudit.model_validate(item["temporal_state"]), NormativeRegistry.load()
    )
    return item, chunks, grounding


def output_parts(case_id="E_validity"):
    from rag_baseline.normative_output import allowed_temporal_facts, normative_references

    _, chunks, grounding = case(case_id)
    return grounding, normative_references(chunks, grounding), allowed_temporal_facts(grounding)


def guard(text, case_id="E_validity"):
    from rag_baseline.normative_output import NormativeOutputGuard

    grounding, refs, facts = output_parts(case_id)
    return NormativeOutputGuard().check(text, refs, facts, grounding)


def codes(text, case_id="E_validity"):
    return {v.code for v in guard(text, case_id)}


def test_reference_display_never_promotes_internal_relation_locator():
    grounding, refs, _ = output_parts()
    assert grounding.known_relations[0].evidence_article == "62, VI"
    ref = next(r for r in refs if r.article == "62")
    assert ref.display_text == "Resolução 956/2025, art. 62"
    assert ref.validated_subdivision is None
    assert "VI" not in ref.display_text and "content" not in ref.model_dump()


def test_only_final_evidence_can_be_displayed_and_mismatch_fails_closed():
    from rag_baseline.normative_output import normative_references

    _, chunks, grounding = case()
    assert {r.chunk_id for r in normative_references(chunks, grounding)} == {c.id for c in chunks}
    _, removed, _ = case("C_post_historical")
    with pytest.raises(ValueError, match="final"):
        normative_references(chunks + removed[:1], grounding)


def test_historical_references_are_allowed_ordered_and_equivalents_use_lowest_rank():
    from rag_baseline.normative_output import normative_references

    _, chunks, grounding = case("C_post_historical")
    expected = normative_references(chunks, grounding)
    assert all(r.temporal_role == "historical" for r in expected)
    assert normative_references(list(reversed(chunks)), grounding) == expected
    duplicate = chunks[0].model_copy(update={"id": "duplicate", "rank": 99})
    state = grounding.evidence_states[0].model_copy(update={"chunk_id": "duplicate"})
    expanded = grounding.model_copy(update={"evidence_states": grounding.evidence_states + [state]})
    assert normative_references([duplicate, *chunks], expanded) == expected


def test_source_ceiling_hides_article_and_unvalidated_paragraph():
    from rag_baseline.normative_output import normative_references

    _, chunks, grounding = case("A_grad_historical")
    refs = normative_references(chunks, grounding)
    assert all("§" not in r.display_text for r in refs)
    constraints = grounding.generation_constraints.model_copy(
        update={"citation_granularity_ceiling": "source"}
    )
    refs = normative_references(
        chunks, grounding.model_copy(update={"generation_constraints": constraints})
    )
    assert all(r.article is None and "art." not in r.display_text for r in refs)


@pytest.mark.parametrize(
    "case_id, required, forbidden",
    [
        ("A_grad_historical", "redação histórica", "está vigente"),
        ("E_validity", "Resolução 658/2024 foi revogada por Resolução 956/2025", "publicada"),
        ("B_grad_current", "alteração parcial", "revogada"),
        ("G_unknown", "não permite certificar a vigência atual", "desde 2025"),
        ("F_comparison", "Papel histórico: Resolução 658/2024", "entrou em vigor"),
    ],
)
def test_temporal_renderer_uses_structural_facts(case_id, required, forbidden):
    from rag_baseline.normative_output import render_temporal_statements

    _, _, facts = output_parts(case_id)
    text = render_temporal_statements(facts)
    assert required in text and forbidden not in text
    if case_id == "F_comparison":
        assert "Papel posterior: Resolução 956/2025" in text
    assert all(
        f.kind not in {"PUBLICATION_DATE", "EFFECTIVE_DATE", "RETROACTIVITY"} for f in facts.items
    )


@pytest.mark.parametrize(
    "text",
    [
        "A defesa deve ser divulgada com a antecedência indicada no texto.",
        "Resolução 956/2025, art. 62.",
        "A Resolução 658/2024 foi revogada pela Resolução 956/2025.",
        "Não é possível certificar a vigência atual da norma.",
    ],
)
def test_guard_accepts_allowed_content_without_llm(text):
    assert guard(text) == []


@pytest.mark.parametrize(
    "text, code",
    [
        ("Fonte: art. 62, §1º.", "unvalidated_subdivision"),
        ("Art. 62, inciso VI.", "unvalidated_subdivision"),
        ("Art. 62, VI.", "unvalidated_subdivision"),
        ("Art. 62, alínea a.", "unvalidated_subdivision"),
        ("Segundo o artigo 999.", "unallowed_article"),
        ("A Resolução 999/2025 determina isso.", "unallowed_norm"),
        ("A resolução entrou em vigor em 2025.", "unsupported_effectivity"),
        ("A norma foi publicada em 2025.", "unsupported_publication"),
        ("A norma vigora desde 2025.", "unsupported_effectivity"),
        ("A regra é aplicável a partir de 2025.", "unsupported_chronology"),
        ("A regra é retroativa.", "unsupported_retroactivity"),
        ("A norma está vigente.", "unsupported_current_validity"),
        ("A redação vigente, após a alteração, é a seguinte:", "unsupported_current_validity"),
        ("A Resolução 956/2025 foi revogada pela Resolução 658/2024.", "contradictory_relation"),
    ],
)
def test_guard_detects_observed_violation_classes_and_preserves_raw(text, code):
    raw = text
    violations = guard(text)
    assert code in {v.code for v in violations}
    assert text == raw and all(raw[v.start : v.end] == v.excerpt for v in violations)


def test_guard_checks_norm_article_pairs_and_contextual_year_is_not_effectivity():
    assert "unallowed_article" in codes("Resolução 658/2024, art. 62.")
    assert (
        guard(
            "Antes da alteração de 2026, a escolha era feita conforme o regulamento.",
            "A_grad_historical",
        )
        == []
    )
    assert guard("A Resolução 177/2012 trata da graduação.", "A_grad_historical") == []


def test_guard_detects_total_repeal_of_partially_amended_base():
    assert "contradictory_relation" in codes(
        "A Resolução 177/2012 foi revogada pela Resolução 1056/2026.", "B_grad_current"
    )


@pytest.mark.parametrize(
    "text, case_id, code",
    [
        (
            "Não há dúvida de que a norma foi publicada em 2025.",
            "E_validity",
            "unsupported_publication",
        ),
        (
            "Não apenas a Resolução 658/2024, mas a Resolução 956/2025 entrou em vigor em 2025.",
            "E_validity",
            "unsupported_effectivity",
        ),
        ("A Resolução 177/2012 foi revogada.", "B_grad_current", "contradictory_relation"),
        ("Artigos 62 e 999 da Resolução 956/2025.", "E_validity", "unallowed_article"),
        ("A norma tem vigência atual.", "G_unknown", "unsupported_current_validity"),
    ],
)
def test_review_regressions_for_explicit_affirmative_claims(text, case_id, code):
    assert code in codes(text, case_id)


@pytest.mark.parametrize(
    "text",
    [
        "A norma não está vigente.",
        "Não há evidência de que a norma foi publicada em 2025.",
        "Não é possível afirmar que a norma entrou em vigor em 2025.",
    ],
)
def test_explicit_negative_claims_are_not_treated_as_affirmative(text):
    assert guard(text) == []


def test_publication_of_academic_work_is_not_normative_chronology():
    assert (
        guard(
            "É necessário ter publicado artigos científicos originados do projeto de dissertação.",
            "H_citation",
        )
        == []
    )


def test_negative_previous_clause_does_not_excuse_affirmative_current_claim():
    assert "unsupported_current_validity" in codes(
        "Não foi possível confirmar o ato posterior, mas a norma está vigente.", "G_unknown"
    )


@pytest.mark.parametrize(
    "text, case_id",
    [
        ("A norma não foi publicada em 2025.", "E_validity"),
        ("A Resolução 177/2012 não foi revogada.", "B_grad_current"),
        (
            "A norma exige ter publicado artigos científicos originados do projeto de dissertação.",
            "H_citation",
        ),
        ("A Resolução 1.056/2026 altera o regulamento.", "B_grad_current"),
        (
            "Antes da alteração da Resolução 1.056/2026, o Art. 68 do regulamento (Resolução 177/2012) previa essa regra.",
            "A_grad_historical",
        ),
    ],
)
def test_bounded_false_positive_regressions(text, case_id):
    assert guard(text, case_id) == []


@pytest.mark.parametrize(
    "repetition, category",
    [
        (2, "unsupported_effectivity"),
        (8, "unsupported_effectivity"),
        (4, "unsupported_publication"),
        (10, "unsupported_publication"),
    ],
)
def test_saved_after_chronology_failures_are_detected(repetition, category):
    rows = [json.loads(line) for line in (PREVIOUS / "after.jsonl").read_text("utf-8").splitlines()]
    row = next(r for r in rows if r["id"] == "E_validity" and r["repetition"] == repetition)
    assert category in codes(row["raw_answer"])


class SequenceClient:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.calls = []

    async def chat(self, **payload):
        self.calls.append(payload)
        return next(self.answers)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answers, action, attempts",
    [
        (["A defesa deve ser divulgada com a antecedência prevista."], "accepted", 1),
        (
            [
                "Fonte: art. 53, §9º.",
                "A defesa deve ser divulgada com a antecedência prevista.",
            ],
            "regenerated",
            2,
        ),
        (["Fonte: art. 53, §9º.", "Fonte: art. 53, §9º."], "fallback", 2),
    ],
)
async def test_service_bounded_policy_keeps_context_and_raw_trace(answers, action, attempts):
    item, chunks, grounding = case("H_citation")
    remote = SequenceClient(answers)
    service = RagService(
        openrouter=remote, vector_store=None, top_k=5, embedding_model="test", llm_model="test"
    )
    result = await service.generate(item["question"], chunks, temporal_grounding=grounding)
    assert len(remote.calls) == result.generation_attempts == attempts
    assert result.output_audit.raw_answer == answers[0]
    assert result.output_audit.guard_action == action
    assert result.output_audit.final_answer == result.answer
    assert result.normative_output.temporal_provenance == grounding.model_dump(mode="json")
    assert [r.model_dump() for r in result.references] == item["references"]
    assert "Fontes:" not in result.answer
    assert result.normative_output.references
    assert "§9º" not in result.answer
    assert all("§" not in r.display_text for r in result.normative_output.references)
    if attempts == 2:
        assert remote.calls[1]["user_prompt"].startswith(remote.calls[0]["user_prompt"])
        assert remote.calls[0]["system_prompt"] == remote.calls[1]["system_prompt"]
        assert "unvalidated_subdivision" in remote.calls[1]["user_prompt"]
        assert result.output_audit.regenerated_answer == answers[1]
        assert result.output_audit.guard_violations
    if action == "fallback":
        assert result.output_audit.second_guard_violations
        assert "Não foi possível formular" in result.answer
    assert "output_audit" not in result.model_dump()


def test_grounding_contract_remains_roundtrippable():
    _, _, grounding = case()
    assert TemporalGroundingContext.model_validate_json(grounding.model_dump_json()) == grounding


@pytest.mark.asyncio
async def test_regeneration_provider_failure_keeps_original_raw_and_falls_back():
    from rag_baseline.openrouter import OpenRouterError

    class FailingRetry(SequenceClient):
        async def chat(self, **payload):
            if self.calls:
                self.calls.append(payload)
                raise OpenRouterError("simulated failure")
            return await super().chat(**payload)

    item, chunks, grounding = case("H_citation")
    remote = FailingRetry(["Fonte: art. 53, §9º."])
    result = await RagService(
        openrouter=remote, vector_store=None, top_k=5, embedding_model="test", llm_model="test"
    ).generate(item["question"], chunks, temporal_grounding=grounding)
    assert len(remote.calls) == 2
    assert result.output_audit.raw_answer == "Fonte: art. 53, §9º."
    assert result.output_audit.guard_action == "fallback"
    assert result.output_audit.regeneration_error == "OpenRouterError"
    assert "§9º" not in result.answer


def test_metrics_separate_provider_failures_guard_actions_and_substantive_completion():
    from rag_baseline.structured_evaluation import summarize

    labels = dict(
        citation_violation=False, chronology_violation=False, temporal_contradiction=False
    )
    bad = dict(citation_violation=True, chronology_violation=True, temporal_contradiction=True)
    rows = [
        dict(
            raw=bad,
            final=labels,
            official_reference_violation=False,
            guard_action="regenerated",
            completed=True,
        ),
        dict(
            raw=bad,
            final=labels,
            official_reference_violation=False,
            guard_action="fallback",
            completed=False,
        ),
        dict(
            raw=labels,
            final=labels,
            official_reference_violation=False,
            guard_action="accepted",
            completed=False,
        ),
    ]
    result = summarize(rows)
    assert result["raw_CGVR"] == {"numerator": 2, "denominator": 3, "value": 2 / 3}
    assert result["final_UCER"]["numerator"] == 0
    assert result["guard_activation"]["numerator"] == 2
    assert result["regeneration_success"]["denominator"] == 2
    assert result["regeneration_success"]["numerator"] == 1
    assert result["answer_completion"]["numerator"] == 1
    assert summarize([])["regeneration_success"]["value"] is None
