"""Regressions drawn from the line structure of indexed articles (OCR and irregular nesting)."""

import pytest

from rag_baseline.citation_contracts import CitedAnswer, Claim, Support
from rag_baseline.citation_verifier import PARTIAL_NOTICE, disposition, verify_claim
from rag_baseline.cited_generation import _permissions
from rag_baseline.evidence_spans import segment_chunk, segment_evidence
from tests.rag_baseline.test_evidence_spans import chunk, reference

NORM = "ufpi-658-2024"
ROOT = f"{NORM}:art58"

# Res. 658/2024, art. 58: OCR reads "III" as "Il", so "II" occurs twice under § 1º.
OCR_DUPLICATE = (
    "Art. 58. A atuação deverá ser definida por meio de um Plano de Estágio.\n"
    "- $ 1º O Plano de Estágio à Docência deverá conter:\n"
    "- | -dados do discente de pós-graduação;\n"
    "- Il -dados do componente curricular de atuação;\n"
    "- Il -objetivos da disciplina;\n"
    "- IV -objetivos do Estágio;\n"
    "- 8 2º O Plano deverá ser submetido à aprovação pelo Colegiado."
)

# Res. 177/2012, art. 68: alíneas directly under a paragraph, without an inciso.
ALINEAS_UNDER_PARAGRAPH = (
    "Art. 68. O estágio curricular obrigatório envolve:\n"
    "1. I - Coordenadoria de Estágio Obrigatório;\n"
    "2. II - orientador de estágio;\n"
    "> § 1º A Coordenadoria tem como atribuições básicas:\n"
    "> * a) viabilizar as condições necessárias ao desenvolvimento do estágio;\n"
    "> * b) propor normas e diretrizes gerais para os estágios obrigatórios;\n"
    "> § 2º O orientador do estágio será um professor do quadro da UFPI."
)

# Res. 956/2025, art. 33: alíneas group incisos that restart at I.
RESTARTING_INCISOS = (
    "Art. 33. O candidato selecionado deve apresentar os seguintes documentos:\n"
    "- a) Para candidatos brasileiros selecionados:\n"
    "2. | -Documento de identidade oficial com foto;\n"
    "3. Il -CPF do candidato selecionado;\n"
    "- b) Para candidatos estrangeiros selecionados:\n"
    "12. | -Cópia do Passaporte ou Documento de Identificação com foto;\n"
    "13. Il -Visto Temporário de estudante válido."
)


def spans_of(text, article="58", norm=NORM):
    return {s.span_id: s for s in segment_chunk(chunk(text, article_number=article), norm)}


def test_ocr_duplicate_labels_do_not_abort_and_are_marked_ambiguous():
    spans = spans_of(OCR_DUPLICATE)
    assert spans[f"{ROOT}:p1:incII"].ambiguous
    assert spans[f"{ROOT}:p1:incII~2"].ambiguous
    assert spans[f"{ROOT}:p1:incII~2"].text.startswith("- Il -objetivos")
    assert not spans[f"{ROOT}:p1:incIV"].ambiguous
    assert not spans[f"{ROOT}:p1"].ambiguous
    assert spans[f"{ROOT}:p2"].parent_id == ROOT


def test_alineas_attach_to_the_nearest_open_paragraph():
    spans = spans_of(ALINEAS_UNDER_PARAGRAPH, article="68", norm="ufpi-177-2012")
    root = "ufpi-177-2012:art68"
    assert spans[f"{root}:p1:ala"].parent_id == f"{root}:p1"
    assert "viabilizar as condições" in spans[f"{root}:p1:ala"].text
    assert "§ 2º" not in spans[f"{root}:p1:alb"].text


def test_restarting_incisos_inside_alineas_do_not_abort():
    spans = spans_of(RESTARTING_INCISOS, article="33", norm="ufpi-956-2025")
    incisos = [s for s in spans.values() if s.kind == "inciso"]
    assert len(incisos) == 4
    assert all(s.ambiguous for s in incisos if s.label in {"I", "II"})


def test_conflicting_evidence_for_one_address_keeps_the_first_without_aborting():
    first = chunk("Art. 68. Texto da primeira redação disponível.")
    second = chunk("Art. 68. Texto de outra redação disponível.", id="c2", rank=2)
    references = [reference(first), reference(second)]
    spans = segment_evidence([first, second], references)
    assert spans["ufpi-177-2012:art68"].chunk_id == "c1"


def ambiguous_claim(text):
    quote = "objetivos da disciplina"
    return Claim(
        text=text,
        role="conclusion",
        group=0,
        side=None,
        support=[Support(span_id=f"{ROOT}:p1:incII~2", quote="Il -" + quote + ";")],
    )


def test_ambiguous_span_cannot_satisfy_a_subdivision_mention():
    spans = spans_of(OCR_DUPLICATE)
    verdict = verify_claim(ambiguous_claim("O inciso II exige os objetivos da disciplina."), spans)
    assert "locator_mismatch" in verdict.codes
    plain = verify_claim(ambiguous_claim("O plano deve conter os objetivos da disciplina."), spans)
    assert plain.status == "supported"


def test_ambiguous_span_grants_no_subdivision_permission_to_the_guard():
    spans = spans_of(OCR_DUPLICATE)
    answer = CitedAnswer(
        answer_type="answer",
        claims=[ambiguous_claim("O plano deve conter os objetivos da disciplina.")],
        missing_user_fact=None,
    )
    verdicts = [verify_claim(c, spans, i) for i, c in enumerate(answer.claims)]
    granted = {
        (p.subdivision_type, p.subdivision_value) for p in _permissions([], answer, verdicts, spans)
    }
    assert ("inciso", "II") not in granted
    assert ("paragraph", "1") in granted


SPANS = spans_of(OCR_DUPLICATE)
GOOD = Claim(
    text="O plano deve conter os objetivos do Estágio.",
    role="conclusion",
    group=0,
    side=None,
    support=[Support(span_id=f"{ROOT}:p1:incIV", quote="IV -objetivos do Estágio;")],
)


@pytest.mark.parametrize(
    "role,expected",
    [
        ("condition", "partial"),
        ("exception", "partial"),
        ("deadline", "partial"),
        ("procedure", "partial"),
        ("context", "partial"),
    ],
)
def test_rejected_qualifiers_of_the_conclusion_are_never_silently_omitted(role, expected):
    bad = Claim(
        text="Há exigência adicional sem suporte.", role=role, group=0, side=None, support=[]
    )
    answer = CitedAnswer(answer_type="answer", claims=[GOOD, bad], missing_user_fact=None)
    result = disposition(answer, [verify_claim(c, SPANS, i) for i, c in enumerate(answer.claims)])
    assert verify_claim(GOOD, SPANS).status == "supported"
    assert result.action == expected
    assert bad.text not in result.body
    if role in {"condition", "exception", "deadline"}:
        assert result.caveats and "load_bearing_claim_rejected" in result.codes
    else:
        assert result.body.endswith(PARTIAL_NOTICE)


def test_schema_can_constrain_span_ids_and_answer_type():
    from rag_baseline.citation_contracts import cited_answer_schema

    schema = cited_answer_schema(span_ids=["b:art1", "a:art1:caput"], answer_types=["answer"])
    support = schema["$defs"]["Support"]["properties"]["span_id"]
    assert support["enum"] == ["a:art1:caput", "b:art1"]
    assert schema["properties"]["answer_type"]["enum"] == ["answer"]
    for model in [schema, *schema["$defs"].values()]:
        assert set(model["required"]) == set(model["properties"])
        assert model["additionalProperties"] is False
    # Without constraints the schema is unchanged.
    assert "enum" not in cited_answer_schema()["$defs"]["Support"]["properties"]["span_id"]
    assert cited_answer_schema(span_ids=[]) == cited_answer_schema()


@pytest.mark.asyncio
async def test_generation_constrains_span_ids_and_repair_keeps_answer_type():
    from tests.rag_baseline.test_cited_generation import Client, claim, generate, payload

    bad = claim(text="O prazo é de 99 dias.", role="deadline")
    client = Client(payload(claim(), bad), payload(claim(role="deadline")))
    await generate(client)
    first, repair = (call["schema"] for call in client.calls)
    eligible = first["$defs"]["Support"]["properties"]["span_id"]["enum"]
    assert eligible == ["fato:1", "ufpi-177-2012:art68", "ufpi-177-2012:art68:caput"]
    assert repair["properties"]["answer_type"]["enum"] == ["answer"]
    assert (
        "enum" not in first["properties"]["answer_type"]
        or len(first["properties"]["answer_type"]["enum"]) == 3
    )


def test_instruction_keeps_locators_out_of_claim_text_and_bounds_abstention():
    from rag_baseline.cited_generation import CITED_INSTRUCTION

    assert "não mencione números de artigos" in CITED_INSTRUCTION
    assert "somente se nenhum span" in CITED_INSTRUCTION


def test_instruction_does_not_let_generation_reopen_the_resolved_level():
    from rag_baseline.cited_generation import CITED_INSTRUCTION

    assert "nível de ensino já foi decidido pelo pipeline" in CITED_INSTRUCTION


def test_schema_generates_claims_before_classifying_the_answer():
    from rag_baseline.citation_contracts import cited_answer_schema

    assert list(cited_answer_schema()["properties"]) == [
        "claims",
        "answer_type",
        "missing_user_fact",
    ]


@pytest.mark.asyncio
async def test_prompt_states_the_level_resolved_from_the_evidence():
    from tests.rag_baseline.test_cited_generation import Client, claim, generate, payload

    text = "Art. 68. O recurso deve ser apresentado em 10 dias úteis."
    client = Client(payload(claim()))
    await generate(client, chunk(text, sector="graduacao"))
    assert "NÍVEL RESOLVIDO PELO PIPELINE: graduação" in client.calls[0]["user_prompt"]
    # Without a single resolved sector nothing is asserted about the level.
    client = Client(payload(claim()))
    await generate(client, chunk(text))
    assert "NÍVEL RESOLVIDO" not in client.calls[0]["user_prompt"]


def test_verified_claims_prevail_over_an_insufficient_label():
    answer = CitedAnswer(answer_type="insufficient", claims=[GOOD], missing_user_fact="x")
    result = disposition(answer, [verify_claim(GOOD, SPANS, 0)])
    assert result.action == "accepted"
    assert "insufficient_label_overridden_by_verified_claims" in result.codes
    assert result.body == GOOD.text
    empty = CitedAnswer(answer_type="insufficient", claims=[], missing_user_fact=None)
    assert disposition(empty, []).action == "insufficient"
    # A label cannot rescue claims that were not verified.
    bad = GOOD.model_copy(update={"support": []})
    unverified = CitedAnswer(answer_type="insufficient", claims=[bad], missing_user_fact=None)
    assert disposition(unverified, [verify_claim(bad, SPANS, 0)]).action == "insufficient"


@pytest.mark.asyncio
async def test_cited_generation_has_its_own_output_budget():
    from rag_baseline.cited_generation import CITED_MAX_TOKENS
    from tests.rag_baseline.test_cited_generation import Client, claim, generate, payload

    client = Client(payload(claim()))
    await generate(client)
    assert client.calls[0]["max_tokens"] == CITED_MAX_TOKENS == 3200


def test_structured_chat_max_tokens_defaults_to_the_client_setting():
    import inspect

    from rag_baseline.openrouter import OpenRouterClient

    parameter = inspect.signature(OpenRouterClient.structured_chat).parameters["max_tokens"]
    assert parameter.default is None


ART36 = (
    "Art. 36. O aproveitamento de estudos é autorizado pelo Colegiado Simples.\n"
    "§ 1º O aproveitamento (caput) é autorizado quando:\n"
    "I - a disciplina cursada tiver conteúdo e duração idênticos;\n"
    "II - os estudos realizados em duas ou mais disciplinas se complementarem;\n"
    "III - os estudos, embora não atendendo aos incisos I e II, guardarem afinidade com a área."
)


def test_cross_reference_inside_the_claims_own_quote_is_quoted_content():
    # Res. 956/2025, art. 36, § 1º, III refers to its sibling incisos.
    spans = spans_of(ART36, article="36", norm="ufpi-956-2025")
    quote = "os estudos, embora não atendendo aos incisos I e II, guardarem afinidade com a área"
    span = "ufpi-956-2025:art36:p1:incIII"
    quoted = Claim(
        text="É autorizado quando os estudos, embora não atendendo aos incisos I e II, "
        "guardarem afinidade com a área.",
        role="condition",
        group=0,
        side=None,
        support=[Support(span_id=span, quote=quote)],
    )
    assert verify_claim(quoted, spans).status == "supported"
    # The same mention outside the quotation is still an attribution to check.
    asserted = Claim(
        text="Pelo inciso II, os estudos guardarem afinidade com a área.",
        role="condition",
        group=0,
        side=None,
        support=[Support(span_id=span, quote=quote)],
    )
    assert "locator_mismatch" in verify_claim(asserted, spans).codes


@pytest.mark.asyncio
async def test_quoted_reference_to_an_unretrieved_article_is_still_blocked_by_the_guard():
    from tests.rag_baseline.test_cited_generation import Client, generate, payload

    text = "Art. 68. A média final, depois do cálculo definido no Art. 117, é 6 (seis)."
    quote = "A média final, depois do cálculo definido no Art. 117, é 6 (seis)."
    item = Claim(
        text=quote,
        role="conclusion",
        group=0,
        side=None,
        support=[Support(span_id="ufpi-177-2012:art68:caput", quote=quote)],
    )
    result = await generate(Client(payload(item), payload(item)), chunk(text))
    first = result.citation_audit["first_verdicts"][0]["codes"]
    assert "locator_mismatch" not in first
    assert any(code.startswith("guard:") for code in first)
    assert result.citation_audit["action"] == "fallback"


@pytest.mark.asyncio
async def test_repair_never_silently_drops_a_rejected_qualifier():
    from tests.rag_baseline.test_cited_generation import Client, claim, generate, payload

    bad_condition = claim(text="Só vale em 99 dias.", role="condition")
    first = payload(claim(), bad_condition)
    # The repair returns a different count and no condition at all.
    repair = payload(claim(role="context"), claim(role="context"))
    result = await generate(Client(first, repair))
    assert result.citation_audit["action"] == "partial"
    assert bad_condition.text not in result.answer
    assert result.citation_audit["caveats"]
    assert "load_bearing_claim_rejected" in result.citation_audit["disposition_codes"]
    assert result.citation_audit["repair"]["unmatched_rejected"] == [1]
