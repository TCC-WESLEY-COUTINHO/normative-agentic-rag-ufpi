"""Claim relations against the evidence: deadlines, procedure roles, consequences, scope and inversion.

Texts come from observed generations. These checks are bounded signals; passing them does not
establish that an answer is legally correct.
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
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

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "claim_relations.json").read_text("utf-8")
)
ANSWERS = sorted(FIXTURE)
ART_108 = (
    "§ 1º O requerimento dirigido ao professor responsável pela disciplina, devidamente "
    "justificado e comprovado, deve ser protocolado à chefia do departamento ou curso, no prazo "
    "de 3 (três) dias úteis, contado este prazo a partir da data da avaliação não realizada.\n"
    "§ 3º O professor do componente curricular terá o prazo máximo de 2 (dois) dias úteis, a "
    "partir do recebimento do requerimento, para julgá-lo.\n"
    "§ 4º A realização da verificação obedecerá ao prazo de até 5 (cinco) dias após o "
    "deferimento do pedido do aluno.\n"
    "§ 6º Ao aluno que não participar de qualquer avaliação, não tendo obtido a permissão para "
    "fazer outra, é atribuída a nota 0 (zero)."
)
EVIDENCE = {("ufpi-177-2012", "108"): ART_108}


def evidence_of(case):
    return {(c["norm_id"], c["article"]): c["content"] for c in FIXTURE[case]["chunks"]}


def text_of(case):
    return FIXTURE[case]["regenerated"] or FIXTURE[case]["raw"]


# Deadlines


@pytest.mark.parametrize(
    "claim",
    [
        "A verificação ocorre em até 5 (cinco) dias úteis após o deferimento.",
        "A verificação ocorre em até cinco dias corridos após o deferimento.",
        "O requerimento deve ser protocolado no prazo de 3 (três) dias.",
        "O professor julga em 2 dias corridos.",
    ],
)
def test_deadline_qualifier_not_in_evidence_is_flagged(claim):
    assert support.deadline_mismatches(claim, EVIDENCE)


@pytest.mark.parametrize(
    "claim",
    [
        "A verificação ocorre em até 5 (cinco) dias após o deferimento.",
        "O requerimento deve ser protocolado no prazo de 3 (três) dias úteis.",
        "O professor julga em até dois dias úteis.",
    ],
)
def test_deadline_as_written_in_evidence_is_accepted(claim):
    assert support.deadline_mismatches(claim, EVIDENCE) == []


def test_number_absent_from_evidence_stays_with_the_number_check():
    assert support.deadline_mismatches("O prazo é de 15 dias úteis.", EVIDENCE) == []


def test_question_does_not_authorize_a_qualifier():
    assert support.deadline_mismatches("São 5 dias úteis.", EVIDENCE)


def test_deadline_start_event_must_come_from_the_same_provision():
    assert support.deadline_mismatches(
        "São 3 dias úteis a partir da publicação do edital.", EVIDENCE
    )
    assert support.deadline_mismatches("São 5 dias após o indeferimento do pedido.", EVIDENCE)
    assert support.deadline_mismatches("São 3 dias úteis contados da publicação.", EVIDENCE)
    for claim in (
        "O prazo de 3 dias úteis é contado a partir da data da avaliação não realizada.",
        "São 5 dias após o deferimento do pedido.",
        "São 5 dias após a aprovação do requerimento.",
        "O professor tem até dois dias úteis, a partir do recebimento do pedido.",
    ):
        assert support.deadline_mismatches(claim, EVIDENCE) == []


def test_observed_deadline_unit_error_is_flagged():
    case = FIXTURE["C1-004"]
    found = support.deadline_mismatches(case["raw"], evidence_of("C1-004"))
    assert any("5" in fold_text(case["raw"], item) for item in found)


def fold_text(raw, item):
    return raw[item.start : item.end]


# Procedure roles


@pytest.mark.parametrize(
    "claim",
    [
        "O requerimento deve ser protocolado ao professor responsável.",
        "O requerimento é dirigido à chefia do departamento.",
        "O requerimento deve ser protocolado na secretaria.",
        "A chefia julga o requerimento.",
        "O pedido será julgado pela chefia.",
    ],
)
def test_role_not_linked_in_evidence_is_flagged(claim):
    assert support.procedure_role_mismatches(claim, EVIDENCE)


@pytest.mark.parametrize(
    "claim",
    [
        "O requerimento é dirigido ao professor e protocolado à chefia do departamento ou curso.",
        "O requerimento deve ser protocolado à chefia do departamento.",
        "O professor julga o requerimento em até dois dias úteis.",
        "A chefia não julga o requerimento.",
        "O pedido é julgado pelo professor.",
        "O pedido não será julgado pela chefia; o professor julga o requerimento.",
    ],
)
def test_role_linked_in_evidence_is_accepted(claim):
    assert support.procedure_role_mismatches(claim, EVIDENCE) == []


def test_decider_is_the_agent_of_the_decision_not_the_first_role_named():
    evidence = {("n", "1"): "A chefia recebe o requerimento e o professor julga o pedido."}
    assert support.procedure_role_mismatches("O professor julga o pedido.", evidence) == []
    assert support.procedure_role_mismatches("A chefia julga o pedido.", evidence)
    relative = {("n", "1"): "A chefia encaminha o requerimento ao professor, que julga o pedido."}
    assert support.procedure_role_mismatches("O professor julga o pedido.", relative) == []
    assert support.procedure_role_mismatches("A chefia julga o pedido.", relative)


def test_observed_protocol_recipient_error_is_flagged():
    assert support.procedure_role_mismatches(FIXTURE["B-002"]["raw"], evidence_of("B-002"))


# Consequences


def test_consequence_not_tied_to_the_deadline_in_evidence_is_flagged():
    case = FIXTURE["C2-021"]
    assert support.unsupported_consequences(case["raw"], evidence_of("C2-021"))


@pytest.mark.parametrize(
    "claim",
    ["Perder o prazo resulta em nota zero.", "Se perder o prazo, o aluno receberá nota zero."],
)
def test_direct_and_conditional_consequence_forms_are_flagged(claim):
    assert support.unsupported_consequences(claim, EVIDENCE)


def test_negated_consequence_is_not_an_assertion_of_it():
    claim = "Se perder o prazo, o aluno não receberá nota zero."
    assert support.unsupported_consequences(claim, EVIDENCE) == []


def test_negated_evidence_does_not_authorize_the_consequence():
    evidence = {("n", "1"): "A perda do prazo não será cancelada a matrícula."}
    claim = "Se perder o prazo, a matrícula será cancelada."
    assert support.unsupported_consequences(claim, evidence)


def test_consequence_tied_to_the_deadline_in_evidence_is_accepted():
    evidence = {("n", "1"): "Não apresentada a justificativa no prazo, a matrícula será cancelada."}
    claim = "Se o aluno não apresentar a justificativa no prazo, a matrícula será cancelada."
    assert support.unsupported_consequences(claim, evidence) == []


def test_consequence_of_absence_without_deadline_is_accepted():
    claim = "Ao aluno que não obtiver a permissão para fazer outra avaliação é atribuída nota zero."
    assert support.unsupported_consequences(claim, EVIDENCE) == []


# Scope


@pytest.mark.parametrize("case", ["GRAD-018.r1"])
def test_universal_scope_absent_from_evidence_is_flagged(case):
    item = FIXTURE[case]
    assert support.unsupported_generalizations(item["raw"], evidence_of(case), item["question"])


def test_universal_scope_present_in_evidence_is_accepted():
    case = FIXTURE["TEMP-GRAD-005.r1"]
    assert (
        support.unsupported_generalizations(
            case["regenerated"], evidence_of("TEMP-GRAD-005.r1"), case["question"]
        )
        == []
    )


def test_universal_scope_outside_a_conclusion_is_not_read():
    claim = "A reprovação em três vezes no componente, independentemente de serem consecutivas."
    assert support.unsupported_generalizations(claim, EVIDENCE, "pergunta") == []


def test_universal_scope_with_another_contraction_is_the_same_marker():
    evidence = {("n", "1"): "Poderá ser designado, independentemente de seu vínculo com a UFPI."}
    claim = "Assim, pode ser designado independentemente do vínculo com a UFPI."
    assert support.unsupported_generalizations(claim, evidence, "pergunta") == []


# Facts the user did not give


def test_inferred_user_value_is_flagged():
    case = FIXTURE["GRAD-003.r1"]
    assert support.inferred_user_facts(case["regenerated"], case["question"])


def test_conditional_answer_with_the_given_value_is_accepted():
    case = FIXTURE["GRAD-003.r2"]
    assert support.inferred_user_facts(case["raw"], case["question"]) == []


def test_inference_about_a_value_the_user_gave_is_accepted():
    claim = "Sua média parcial foi 5,0, o que indica que está entre 4 e 7."
    assert support.inferred_user_facts(claim, "Tenho média parcial 5,0, entre 4 e 7") == []


def test_normative_limit_next_to_the_value_is_not_a_user_fact():
    claim = "No seu caso, a frequência de 80% atende, e a nota mínima exigida é sete."
    assert support.inferred_user_facts(claim, "Tenho frequência de 80%.") == []


def test_attribute_the_user_did_not_give_is_flagged():
    claim = "Sua média final foi 5,0."
    assert support.inferred_user_facts(claim, "Minha nota parcial foi 5,0.")
    assert support.inferred_user_facts("Sua média parcial foi 5,0.", "Média parcial 5,0.") == []
    asked_exam = "Minha média parcial é 5,0. Tenho direito ao exame final?"
    assert support.inferred_user_facts("Sua média final foi 5,0.", asked_exam)
    conditional = "Se sua média final for inferior a 6, você será reprovado."
    assert support.inferred_user_facts(conditional, "Média parcial 5,0. Serei aprovado?") == []


# Inversion between the two generations


def test_conclusion_polarity_reads_the_conclusion_not_the_rule():
    case = FIXTURE["GRAD-003.r1"]
    assert support.conclusion_polarity(case["raw"]) == "positive"
    assert support.conclusion_polarity(case["regenerated"]) == "negative"


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ("Você tem direito ao exame.", "Não há direito ao exame.", True),
        ("Sim, é possível.", "Não, não é possível.", True),
        ("Você pode realizar o exame.", "Você não pode realizar o exame.", True),
        (
            "Você tem direito ao exame.",
            "Você não tem direito ao exame. O aluno com média de 4 a 7 tem direito ao exame.",
            True,
        ),
        ("A matrícula pode ser feita na coordenação.", "O aluno não poderá participar.", False),
        (
            "Você tem direito ao exame final.",
            "Você não tem direito ao exame final. Assim, pode solicitar esclarecimento.",
            True,
        ),
        (
            "Você tem direito ao exame final.",
            "Você tem direito ao exame final; não é possível calcular sua média sem a nota.",
            False,
        ),
        ("Você tem direito ao exame.", "O aluno tem direito ao exame final.", False),
        ("Não há direito ao exame.", "Não há direito ao exame, conforme o art. 113.", False),
        ("O prazo é de 3 dias úteis.", "Não há direito ao exame.", False),
    ],
)
def test_inversion_needs_two_opposite_conclusions(first, second, expected):
    assert support.inverted_conclusion(first, second) is expected


@pytest.mark.parametrize("case", [name for name in ANSWERS if FIXTURE[name]["regenerated"]])
def test_observed_regenerations_invert_only_where_the_conclusion_changed(case):
    item = FIXTURE[case]
    assert support.inverted_conclusion(item["raw"], item["regenerated"]) is (case == "GRAD-003.r1")


# Whole guard


def guard_codes(raw, case):
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
            evidence=evidence_of(case),
            question=FIXTURE[case]["question"],
        )
    }


@pytest.mark.parametrize(
    ("case", "text", "code"),
    [
        ("C1-004", "raw", "deadline_mismatch"),
        ("B-002", "raw", "procedure_role_mismatch"),
        ("C2-021", "raw", "unsupported_consequence"),
        ("GRAD-018.r1", "raw", "unsupported_generalization"),
        ("GRAD-003.r1", "regenerated", "inferred_user_fact"),
    ],
)
def test_guard_reports_each_class(case, text, code):
    assert code in guard_codes(FIXTURE[case][text], case)


NEW = {
    "deadline_mismatch",
    "procedure_role_mismatch",
    "unsupported_consequence",
    "unsupported_generalization",
    "inferred_user_fact",
}
ACCEPTED = [
    "B-001.r1",
    "C2-003",
    "C2-009",
    "C2-012",
    "GRAD-019.r1",
    "POS2-008",
    "POS-013",
    "POS-015.r1",
    "GRAD-008.r2",
    "GRAD-003.r2",
    "TEMP-POS-005",
]


@pytest.mark.parametrize("case", ACCEPTED)
def test_guard_does_not_flag_answers_read_as_supported(case):
    assert guard_codes(text_of(case), case) & NEW == set()


# Regeneration path


def generate(replies, question="Tenho direito ao exame final?"):
    corpus = REGISTRY_PATH.parent.parent / "evaluation/corpora/graduacao_setor_v2.json"
    chunks = [
        RetrievedChunk(**c.model_dump(), rank=i + 1, distance=None)
        for i, c in enumerate(
            c for c in load_corpus(corpus, id_prefix="ufpi-177-2012") if c.article_number == "116"
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


def test_regeneration_that_inverts_the_conclusion_falls_back():
    result, _ = generate(
        [
            "Com base na redação vigente, você tem direito ao exame final, conforme o art. 116.",
            "Não há direito ao exame final, conforme o art. 116.",
        ]
    )
    assert result.output_audit.guard_action == "fallback"
    codes = {v.code for v in result.output_audit.second_guard_violations}
    assert "regeneration_conclusion_inverted" in codes


def test_inversion_after_a_bibliography_correction_falls_back():
    result, _ = generate(
        [
            "Você tem direito ao exame final, conforme o art. 116.\n\nReferências:\n- Resolução 177/2012, art. 116.",
            "Você não tem direito ao exame final, conforme o art. 116.",
        ]
    )
    assert result.output_audit.guard_action == "fallback"


def test_regeneration_that_keeps_the_conclusion_is_accepted():
    first = "Com base na redação vigente, você tem direito ao exame final, conforme o art. 116."
    result, remote = generate([first, "Você tem direito ao exame final, conforme o art. 116."])
    assert result.output_audit.guard_action == "regenerated"
    assert first in remote.calls[1]["user_prompt"]


def test_regeneration_after_a_content_violation_may_change_the_conclusion():
    result, remote = generate(
        [
            "Você não tem direito ao exame, pois isso indica que sua média final foi 3.",
            "Você tem direito ao exame final, conforme o art. 116.",
        ],
    )
    assert result.output_audit.guard_action == "regenerated"
    assert "RESPOSTA ANTERIOR" not in remote.calls[1]["user_prompt"]


# Version


def test_guard_identity_changed():
    assert GenerationAudit.model_fields["guard_version"].default == "5"


@pytest.mark.parametrize(
    "fragment",
    ["dias úteis", "dirigido", "protocolado", "consequência", "categoria"],
)
def test_prompt_states_each_distinction(fragment):
    assert fragment in V2_SYSTEM_PROMPT
