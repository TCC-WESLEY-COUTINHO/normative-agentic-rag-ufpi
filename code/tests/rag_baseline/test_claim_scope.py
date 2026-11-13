"""Conditions of application, presumed facts and added qualifiers.

Texts come from observed generations. These checks are bounded signals; passing them does not
establish that an answer is legally correct.
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_claim_relations import generate
from test_normative_output import SequenceClient

import rag_baseline.evidence_support as support
from rag_baseline.corpus import load_corpus
from rag_baseline.grounding import build_temporal_grounding
from rag_baseline.models import RetrievedChunk
from rag_baseline.normative_output import NormativeOutputGuard
from rag_baseline.output_contracts import AllowedTemporalFacts, GenerationAudit
from rag_baseline.prompts import V2_SYSTEM_PROMPT
from rag_baseline.service import RagService
from rag_baseline.versioning import REGISTRY_PATH, NormativeRegistry, TemporalIntent, VersionFilter

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "claim_scope.json").read_text("utf-8"))
ART_258 = (
    "Art. 258. Os componentes curriculares oriundos de cursos concluídos na UFPI, aproveitadas "
    "em outro curso, implicarão o registro da nota obtida anteriormente acrescida da ocorrência "
    "CC (crédito concedido), não devendo compor o índice de rendimento acadêmico (IRA)."
)
EVIDENCE = {("ufpi-177-2012", "258"): ART_258}


def evidence_of(case):
    return {(c["norm_id"], c["article"]): c["content"] for c in FIXTURE[case]["chunks"]}


def text_of(case):
    return FIXTURE[case]["regenerated"] or FIXTURE[case]["raw"]


def guard_codes(raw, evidence, question):
    grounding = SimpleNamespace(
        evidence_states=[],
        known_relations=[],
        requested_time_context={},
        generation_constraints=SimpleNamespace(
            must_not_claim_current_validity=False,
            must_not_claim_unknown_as_current=False,
            must_not_present_revoked_rule_as_current=False,
        ),
        temporal_intent="indeterminate",
    )
    return {
        v.code
        for v in NormativeOutputGuard().check(
            raw,
            [],
            AllowedTemporalFacts(items=[]),
            grounding,
            evidence=evidence,
            question=question,
        )
    }


# Conditions of application


def test_condition_is_extracted_from_the_provision():
    found = support.scope_conditions(EVIDENCE)
    assert [(c.article, c.noun, c.qualifier) for c in found] == [("258", "cursos", "concluidos")]


def test_provision_without_a_condition_yields_none():
    assert support.scope_conditions({("n", "1"): "O curso tem duração de quatro anos."}) == []


@pytest.mark.parametrize("case", ["GRAD-018.r1", "GRAD-018.r2"])
def test_observed_rule_extended_beyond_its_condition_is_flagged(case):
    assert support.dropped_scope_conditions(text_of(case), evidence_of(case))


@pytest.mark.parametrize(
    "claim",
    [
        "A nota de componente aproveitado de outro curso da UFPI não entra no IRA.",
        "Como você não concluiu o curso, a nota aproveitada não deve compor o IRA.",
    ],
)
def test_rule_applied_outside_its_condition_is_flagged(claim):
    assert support.dropped_scope_conditions(claim, EVIDENCE)


@pytest.mark.parametrize(
    "claim",
    [
        "Se o curso de origem foi concluído na UFPI, a nota aproveitada não compõe o IRA.",
        "A nota aproveitada de cursos concluídos na UFPI recebe CC e não compõe o IRA.",
        "O art. 258 trata só de cursos concluídos; os trechos não tratam de curso não concluído.",
        "O curso exige estágio supervisionado para a colação de grau.",
        "O IRA é a média do rendimento escolar final.",
        "O art. 124 inclui componentes aproveitados, durante o curso de graduação, no cálculo do IRA.",
    ],
)
def test_rule_stated_with_its_condition_or_about_something_else_is_accepted(claim):
    assert support.dropped_scope_conditions(claim, EVIDENCE) == []


def test_condition_of_one_article_does_not_reach_a_rule_of_another():
    evidence = {
        **EVIDENCE,
        ("ufpi-177-2012", "257"): "Art. 257. Os componentes cursados em outra IES, aproveitados "
        "na UFPI, implicam registro como CC e não compõem o índice de rendimento acadêmico (IRA).",
    }
    claim = "Os componentes cursados em outra IES, aproveitados em curso da UFPI, recebem CC e não compõem o IRA."
    assert support.dropped_scope_conditions(claim, evidence) == []


def test_condition_not_retrieved_is_not_required():
    claim = "A nota aproveitada de outro curso da UFPI não compõe o IRA."
    assert support.dropped_scope_conditions(claim, {("n", "1"): "O curso tem quatro anos."}) == []


def test_justification_that_extends_a_category_is_flagged():
    item = FIXTURE["GRAD-018.r2"]
    assert support.unsupported_generalizations(
        item["raw"], evidence_of("GRAD-018.r2"), item["question"]
    )


def test_explanation_that_is_not_a_category_extension_is_accepted():
    claim = "A faixa do art. 116, o que inclui média parcial de 5,0, depende da assiduidade."
    assert support.unsupported_generalizations(claim, {("n", "1"): "Art. 116."}, "pergunta") == []


def test_extension_stated_by_the_provision_is_accepted():
    evidence = {("n", "1"): "São isentos os alunos, o que inclui os transferidos."}
    claim = "São isentos os alunos, o que inclui os transferidos."
    assert support.unsupported_generalizations(claim, evidence, "pergunta") == []


# Facts the user did not give


def test_observed_presumed_status_is_flagged():
    item = FIXTURE["GRAD-003.r3"]
    assert support.inferred_user_facts(item["raw"], item["question"])


@pytest.mark.parametrize(
    "claim",
    [
        "Isso não se aplica, pois o exame final ainda não foi realizado.",
        "O exame final já foi realizado, então não há nova oportunidade.",
        "Você já realizou o exame final.",
        "Você cumpriu a frequência mínima.",
        "Você foi aprovado no componente.",
    ],
)
def test_status_the_user_did_not_give_is_flagged(claim):
    assert support.inferred_user_facts(claim, "Minha média parcial foi 5,0.")


@pytest.mark.parametrize(
    ("claim", "question"),
    [
        (
            "Como o exame final ainda não foi realizado, você pode fazê-lo.",
            "Ainda não fiz o exame.",
        ),
        ("Você já realizou o exame final, então vale a média final.", "Já fiz o exame final."),
        ("Você foi reprovado no componente.", "Fui reprovado no componente."),
        ("Você cumpriu a frequência mínima.", "Cumpri a frequência mínima."),
        ("O exame final já foi realizado.", "Já realizei o exame final."),
        ("Se você já realizou o exame final, vale a média final.", "Média parcial 5,0."),
        ("Se o exame final ainda não foi realizado, você pode fazê-lo.", "Média parcial 5,0."),
        ("Caso o exame final já foi realizado, vale a média final.", "Média parcial 5,0."),
        ("Quem tem média parcial de 4 a 7 e assiduidade faz o exame final.", "Média parcial 5,0."),
    ],
)
def test_status_given_by_the_user_or_stated_conditionally_is_accepted(claim, question):
    assert support.inferred_user_facts(claim, question) == []


@pytest.mark.parametrize("case", ["GRAD-003.r1", "GRAD-003.r2"])
def test_conditional_observed_answers_are_not_flagged(case):
    item = FIXTURE[case]
    assert support.inferred_user_facts(text_of(case), item["question"]) == []


@pytest.mark.parametrize(
    ("claim", "question"),
    [
        ("Você já realizou o exame final.", "Ainda não fiz o exame final."),
        ("Você foi aprovado no componente.", "Fui aprovado? Minha média parcial foi 5,0."),
        ("O exame final ainda não foi realizado.", "Já fiz o exame final."),
        ("Você foi reprovado.", "Minha média parcial foi 5,0, fui reprovado?"),
        ("Você já realizou o exame final.", "Já fiz a matrícula."),
        ("Você cumpriu a frequência mínima.", "Cumpri o prazo de matrícula."),
        ("Você foi aprovado no componente.", "Fui aprovado no vestibular."),
    ],
)
def test_question_or_opposite_statement_does_not_authorize_a_status(claim, question):
    assert support.inferred_user_facts(claim, question)


# Added qualifiers


def test_observed_added_qualifier_is_flagged():
    item = FIXTURE["POS-015"]
    assert support.unsupported_qualifiers(text_of("POS-015"), evidence_of("POS-015"))
    assert item["question"]


@pytest.mark.parametrize(
    "claim",
    [
        "Devem ser observados os critérios do Regimento Interno de origem.",
        "Devem ser observados os critérios do Regimento Interno do PPG de destino.",
    ],
)
def test_qualifier_absent_from_evidence_is_flagged(claim):
    evidence = {("n", "1"): "A aprovação observa os critérios definidos no Regimento Interno."}
    assert support.unsupported_qualifiers(claim, evidence)


@pytest.mark.parametrize(
    "claim",
    [
        "Devem ser observados os critérios do Regimento Interno.",
        "Devem ser observados os critérios do Regimento Interno de cada PPG.",
    ],
)
def test_plain_instrument_is_accepted(claim):
    evidence = {("n", "1"): "A aprovação observa os critérios definidos no Regimento Interno."}
    assert support.unsupported_qualifiers(claim, evidence) == []


def test_qualifier_present_in_evidence_is_preserved():
    evidence = {("n", "1"): "Observa o Regimento Interno dos PPGs de origem e destino."}
    claim = "Observa o Regimento Interno do PPG de origem e destino."
    assert support.unsupported_qualifiers(claim, evidence) == []


# Whole guard


@pytest.mark.parametrize(
    ("case", "code"),
    [
        ("GRAD-018.r1", "dropped_scope_condition"),
        ("GRAD-018.r2", "dropped_scope_condition"),
        ("GRAD-003.r3", "inferred_user_fact"),
        ("POS-015", "unsupported_qualifier"),
    ],
)
def test_guard_reports_each_observed_failure(case, code):
    assert code in guard_codes(text_of(case), evidence_of(case), FIXTURE[case]["question"])


NEW = {"dropped_scope_condition", "unsupported_qualifier", "inferred_user_fact"}


@pytest.mark.parametrize(
    "case",
    [
        "B-001",
        "B-002",
        "C1-003",
        "C1-004",
        "GRAD-009",
        "GRAD-019",
        "TEMP-GRAD-002",
        "TEMP-GRAD-005",
        "GRAD-003.r1",
    ],
)
def test_guard_does_not_flag_answers_read_as_supported(case):
    codes = guard_codes(text_of(case), evidence_of(case), FIXTURE[case]["question"])
    assert codes & NEW == set()


# Generation


def test_prompt_states_conditions_found_in_the_evidence():
    assert support.scope_instruction(support.scope_conditions(EVIDENCE))
    assert "concluidos" in support.scope_instruction(support.scope_conditions(EVIDENCE))
    assert support.scope_instruction([]) == ""


def generate_on(replies, question):
    corpus = REGISTRY_PATH.parent.parent / "evaluation/corpora/graduacao_setor_v2.json"
    chunks = [
        RetrievedChunk(**c.model_dump(), rank=i + 1, distance=None)
        for i, c in enumerate(
            c
            for c in load_corpus(corpus, id_prefix="ufpi-177-2012")
            if c.article_number in {"124", "257", "258"}
        )
    ]
    registry = NormativeRegistry.load()
    chunks, audit = VersionFilter(registry).apply(
        chunks, temporal_intent=TemporalIntent(mode="current"), top_k=5
    )
    remote = SequenceClient(replies)
    result = asyncio.run(
        RagService(
            openrouter=remote,
            vector_store=None,
            top_k=5,
            embedding_model="controlled",
            llm_model="controlled",
        ).generate(
            question,
            chunks,
            temporal_grounding=build_temporal_grounding(chunks, audit, registry),
        )
    )
    return result, remote


CONDITIONED = "A nota de cursos concluídos na UFPI, aproveitada em outro curso, recebe CC e não compõe o IRA, conforme o art. 258."
EXTENDED = "A nota de componentes aproveitados de outro curso da UFPI não entra no IRA, conforme o art. 258."
OUTSIDE = (
    "O art. 258 trata de cursos concluídos e não trata de curso não concluído; "
    "para esse caso os trechos não trazem a regra."
)
SATISFIED, NOT_SATISFIED, UNKNOWN = (
    "Concluí um curso na UFPI e aproveitei componentes em outro curso. A nota entra no IRA?",
    "Não concluí meu curso na UFPI e aproveitei componentes em outro curso. A nota entra no IRA?",
    "Aproveitei componentes de outro curso da UFPI. A nota entra no IRA?",
)


@pytest.mark.parametrize(
    ("question", "reply"),
    [
        (SATISFIED, CONDITIONED),
        (NOT_SATISFIED, OUTSIDE),
        (UNKNOWN, CONDITIONED),
        (UNKNOWN, OUTSIDE),
    ],
)
def test_service_accepts_answers_that_keep_the_condition(question, reply):
    result, remote = generate_on([reply], question)
    assert result.output_audit.guard_action == "accepted"
    assert "CONDIÇÕES DE APLICAÇÃO" in remote.calls[0]["user_prompt"]


@pytest.mark.parametrize("question", [SATISFIED, NOT_SATISFIED, UNKNOWN])
def test_service_recovers_when_the_regeneration_restores_the_condition(question):
    result, remote = generate_on([EXTENDED, CONDITIONED], question)
    assert result.output_audit.guard_action == "regenerated"
    assert "dropped_scope_condition" in remote.calls[1]["user_prompt"]


@pytest.mark.parametrize("question", [NOT_SATISFIED, UNKNOWN])
def test_service_abstains_when_the_extension_persists(question):
    result, remote = generate_on([EXTENDED, EXTENDED], question)
    assert result.output_audit.guard_action == "fallback"
    assert len(remote.calls) == 2


def test_generation_without_a_condition_keeps_the_prompt_unchanged():
    _, remote = generate(["Você tem direito ao exame final, conforme o art. 116."])
    assert "CONDIÇÕES DE APLICAÇÃO" not in remote.calls[0]["user_prompt"]


def test_regeneration_keeps_a_single_retry_after_a_presumed_fact():
    _, remote = generate(
        [
            "Você tem direito, pois o exame final ainda não foi realizado, conforme o art. 116.",
            "Você tem direito, pois o exame final ainda não foi realizado, conforme o art. 116.",
        ]
    )
    assert len(remote.calls) == 2


def test_guard_identity_changed():
    assert GenerationAudit.model_fields["guard_version"].default == "5"


@pytest.mark.parametrize("fragment", ["qualificador", "mais de uma situação"])
def test_prompt_states_each_distinction(fragment):
    assert fragment in V2_SYSTEM_PROMPT
