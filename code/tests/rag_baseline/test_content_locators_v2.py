"""V2 permissions are structural, scoped and independent of official display."""

import importlib
import json
from pathlib import Path

import pytest

from rag_baseline.normative_output import NormativeOutputGuard
from rag_baseline.service import RagService
from tests.rag_baseline.test_normative_output import SequenceClient, case, output_parts

V1 = Path(__file__).resolve().parents[3] / "evaluation/results/structured_normative_output_v1_001"


def policy_parts(case_id="A_grad_historical", question=None, **kwargs):
    module = importlib.import_module("rag_baseline.content_locators")
    item, _, grounding = case(case_id)
    _, references, facts = output_parts(case_id)
    locators = module.ContentLocatorPolicy().build(
        question if question is not None else item["question"], grounding, references, **kwargs
    )
    return grounding, references, facts, locators


def check(text, case_id="A_grad_historical", question=None, **kwargs):
    grounding, references, facts, locators = policy_parts(case_id, question, **kwargs)
    return NormativeOutputGuard().check(
        text, references, facts, grounding, allowed_content_locators=locators
    )


@pytest.mark.parametrize(
    "question",
    [
        "Como era o §4º do art. 68?",
        "Como era o artigo 68, parágrafo 4º?",
        "O art. 68, § 4 da Resolução 177/2012 tratava de quê?",
    ],
)
def test_query_explicit_is_normalized_and_scoped(question):
    _, references, _, locators = policy_parts(question=question)
    assert any(
        (
            locator.norm_id,
            locator.article,
            locator.subdivision_type,
            locator.subdivision_value,
            locator.source,
        )
        == ("ufpi-177-2012", "68", "paragraph", "4", "query_explicit")
        for locator in locators
    )
    assert all(r.validated_subdivision is None and "§" not in r.display_text for r in references)


@pytest.mark.parametrize(
    "question",
    ["E o §4º?", "Como era o art. 68?", "Art. 999, §4º?", "Art. 68, §4º da Resolução 999/2025?"],
)
def test_query_does_not_grant_ambiguous_or_unbound_permission(question):
    _, _, _, locators = policy_parts(question=question)
    assert not any(
        locator.source == "query_explicit" and locator.subdivision_type for locator in locators
    )


def test_amendment_target_authorizes_without_query_subdivision():
    _, _, _, locators = policy_parts(question="Como era o coordenador?")
    assert any(
        (locator.norm_id, locator.article, locator.subdivision_value, locator.source)
        == ("ufpi-177-2012", "68", "4", "amendment_target")
        for locator in locators
    )
    assert check("O §4º estabelecia a escolha do coordenador.") == []


@pytest.mark.parametrize(
    "text",
    [
        "O §4º do art. 68 estabelecia a escolha.",
        "O art. 68, parágrafo 4º estabelecia a escolha.",
        "O §4º estabelecia a escolha.",
    ],
)
def test_supported_paragraph_is_content_and_never_promotes_display(text):
    assert check(text) == []
    _, refs, _, _ = policy_parts()
    assert next(r for r in refs if r.article == "68").display_text == "Resolução 177/2012, art. 68"


@pytest.mark.parametrize("case_id", ["E_validity", "F_comparison", "C_post_historical"])
@pytest.mark.parametrize(
    "text",
    [
        "O inciso VI do art. 62 da Resolução 956/2025 registra a revogação.",
        "A Resolução 956/2025, art. 62, VI, registra a revogação.",
    ],
)
def test_known_relation_authorizes_proof_locator_but_adds_no_display(case_id, text):
    grounding, refs, _, locators = policy_parts(case_id)
    assert grounding.known_relations[0].evidence_article == "62, VI"
    assert any(
        (locator.article, locator.subdivision_value, locator.source)
        == ("62", "VI", "normative_relation")
        for locator in locators
    )
    assert check(text, case_id) == []
    assert all("VI" not in r.display_text for r in refs)
    if case_id != "E_validity":
        assert all(r.article != "62" for r in refs)


@pytest.mark.parametrize(
    "text",
    [
        "O §4º do art. 69 estabelece isso.",
        "A Resolução 1056/2026, art. 68, §4º estabelece isso.",
        "O §1º do art. 68 estabelece isso.",
        "O art. 999 estabelece isso.",
        "A Resolução 999/2025 estabelece isso.",
    ],
)
def test_permissions_do_not_transfer_to_another_article_norm_or_subdivision(text):
    assert check(text)


@pytest.mark.parametrize(
    "text",
    [
        "caput",
        "No caput está o prazo.",
        "Art. 53, caput.",
        "O caput do art. 53 estabelece o prazo.",
        "O §1º do art. 53 estabelece o prazo.",
    ],
)
def test_f3_unvalidated_subdivisions_including_caput_are_blocked(text):
    violations = check(text, "H_citation")
    assert any(v.code == "unvalidated_subdivision" for v in violations)
    assert all(text[v.start : v.end] == v.excerpt for v in violations)


def test_plain_article_and_raw_chunk_text_do_not_authorize_caput_or_paragraph():
    assert check("O art. 53 estabelece o prazo.", "H_citation") == []
    assert not any(locator.subdivision_type for locator in policy_parts("H_citation")[3])
    item, chunks, grounding = case("A_grad_historical")
    assert any("§" in c.content for c in chunks)
    module = importlib.import_module("rag_baseline.content_locators")
    grounding = grounding.model_copy(update={"known_relations": []})
    permissions = module.ContentLocatorPolicy().build(
        "Qual o art. 68?", grounding, output_parts("A_grad_historical")[1]
    )
    assert not any(locator.subdivision_type for locator in permissions)


def test_explicit_validated_caput_does_not_change_display():
    contracts = importlib.import_module("rag_baseline.output_contracts")
    locator = contracts.AllowedContentLocator(
        norm_id="ufpi-956-2025",
        article="53",
        subdivision_type="caput",
        subdivision_value="caput",
        source="validated_evidence",
        authorization_reason="Explicit validated structural test fixture; not raw chunk text.",
    )
    assert (
        check("O caput do art. 53 estabelece o prazo.", "H_citation", validated_evidence=[locator])
        == []
    )
    assert all(r.validated_subdivision is None for r in policy_parts("H_citation")[1])


def test_query_explicit_caput_is_scoped_to_its_article():
    assert (
        check(
            "O caput do art. 53 estabelece o prazo.",
            "H_citation",
            question="Qual o caput do art. 53 da Resolução 956/2025?",
        )
        == []
    )
    assert check(
        "O caput do art. 54 estabelece o prazo.",
        "H_citation",
        question="Qual o caput do art. 53 da Resolução 956/2025?",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case_id,text",
    [
        ("A_grad_historical", "O §4º do art. 68 estabelecia a escolha."),
        ("E_validity", "O art. 62, VI, da Resolução 956/2025 registra a revogação."),
    ],
)
async def test_service_supported_locator_does_not_retry_and_audits_permissions(case_id, text):
    item, chunks, grounding = case(case_id)
    client = SequenceClient([text])
    result = await RagService(
        openrouter=client, vector_store=None, top_k=5, embedding_model="test", llm_model="test"
    ).generate(item["question"], chunks, temporal_grounding=grounding)
    assert result.output_audit.guard_action == "accepted"
    assert len(client.calls) == 1
    assert text in result.answer
    assert result.output_audit.allowed_content_locators
    assert result.output_audit.guard_version == "5"
    assert "output_audit" not in result.model_dump()
    assert "LOCATORS DE CONTEÚDO" in client.calls[0]["user_prompt"]


@pytest.mark.asyncio
async def test_service_caput_recurrence_falls_back_with_identical_permissions():
    item, chunks, grounding = case("H_citation")
    raw = "O art. 53, § 9º estabelece o prazo."
    client = SequenceClient([raw, raw])
    result = await RagService(
        openrouter=client, vector_store=None, top_k=5, embedding_model="test", llm_model="test"
    ).generate(item["question"], chunks, temporal_grounding=grounding)
    assert result.output_audit.guard_action == "fallback"
    assert result.output_audit.raw_answer == result.output_audit.regenerated_answer == raw
    assert len(client.calls) == 2
    assert client.calls[1]["user_prompt"].startswith(client.calls[0]["user_prompt"])
    assert "§ 9º" not in result.answer


@pytest.mark.parametrize(
    "case_id,repetition",
    [
        ("A_grad_historical", 9),
        ("E_validity", 3),
        ("E_validity", 6),
        ("E_validity", 7),
        ("E_validity", 9),
        ("E_validity", 10),
    ],
)
def test_six_saved_v1_chronology_failures_are_detected_directly(case_id, repetition):
    row = next(
        json.loads(line)
        for line in (V1 / "raw_generations.jsonl").read_text("utf-8").splitlines()
        if (json.loads(line)["id"], json.loads(line)["repetition"]) == (case_id, repetition)
    )
    grounding, refs, facts = output_parts(case_id)
    violations = NormativeOutputGuard().check(row["raw_answer"], refs, facts, grounding)
    assert any(
        v.code in {"unsupported_effectivity", "unsupported_chronology", "unsupported_publication"}
        for v in violations
    )


@pytest.mark.parametrize(
    "text",
    [
        "A norma passou a vigorar em 2025.",
        "A norma produz efeitos desde sua assinatura.",
        "A norma tem efeito imediato.",
        "A norma aplica-se com efeito imediato.",
        "A norma tem efeitos a partir da vigência do ato posterior.",
        "A redação estava em vigor até a entrada em vigor do novo ato.",
        "A norma anterior não tem eficácia vigente após a publicação da Resolução 956/2025.",
        "A norma vale na data de sua publicação.",
    ],
)
def test_new_unsupported_chronology_classes(text):
    grounding, refs, facts = output_parts("E_validity")
    assert any(
        v.code.startswith("unsupported_") and v.code != "unsupported_current_validity"
        for v in NormativeOutputGuard().check(text, refs, facts, grounding)
    )


@pytest.mark.parametrize(
    "text",
    [
        "Não é possível afirmar que está vigente.",
        "Não se pode certificar que está vigente.",
        "A evidência não permite concluir que está vigente.",
        "Não há elementos suficientes para confirmar se a resolução está em vigor.",
    ],
)
def test_conservative_unknown_negations_pass(text):
    grounding, refs, facts = output_parts("G_unknown")
    assert NormativeOutputGuard().check(text, refs, facts, grounding) == []


def test_saved_unknown_false_positive_is_reproduced_and_fixed():
    row = next(
        json.loads(line)
        for line in (V1 / "raw_generations.jsonl").read_text("utf-8").splitlines()
        if json.loads(line)["id"] == "G_unknown"
    )
    grounding, refs, facts = output_parts("G_unknown")
    assert NormativeOutputGuard().check(row["raw_answer"], refs, facts, grounding) == []


@pytest.mark.parametrize(
    "text",
    [
        "A norma está vigente.",
        "Não é possível certificar a anterior, mas a norma está vigente.",
        "Não há dúvida de que a norma está vigente.",
    ],
)
def test_positive_unknown_certification_remains_blocked(text):
    grounding, refs, facts = output_parts("G_unknown")
    assert any(
        v.code == "unsupported_current_validity"
        for v in NormativeOutputGuard().check(text, refs, facts, grounding)
    )


@pytest.mark.parametrize(
    "text",
    [
        "Antes da alteração promovida pela Resolução CEPEX/UFPI nº 1056/2026, o § 4º do art. 68 da Resolução nº 177/2012 estabelecia a escolha.",
        "Antes da alteração da Resolução 1.056/2026, o Art. 68 do regulamento (Resolução 177/2012), §4º, previa a escolha.",
        "O §4º do art. 68 do Regulamento Geral da Graduação da UFPI, após a alteração promovida pela Resolução CEPEX/UFPI nº 1.056/2026, estabelece a escolha.",
    ],
)
def test_article_attachment_distinguishes_provision_from_amending_act(text):
    assert check(text, "B_grad_current") == []


def test_comparison_nominal_vigente_in_explicit_past_is_not_current_certification():
    text = "A regra vigente na Resolução CEPEX/UFPI nº 658/2024, art. 43, estabelecia a defesa presencial."
    assert check(text, "F_comparison") == []
    assert check(text.replace("estabelecia", "estabelece"), "F_comparison")
    assert check("A Resolução 658/2024 está vigente e estabelecia a regra.", "F_comparison")


@pytest.mark.parametrize(
    "text", ["O §4º do art. 68 e 69 estabelecia isso.", "O art. 68 e 69, §4º, estabelecia isso."]
)
def test_explicit_article_list_does_not_become_implicit_unique_paragraph_permission(text):
    assert any(v.code == "unvalidated_subdivision" for v in check(text))


@pytest.mark.parametrize(
    "raw",
    [
        "Essa redação constava da Resolução 177/2012, art. 68, parágrafo 4, "
        "e foi alterada pela Resolução 1056/2026.",
        "Essa redação constava da Resolução 177/2012, art. 68, parágrafo 4, "
        "alterado pela Resolução 1056/2026.",
    ],
)
def test_article_stays_with_preceding_norm_when_amendment_follows(raw):
    module = importlib.import_module("rag_baseline.content_locators")
    text = module.fold(raw)
    norms = list(module.NORM.finditer(text))
    article = next(module.ARTICLE.finditer(text))
    assert module.associated_norm(text, article, norms)[0] == "177/2012"
    assert [mention.norm_id for mention in module.locator_mentions(raw)] == ["ufpi-177-2012"]
