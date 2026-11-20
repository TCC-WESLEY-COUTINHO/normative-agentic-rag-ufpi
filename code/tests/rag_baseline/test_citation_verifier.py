import pytest

from rag_baseline.citation_contracts import CitedAnswer, Claim, Support, cited_answer_schema
from rag_baseline.citation_verifier import PARTIAL_NOTICE, disposition, verify_claim
from rag_baseline.evidence_spans import segment_chunk
from rag_baseline.normative_output import FALLBACK_BODY
from tests.rag_baseline.test_evidence_spans import chunk

ROOT = "ufpi-177-2012:art68"
TEXT = "Art. 68. O recurso deve ser apresentado em 10 dias úteis.\n§ 2º A coordenação recebe o pedido por escrito."
SPANS = {s.span_id: s for s in segment_chunk(chunk(TEXT), "ufpi-177-2012")}


def claim(
    text="O recurso deve ser apresentado em 10 dias úteis.",
    quote="O recurso deve ser apresentado em 10 dias úteis.",
    span_id=ROOT,
    role="conclusion",
    group=0,
    side=None,
):
    return Claim(
        text=text,
        role=role,
        group=group,
        side=side,
        support=[Support(span_id=span_id, quote=quote)],
    )


@pytest.mark.parametrize(
    "item,code",
    [
        (claim().model_copy(update={"support": []}), "no_support"),
        (claim(span_id="excluded"), "unknown_span"),
        (claim(quote="O recurso"), "quote_too_short"),
        (claim(quote="O estudante apresenta outro documento."), "quote_not_found"),
        (claim(text="O prazo é de onze dias úteis."), "number_not_in_quotes"),
        (
            claim(text="O recurso deve ser apresentado em 10 dias corridos."),
            "deadline_qualifier_mismatch",
        ),
        (claim(text="O recurso deve ser apresentado em 10 dias."), "deadline_qualifier_mismatch"),
        (claim(text="O art. 69 prevê o recurso."), "locator_mismatch"),
        (claim(text="O § 2º prevê o pedido."), "locator_mismatch"),
    ],
)
def test_rejections(item, code):
    assert code in verify_claim(item, SPANS).codes


@pytest.mark.parametrize(
    "item",
    [
        claim(),
        claim(text="O art. 68 da Resolução 177/2012 prevê recurso em dez dias úteis."),
        claim(
            text="O § 2º do art. 68 prevê pedido por escrito.",
            quote="A coordenação recebe o pedido por escrito.",
            span_id=ROOT + ":p2",
        ),
    ],
)
def test_supported(item):
    assert verify_claim(item, SPANS).status == "supported"


def test_normalization_and_reverse_deadline_qualification():
    spans = {
        s.span_id: s
        for s in segment_chunk(
            chunk(
                "Art. 68. A “coordenação” recebe — o pedido por escrito.\n$ 2º O prazo para recurso é de 10 dias."
            ),
            "ufpi-177-2012",
        )
    }
    assert (
        verify_claim(
            claim(
                text="A coordenação recebe o pedido.",
                quote='A "COORDENACAO" recebe -\n o pedido por escrito.',
            ),
            spans,
        ).status
        == "supported"
    )
    assert verify_claim(
        claim(
            text="O § 2º fixa o prazo de 10 dias úteis.",
            quote="§ 2º O prazo para recurso é de 10 dias.",
            span_id=ROOT + ":p2",
        ),
        spans,
    ).codes == ["deadline_qualifier_mismatch"]


@pytest.mark.parametrize(
    "kind,items,expected",
    [
        ("answer", [], "fallback"),
        ("answer", [claim().model_copy(update={"support": []})], "fallback"),
        ("answer", [claim(), claim(role="context").model_copy(update={"support": []})], "partial"),
        ("insufficient", [], "insufficient"),
        # A verified claim is not discarded by the label.
        ("insufficient", [claim()], "accepted"),
        ("needs_user_fact", [claim(role="condition")], "needs_user_fact"),
    ],
)
def test_disposition(kind, items, expected):
    answer = CitedAnswer(answer_type=kind, claims=items, missing_user_fact="Qual é o curso?")
    result = disposition(answer, [verify_claim(c, SPANS, i) for i, c in enumerate(items)])
    assert result.action == expected
    if expected == "fallback":
        assert result.body == FALLBACK_BODY
    if expected == "partial":
        assert result.body.endswith(PARTIAL_NOTICE)
    if expected == "insufficient":
        assert "10" not in result.body
    if expected == "needs_user_fact":
        assert "Qual é o curso?" in result.body


def test_strict_schema():
    schema = cited_answer_schema()
    for model in [schema, *schema["$defs"].values()]:
        assert set(model["required"]) == set(model["properties"])
        assert model["additionalProperties"] is False
    assert {"type": "null"} in schema["properties"]["missing_user_fact"]["anyOf"]


@pytest.mark.parametrize(
    "kind,claim_qualifier,quote_qualifier,expected",
    [
        ("digits", "", "", "supported"),
        ("digits", " úteis", " úteis", "supported"),
        ("words", " corridos", " corridos", "supported"),
        ("words", " letivos", " letivos", "supported"),
        ("words", "", " letivos", "rejected"),
        ("digits", " úteis", "", "rejected"),
        ("digits", " letivos", " corridos", "rejected"),
    ],
)
def test_deadline_qualification(kind, claim_qualifier, quote_qualifier, expected):
    text = f"Art. 68. O prazo de recurso é de 10 dias{quote_qualifier}."
    spans = {s.span_id: s for s in segment_chunk(chunk(text), "ufpi-177-2012")}
    item = claim(
        text=f"O prazo é de {'dez' if kind == 'words' else '10'} dias{claim_qualifier}.", quote=text
    )
    assert verify_claim(item, spans).status == expected


@pytest.mark.parametrize(
    "text",
    [
        "A Resolução 999/2025 prevê recurso.",
        "O art. 68 da Resolução 999/2025 prevê recurso.",
        "O inciso II prevê recurso.",
        "A alínea a prevê recurso.",
    ],
)
def test_locators_must_belong_to_this_claims_support(text):
    assert "locator_mismatch" in verify_claim(claim(text=text), SPANS).codes


def test_numbers_cannot_borrow_quotes_from_another_claim_or_span_text():
    a = claim(
        text="O prazo é de 10 dias úteis.",
        quote="A coordenação recebe o pedido por escrito.",
        span_id=ROOT + ":p2",
    )
    assert "number_not_in_quotes" in verify_claim(a, SPANS).codes
    b = claim(text="Há 177 vagas para recurso.")
    assert "number_not_in_quotes" in verify_claim(b, SPANS).codes


def test_compound_number_does_not_authorize_its_parts():
    spans = {
        s.span_id: s
        for s in segment_chunk(chunk("Art. 68. O limite é de vinte e um pedidos."), "ufpi-177-2012")
    }
    assert (
        verify_claim(
            claim(text="O limite é de 21 pedidos.", quote="O limite é de vinte e um pedidos."),
            spans,
        ).status
        == "supported"
    )
    assert (
        "number_not_in_quotes"
        in verify_claim(
            claim(text="O limite é de 20 pedidos.", quote="O limite é de vinte e um pedidos."),
            spans,
        ).codes
    )


def test_each_support_must_be_verified_even_if_another_is_valid():
    item = claim()
    item.support.append(Support(span_id=ROOT + ":p2", quote="Este trecho não consta da evidência."))
    assert "quote_not_found" in verify_claim(item, SPANS).codes


@pytest.mark.parametrize(
    "words,digits",
    [
        ("cento e vinte e cinco", "125"),
        ("duzentos", "200"),
        ("dois mil e dez", "2010"),
        ("um milhão", "1.000.000"),
        ("zero", "0"),
    ],
)
def test_extended_numerals(words, digits):
    text = f"Art. 68. O limite é de {words} pedidos."
    spans = {s.span_id: s for s in segment_chunk(chunk(text), "ufpi-177-2012")}
    assert (
        verify_claim(claim(text=f"O limite é de {digits} pedidos.", quote=text), spans).status
        == "supported"
    )
    assert (
        "number_not_in_quotes"
        in verify_claim(claim(text=f"O limite é de {words} pedidos.", quote=TEXT), SPANS).codes
    )


def test_empty_conclusion_cannot_be_accepted():
    assert verify_claim(claim(text="  "), SPANS).codes == ["empty_claim"]


@pytest.mark.parametrize(
    "source,target", [("corrido", "letivo"), ("corrido", ""), ("útil", "corrido"), ("", "útil")]
)
def test_singular_deadline_qualifiers_are_preserved(source, target):
    text = f"Art. 68. O recurso tem prazo de 1 dia {source}."
    spans = {s.span_id: s for s in segment_chunk(chunk(text), "ufpi-177-2012")}
    item = claim(text=f"O recurso tem prazo de 1 dia {target}.", quote=text)
    assert "deadline_qualifier_mismatch" in verify_claim(item, spans).codes


@pytest.mark.parametrize("number", ["dez (10)", "10 (dez)"])
def test_parenthesized_deadline_cannot_borrow_qualifier_from_uncited_text(number):
    text = "Art. 68. O recurso tem prazo de 10 dias úteis. A revisão tem prazo de 10 dias corridos."
    spans = {s.span_id: s for s in segment_chunk(chunk(text), "ufpi-177-2012")}
    item = claim(
        text=f"O recurso tem prazo de {number} dias corridos.",
        quote="O recurso tem prazo de 10 dias úteis.",
    )
    assert "deadline_qualifier_mismatch" in verify_claim(item, spans).codes


def test_deadline_qualifier_without_explicit_number_still_requires_own_quote():
    item = claim(text="O prazo é contado em dias corridos.")
    assert "deadline_qualifier_mismatch" in verify_claim(item, SPANS).codes


def test_ocr_normalization_uses_the_same_line_prefixes_as_segmentation():
    spans = {
        s.span_id: s
        for s in segment_chunk(
            chunk(
                "Art. 68. Texto do caput.\n> 1. S$ 2º A coordenação recebe o pedido por escrito."
            ),
            "ufpi-177-2012",
        )
    }
    item = claim(
        text="O § 2º prevê pedido por escrito.",
        quote="§ 2º A coordenação recebe o pedido por escrito.",
        span_id=ROOT + ":p2",
    )
    assert verify_claim(item, spans).status == "supported"
