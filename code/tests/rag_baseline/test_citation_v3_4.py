"""Regressions for attribution, polarity and safe deterministic delivery."""

import re

import pytest

from rag_baseline.citation_contracts import CitationAudit, Support, cited_answer_schema
from rag_baseline.citation_verifier import compose_claims, disposition, snap_quote, verify_claim
from rag_baseline.cited_generation import _evaluate, _permissions, generate_cited
from rag_baseline.content_locators import ContentLocatorPolicy
from rag_baseline.evidence_spans import segment_evidence, temporal_fact_spans
from rag_baseline.grounding import KnownRelation
from rag_baseline.normative_output import FALLBACK_BODY, normative_references
from tests.rag_baseline.test_citation_side_coverage import (
    GRAD_CLAIM,
    POS_CLAIM,
    graduation,
    postgraduate,
)
from tests.rag_baseline.test_citation_temporal import chunk, grounding, relation
from tests.rag_baseline.test_citation_v3_3 import answer, claim
from tests.rag_baseline.test_citation_verifier import claim as deadline_claim
from tests.rag_baseline.test_cited_generation import Client, service


def spans_for(*chunks):
    temporal = grounding(list(chunks))
    return segment_evidence(list(chunks), normative_references(list(chunks), temporal))


@pytest.mark.parametrize("make_chunk", [graduation, postgraduate])
def test_segment_evidence_carries_sector_on_every_structural_span(make_chunk):
    c = make_chunk().model_copy(
        update={"content": "Art. 7. Texto inicial.\n§ 1º Texto subordinado."}
    )
    spans = spans_for(c)
    assert {s.kind for s in spans.values()} == {"article", "caput", "paragraph"}
    assert all(s.sector == c.sector for s in spans.values())


@pytest.mark.parametrize("item", [GRAD_CLAIM, POS_CLAIM])
def test_swapped_comparison_sides_are_rejected(item):
    swapped = item.model_copy(
        update={"side": "pos_graduacao" if item.side == "graduacao" else "graduacao"}
    )
    assert "side_mismatch" in verify_claim(swapped, spans_for(graduation(), postgraduate())).codes


def test_norm_side_must_match_all_non_fact_support():
    item = GRAD_CLAIM.model_copy(update={"side": postgraduate().norm_id})
    assert "side_mismatch" in verify_claim(item, spans_for(graduation())).codes


def test_graduation_claim_cannot_use_only_postgraduate_evidence():
    item = POS_CLAIM.model_copy(
        update={"text": "Na graduação, o discente apresenta o pedido.", "side": None}
    )
    assert "level_mismatch" in verify_claim(item, spans_for(postgraduate())).codes


@pytest.mark.parametrize(
    "level", ["pós-graduação", "pós graduação", "stricto sensu", "mestrado", "doutorado"]
)
def test_postgraduate_mentions_do_not_count_as_graduation(level):
    item = POS_CLAIM.model_copy(
        update={"text": f"No {level}, o discente apresenta o pedido.", "side": None}
    )
    assert verify_claim(item, spans_for(postgraduate())).status == "supported"
    wrong = GRAD_CLAIM.model_copy(update={"text": item.text, "side": None})
    assert "level_mismatch" in verify_claim(wrong, spans_for(graduation())).codes


def test_each_mentioned_level_needs_its_own_evidence():
    item = POS_CLAIM.model_copy(
        update={"text": "Na graduação e no mestrado, o discente apresenta o pedido.", "side": None}
    )
    assert "level_mismatch" in verify_claim(item, spans_for(postgraduate())).codes


@pytest.mark.parametrize(
    "text", ["Na pós-graduação, o discente apresenta o pedido.", "O discente apresenta o pedido."]
)
def test_postgraduate_and_unscoped_claims_remain_supported(text):
    item = POS_CLAIM.model_copy(update={"text": text, "side": None})
    assert verify_claim(item, spans_for(postgraduate())).status == "supported"


def scoped_deadline(scope, local_quote, other_quote):
    local = chunk("ufpi-956-2025", "15", local_quote).model_copy(update={"sector": "pos_graduacao"})
    other = chunk("ufpi-177-2012", "68", other_quote).model_copy(update={"sector": "graduacao"})
    item = claim(
        f"O trancamento {scope} tem prazo de 10 dias úteis.",
        quote=local_quote,
        span_id=f"{local.norm_id}:art15",
    )
    item.support.append(Support(span_id=f"{other.norm_id}:art68", quote=other_quote))
    return item, spans_for(local, other)


@pytest.mark.parametrize("scope", ["na Resolução 956/2025", "na pós-graduação"])
def test_numbers_cannot_be_borrowed_from_another_norm_or_level(scope):
    item, spans = scoped_deadline(
        scope, "O discente pode solicitar o trancamento.", "O prazo é de 10 (dez) dias úteis."
    )
    assert "number_not_in_quotes" in verify_claim(item, spans).codes


@pytest.mark.parametrize("scope", ["na Resolução 956/2025", "na pós-graduação"])
def test_deadline_qualifiers_cannot_be_borrowed_from_another_norm_or_level(scope):
    item, spans = scoped_deadline(
        scope, "O prazo é de 10 dias corridos.", "O prazo é de 10 dias úteis."
    )
    assert "deadline_qualifier_mismatch" in verify_claim(item, spans).codes


def test_side_alone_scopes_numeric_quotes():
    item, spans = scoped_deadline(
        "", "O prazo é de 10 dias corridos.", "O prazo é de 10 dias úteis."
    )
    item.side = "pos_graduacao"
    assert "deadline_qualifier_mismatch" in verify_claim(item, spans).codes


def test_unscoped_claim_keeps_union_of_its_quotes():
    item, spans = scoped_deadline(
        "", "O discente pode solicitar o trancamento.", "O prazo é de 10 dias úteis."
    )
    assert verify_claim(item, spans).status == "supported"


@pytest.mark.parametrize(
    "marker",
    [
        "não",
        "nunca",
        "nenhum",
        "nenhuma",
        "nem",
        "vedado",
        "vedada",
        "vedados",
        "vedadas",
        "vedação",
        "proibido",
        "proibida",
        "proibidos",
        "proibidas",
        "impedido",
        "impedida",
    ],
)
def test_negation_added_to_affirmative_quote_is_rejected(marker):
    item = claim(f"{marker} o pedido pode ser apresentado.")
    assert "negation_added" in verify_claim(item, spans_for(graduation())).codes


@pytest.mark.parametrize("text", ["Não se recebe o pedido.", "O pedido pode ser apresentado."])
def test_negation_in_quote_is_allowed_without_reverse_enforcement(text):
    quote = "A coordenação não recebe o pedido por escrito."
    c = graduation().model_copy(update={"content": quote})
    assert verify_claim(claim(text, quote=quote), spans_for(c)).status == "supported"


def test_negation_markers_are_whole_words():
    item = claim("A denominação do pedido foi definida.")
    assert verify_claim(item, spans_for(graduation())).status == "supported"


@pytest.mark.parametrize("negative_source", [False, True])
def test_snap_cannot_change_quote_polarity(negative_source):
    affirmative = "A coordenação recebe o pedido por escrito e encaminha a documentação ao colegiado responsável."
    negative = affirmative.replace("recebe", "não recebe")
    source, original = (negative, affirmative) if negative_source else (affirmative, negative)
    spans = spans_for(graduation().model_copy(update={"content": source}))
    candidate, similarity = snap_quote(original, source)
    assert candidate is not None and similarity >= 0.90
    item = claim("O pedido segue as regras previstas.", quote=original)
    audit = CitationAudit()
    verdicts, _, _ = _evaluate(answer(item), spans, [], lambda *_: [], audit, "first")
    assert "quote_not_found" in verdicts[0].codes
    assert item.support[0].quote == original
    assert audit.snapped_quotes == []


def amending_case(role="eligible"):
    c = chunk(
        "ufpi-1056-2026",
        "1",
        "A norma recebe nova redação.\n§ 4º A exceção depende de pedido por escrito.",
    )
    link = KnownRelation(
        relation="AMENDED_BY",
        source_norm="ufpi-177-2012",
        target_norm=c.norm_id,
        target_article="68",
        target_paragraph="4",
        evidence_source=c.source,
        evidence_article="1",
    )
    temporal = grounding([c], [link], roles=[role])
    refs = normative_references([c], temporal)
    _, base = ContentLocatorPolicy.for_generation("Qual é a exceção?", temporal, refs, [c])
    spans = segment_evidence([c], refs)
    item = claim(
        "O § 4º do art. 1 da Resolução 1056/2026 prevê a exceção.",
        quote="A exceção depende de pedido por escrito.",
        span_id=f"{c.norm_id}:art1:p4",
    )
    return c, temporal, base, spans, item


@pytest.mark.parametrize("role", ["eligible", "historical", "posterior"])
def test_verified_quote_cannot_restore_a_locator_rejected_by_policy(role):
    _, temporal, base, spans, item = amending_case(role)
    permitted = _permissions(base, answer(item), [verify_claim(item, spans)], spans, temporal)
    assert not any(
        p.norm_id == "ufpi-1056-2026" and p.subdivision_type == "paragraph" for p in permitted
    )


def test_amending_relation_blocks_only_the_target_norm_and_evidence_article():
    c, temporal, _, spans, item = amending_case()
    link = temporal.known_relations[0]
    verdicts = [verify_claim(item, spans)]
    assert _permissions([], answer(item), verdicts, spans, temporal) == []
    for update in [
        {"evidence_article": "2"},
        {"source_norm": c.norm_id, "target_norm": link.source_norm},
        {"relation": "REVOKED_BY"},
    ]:
        other = temporal.model_copy(update={"known_relations": [link.model_copy(update=update)]})
        assert any(
            p.subdivision_type == "paragraph"
            for p in _permissions([], answer(item), verdicts, spans, other)
        )
    numbered_article = link.model_copy(update={"evidence_article": " 1º"})
    temporal = temporal.model_copy(update={"known_relations": [numbered_article]})
    assert _permissions([], answer(item), verdicts, spans, temporal) == []


@pytest.mark.parametrize("role", ["eligible", "historical", "posterior"])
def test_literal_permission_without_amendment_is_independent_of_temporal_role(role):
    _, temporal, _, spans, item = amending_case()
    temporal = temporal.model_copy(
        update={
            "known_relations": [],
            "evidence_states": [
                state.model_copy(update={"temporal_role": role})
                for state in temporal.evidence_states
            ],
        }
    )
    permitted = _permissions([], answer(item), [verify_claim(item, spans)], spans, temporal)
    assert any(p.subdivision_type == "paragraph" for p in permitted)


@pytest.mark.parametrize("citation_error", ["quote_not_found", "quote_too_short"])
@pytest.mark.asyncio
async def test_citation_failure_stays_ineligible_with_new_rejection(citation_error):
    item = claim("O pedido não será aceito.")
    if citation_error == "quote_not_found":
        item.support[0].quote = "Este texto está completamente ausente."
    elif citation_error == "quote_too_short":
        item.support[0].quote = "A coordenação"
    c = chunk()
    client = Client(answer(item).model_dump_json())
    result = await generate_cited(
        service(client),
        "Como apresentar o pedido?",
        [c],
        context_notice="",
        grounding=grounding([c]),
    )
    assert {citation_error, "negation_added"} <= set(
        result.citation_audit["first_verdicts"][0]["codes"]
    )
    assert result.citation_audit["repair"] is None
    assert result.generation_attempts == 1


@pytest.mark.asyncio
async def test_new_rejection_alone_is_repairable():
    c = chunk()
    client = Client(
        answer(claim("O pedido não será aceito.")).model_dump_json(),
        answer(claim()).model_dump_json(),
    )
    result = await generate_cited(
        service(client),
        "Como apresentar o pedido?",
        [c],
        context_notice="",
        grounding=grounding([c]),
    )
    assert result.citation_audit["first_verdicts"][0]["codes"] == ["negation_added"]
    assert result.citation_audit["action"] == "repaired"
    assert result.generation_attempts == 2


@pytest.mark.parametrize("role", ["eligible", "historical", "posterior"])
@pytest.mark.asyncio
async def test_transcribed_amending_subdivision_is_rejected_by_cited_pipeline(role):
    c, temporal, _, _, item = amending_case(role)
    client = Client(answer(item).model_dump_json(), answer(item).model_dump_json())
    result = await generate_cited(
        service(client), "Qual é a exceção?", [c], context_notice="", grounding=temporal
    )
    assert "guard:unvalidated_subdivision" in result.citation_audit["first_verdicts"][0]["codes"]
    assert item.text not in result.answer


@pytest.mark.parametrize(
    "question",
    [
        "Tenho 30 créditos. Qual é o prazo para recurso?",
        "Tenho trinta créditos. Qual é o prazo para recurso?",
    ],
)
def test_question_number_with_different_unit_does_not_excuse_deadline(question):
    c = chunk("ufpi-177-2012", "68", "O prazo para recurso é de 5 dias úteis.")
    item = deadline_claim("O prazo para recurso é de 30 dias corridos.", quote=c.content)
    codes = verify_claim(item, spans_for(c), question=question).codes
    assert "number_not_in_quotes" in codes
    assert "deadline_qualifier_mismatch" in codes


@pytest.mark.parametrize(
    "claim_text,question,expected",
    [
        ("O prazo é de 30 dias corridos.", "Tenho 30 dias para recorrer?", "supported"),
        ("O discente possui 30 créditos.", "Tenho trinta créditos.", "supported"),
        ("O discente possui 30 vagas.", "Tenho 30 créditos.", "rejected"),
        ("O discente possui 30 créditos.", "Tenho 30 dias.", "rejected"),
    ],
)
def test_user_number_exemptions_require_the_same_unit(claim_text, question, expected):
    assert (
        verify_claim(claim(claim_text), spans_for(graduation()), question=question).status
        == expected
    )


@pytest.mark.parametrize(
    "question",
    [
        "A norma continua em vigor. Qual é seu curso?",
        "Qual é seu curso? A norma continua em vigor.",
        "Qual é seu curso? Qual é seu turno?",
        "Qual é seu curso",
        "Você não concluiu o curso?",
        "Você tem 30 créditos?",
        "Você tem trinta créditos?",
        "Qual é seu curso!",
        "",
    ],
)
@pytest.mark.parametrize("with_claim", [False, True])
def test_missing_user_fact_discards_unverified_statements(question, with_claim):
    items = [claim(role="condition")] if with_claim else []
    final = disposition(
        answer(*items, answer_type="needs_user_fact", missing_user_fact=question),
        [verify_claim(c, spans_for(graduation()), i) for i, c in enumerate(items)],
    )
    assert final.action == "fallback"
    assert final.body == FALLBACK_BODY


def test_single_interrogative_without_numbers_or_negation_is_delivered():
    final = disposition(
        answer(answer_type="needs_user_fact", missing_user_fact="Qual é seu curso?"), []
    )
    assert final.action == "needs_user_fact"
    assert final.body == "Dado necessário: Qual é seu curso?"


@pytest.mark.parametrize(
    "user_request",
    [
        "Informe o curso.",
        "INDIQUE seu curso.",
        "Diga seu curso.",
        "Especifique seu curso.",
        "Esclareça seu curso.",
        "Confirme seu curso.",
        "Selecione seu curso.",
        "Escolha seu curso.",
        "Qual é seu curso?",
        "Qual é o seu curso?",
        "Informe " + "seu " * 23 + "curso.",
    ],
)
def test_single_bounded_user_fact_request_is_delivered(user_request):
    final = disposition(answer(answer_type="needs_user_fact", missing_user_fact=user_request), [])
    assert final.action == "needs_user_fact"
    assert final.body == f"Dado necessário: {user_request}"


@pytest.mark.parametrize(
    "user_request",
    [
        "Em qual semestre você está? O trancamento de matrícula é permitido.",
        "O trancamento de matrícula é permitido.",
        "Qual é a norma aplicável?",
        "Informe o artigo aplicável.",
        "Qual é o dispositivo aplicável?",
        "Informe a Resolução aplicável.",
        "Informe o § aplicável.",
        "Informe seu curso 2.",
        "Informe os trinta créditos.",
        "Informe seu curso não concluído.",
        "Informe " + "seu " * 24 + "curso.",
    ],
)
def test_unsafe_or_overlong_user_fact_request_is_discarded(user_request):
    final = disposition(answer(answer_type="needs_user_fact", missing_user_fact=user_request), [])
    assert final.action == "fallback"
    assert final.body == FALLBACK_BODY


@pytest.mark.parametrize(
    "side",
    [
        "Outro nível",
        "ufpi-1-2000\n",
        "pos_graduacao.\n\nA norma continua em vigor",
        "",
        "UFPI-1-2000",
    ],
)
def test_invalid_side_is_rejected_and_never_rendered(side):
    item = claim(side=side)
    spans = spans_for(graduation())
    verdict = verify_claim(item, spans, 1)
    assert "invalid_side" in verdict.codes
    good = claim()
    final = disposition(answer(good, item), [verify_claim(good, spans), verdict])
    rendered, _ = compose_claims([item], [0])
    assert side + ":" not in rendered
    assert not any(side in caveat for caveat in final.caveats)
    assert final.approved_indices == [0]


@pytest.mark.parametrize(
    "side,expected",
    [
        (None, True),
        ("graduacao", True),
        ("pos_graduacao", True),
        ("ufpi-956-2025", True),
        ("Outro nível", False),
        ("pos_graduacao.\n\nA norma continua em vigor", False),
    ],
)
def test_schema_constrains_side_values(side, expected):
    variants = cited_answer_schema()["$defs"]["Claim"]["properties"]["side"]["anyOf"]

    def accepts(variant):
        if side is None:
            return variant.get("type") == "null"
        return (
            variant.get("type") == "string"
            and ("enum" not in variant or side in variant["enum"])
            and ("pattern" not in variant or re.search(variant["pattern"], side) is not None)
        )

    assert any(accepts(variant) for variant in variants) == expected


def test_temporal_facts_remain_unscoped_and_citable_by_either_side():
    c = graduation()
    facts = temporal_fact_spans(grounding([c], [relation()]))
    fact = facts["fato:1"]
    assert fact.sector is None
    item = claim(fact.text, quote=fact.text, span_id=fact.span_id, side="pos_graduacao")
    assert verify_claim(item, facts).status == "supported"


@pytest.mark.parametrize("side", [None, "pos_graduacao"])
@pytest.mark.parametrize(
    "document",
    ["diploma de Graduação", "histórico escolar final da Graduação", "formação na graduação"],
)
def test_quoted_graduation_requirement_in_postgraduate_evidence_is_supported(document, side):
    text = f"O candidato deve apresentar o {document} no ato da matrícula."
    c = postgraduate().model_copy(update={"content": text})
    item = claim(text, quote=text, span_id=f"{c.norm_id}:art15", side=side)
    assert verify_claim(item, spans_for(c)).status == "supported"


@pytest.mark.parametrize(
    "expression", ["pós-graduação", "pós graduação", "stricto sensu", "mestrado", "doutorado"]
)
def test_each_quoted_postgraduate_expression_is_ignored_in_level_detection(expression):
    text = f"O candidato deve apresentar o diploma de {expression} na matrícula."
    c = graduation().model_copy(update={"content": text})
    item = claim(text, quote=text)
    assert verify_claim(item, spans_for(c)).status == "supported"


def test_unquoted_graduation_grade_requirement_still_rejects_postgraduate_evidence():
    quote = "A aprovação exige nota mínima sete."
    c = postgraduate().model_copy(update={"content": quote})
    item = claim(
        "Na graduação, a aprovação exige nota mínima sete.",
        quote=quote,
        span_id=f"{c.norm_id}:art15",
    )
    assert "level_mismatch" in verify_claim(item, spans_for(c)).codes


@pytest.mark.parametrize(
    "text,quote",
    [
        ("O diploma de mestrado deve ser apresentado.", "O diploma de doutorado é exigido."),
        ("Na pós-graduação, o diploma é exigido.", "O diploma de Graduação é exigido."),
    ],
)
def test_a_quoted_level_does_not_exempt_a_different_expression(text, quote):
    c = graduation().model_copy(update={"content": quote})
    assert "level_mismatch" in verify_claim(claim(text, quote=quote), spans_for(c)).codes


def test_quoted_level_still_scopes_numbers_and_deadline_qualifiers():
    text = "O diploma de Graduação deve ser apresentado em 10 dias úteis."
    c = postgraduate().model_copy(update={"content": text})
    item = claim(text, quote=text, span_id=f"{c.norm_id}:art15")
    codes = verify_claim(item, spans_for(c)).codes
    assert "level_mismatch" not in codes
    assert "number_not_in_quotes" in codes
    assert "deadline_qualifier_mismatch" in codes
    item.side = "pos_graduacao"
    assert verify_claim(item, spans_for(c)).status == "supported"


def test_quoted_level_does_not_override_an_explicit_side():
    text = "O candidato deve apresentar o diploma de Graduação na matrícula."
    c = postgraduate().model_copy(update={"content": text})
    item = claim(text, quote=text, span_id=f"{c.norm_id}:art15", side="graduacao")
    assert "side_mismatch" in verify_claim(item, spans_for(c)).codes


@pytest.mark.parametrize("expression", ["pós-graduação", "pós graduação"])
def test_quoted_postgraduate_word_does_not_exempt_graduation(expression):
    quote = f"Nos programas de {expression}, a aprovação exige nota mínima sete."
    c = postgraduate().model_copy(update={"content": quote})
    item = claim(
        "Na graduação, a aprovação exige nota mínima sete.",
        quote=quote,
        span_id=f"{c.norm_id}:art15",
    )
    assert "level_mismatch" in verify_claim(item, spans_for(c)).codes


def test_quoted_level_expression_requires_whole_word_match():
    quote = "O título de mestrados deve ser informado no pedido."
    item = claim("No mestrado, o título deve ser informado.", quote=quote)
    c = graduation().model_copy(update={"content": quote})
    assert "level_mismatch" in verify_claim(item, spans_for(c)).codes


@pytest.mark.parametrize(
    "local_quote",
    [
        "Os programas de pós-graduação recebem o pedido de trancamento.",
        "Na pós-graduação o prazo é de 10 dias corridos.",
    ],
)
def test_quoted_postgraduate_scope_cannot_borrow_graduation_deadline(local_quote):
    item, spans = scoped_deadline(
        "na pós-graduação", local_quote, "O prazo é de 10 (dez) dias úteis."
    )
    codes = verify_claim(item, spans).codes
    assert "deadline_qualifier_mismatch" in codes
    if "10" not in local_quote:
        assert "number_not_in_quotes" in codes


@pytest.mark.parametrize(
    "user_request",
    [
        "Informe seu curso\nO trancamento é permitido a qualquer tempo",
        "Informe seu curso; o trancamento é permitido a qualquer tempo",
        "Informe seu curso, pois o trancamento é sempre permitido",
        "Você sabia que o trancamento é sempre permitido?",
        "Informe seu curso\rregular.",
        "Informe seu curso\nregular.",
        "Informe seu curso; turno.",
        "Informe seu curso: turno.",
        "Informe seu curso, POIS precisamos desse dado.",
        "Informe seu curso porque precisamos desse dado.",
        "Informe seu curso, já que precisamos desse dado.",
        "Informe seu curso, uma vez que precisamos desse dado.",
        "Qual é o curso permitido?",
        "Qual é o curso proibido?",
        "Qual é a matrícula vedada?",
        "Qual é o curso obrigatório?",
        "Qual curso você sempre frequenta?",
    ],
)
def test_missing_user_fact_rejects_embedded_explanations_or_normative_terms(user_request):
    final = disposition(answer(answer_type="needs_user_fact", missing_user_fact=user_request), [])
    assert final.action == "fallback"
    assert final.body == FALLBACK_BODY


def test_provider_side_schema_has_no_lookaround():
    variants = cited_answer_schema()["$defs"]["Claim"]["properties"]["side"]["anyOf"]
    pattern = next(v["pattern"] for v in variants if v.get("type") == "string")
    assert not any(token in pattern for token in ("(?=", "(?!", "(?<=", "(?<!"))


@pytest.mark.parametrize(
    "old_code", ["unknown_span", "no_support", "empty_claim", "locator_mismatch"]
)
@pytest.mark.parametrize("bad_quote", [False, True])
@pytest.mark.asyncio
async def test_old_repair_rejections_remain_eligible(old_code, bad_quote):
    item = claim("O pedido não será aceito.")
    if bad_quote:
        item.support[0].quote = "Este texto está completamente ausente."
    if old_code == "unknown_span":
        item.support[0].span_id = "unknown"
    elif old_code == "no_support":
        item.support = []
    elif old_code == "empty_claim":
        item.text = ""
    else:
        item.text = "O art. 99 prevê o pedido."
    c = chunk()
    client = Client(answer(item).model_dump_json(), answer(claim()).model_dump_json())
    result = await generate_cited(
        service(client),
        "Como apresentar o pedido?",
        [c],
        context_notice="",
        grounding=grounding([c]),
    )
    assert old_code in result.citation_audit["first_verdicts"][0]["codes"]
    assert result.generation_attempts == 2
    assert result.citation_audit["repair"] is not None
    assert result.citation_audit["action"] == "repaired"


@pytest.mark.parametrize(
    "new_code,text,side",
    [
        ("negation_added", "O pedido não será aceito.", None),
        ("level_mismatch", "No mestrado, o pedido pode ser apresentado.", None),
        ("side_mismatch", "O pedido pode ser apresentado.", "pos_graduacao"),
        ("invalid_side", "O pedido pode ser apresentado.", "outro"),
    ],
)
@pytest.mark.parametrize(
    "quote,quote_code",
    [
        ("Este texto está completamente ausente.", "quote_not_found"),
        ("A coordenação", "quote_too_short"),
    ],
)
@pytest.mark.asyncio
async def test_new_rejection_does_not_make_a_bad_quote_repairable(
    new_code, text, side, quote, quote_code
):
    c = graduation()
    item = claim(text, side=side, quote=quote)
    result = await generate_cited(
        service(Client(answer(item).model_dump_json())),
        "Como apresentar o pedido?",
        [c],
        context_notice="",
        grounding=grounding([c]),
    )
    assert {new_code, quote_code} <= set(result.citation_audit["first_verdicts"][0]["codes"])
    assert result.generation_attempts == 1
    assert result.citation_audit["repair"] is None


@pytest.mark.asyncio
async def test_discarded_user_fact_guard_has_its_own_audit_phase():
    missing = "A norma está em vigor."
    c = graduation()
    result = await generate_cited(
        service(
            Client(
                answer(answer_type="needs_user_fact", missing_user_fact=missing).model_dump_json()
            )
        ),
        "Qual é a regra?",
        [c],
        context_notice="",
        grounding=grounding([c]),
    )
    violations = [
        v
        for v in result.citation_audit["guard_violations"]
        if v["code"] == "unsupported_current_validity"
    ]
    assert violations
    assert all(v["phase"] == "discarded_missing_user_fact" for v in violations)
    assert missing not in result.answer
