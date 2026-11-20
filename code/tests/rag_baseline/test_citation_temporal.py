import pytest

from rag_baseline import evidence_spans
from rag_baseline.citation_contracts import CitedAnswer, Claim, Support
from rag_baseline.citation_verifier import verify_claim
from rag_baseline.cited_generation import _permissions, generate_cited
from rag_baseline.evidence_spans import segment_chunk
from rag_baseline.grounding import (
    EvidenceState,
    GenerationConstraints,
    KnownRelation,
    TemporalGroundingContext,
)
from rag_baseline.models import RetrievedChunk
from rag_baseline.normative_output import (
    FALLBACK_BODY,
    allowed_temporal_facts,
    norm_name,
    render_temporal_statements,
)
from rag_baseline.output_contracts import AllowedTemporalFacts, TemporalFact
from tests.rag_baseline.test_cited_generation import Client, service

BASE = "ufpi-901-2031"
LATER = "ufpi-902-2033"
OTHER = "ufpi-903-2035"
QUOTE = "A coordenação recebe o pedido por escrito."


def chunk(norm=BASE, article="7", text=QUOTE, rank=1):
    return RetrievedChunk(
        id=f"{norm}-{article}",
        norm_id=norm,
        content=f"Art. {article}. {text}",
        source=norm_name(norm),
        article_number=article,
        article_label=f"Art. {article}",
        original_index=0,
        distance=None,
        rank=rank,
    )


def relation(kind="AMENDED_BY", article="7", paragraph="3"):
    return KnownRelation(
        relation=kind,
        source_norm=BASE,
        target_norm=LATER,
        target_article=article,
        target_paragraph=paragraph,
        evidence_source=norm_name(LATER),
        evidence_article="15",
    )


def grounding(chunks, relations=(), roles=(), unknown=True):
    return TemporalGroundingContext(
        temporal_intent="indeterminate",
        requested_time_context={},
        known_relations=list(relations),
        evidence_states=[
            EvidenceState(
                chunk_id=c.id,
                source_norm=c.norm_id,
                source_article=c.article_number,
                temporal_action="historical_preserved" if roles else "kept",
                normative_status="desconhecida" if unknown else "vigente",
                temporal_role=roles[i] if roles else "eligible",
            )
            for i, c in enumerate(chunks)
        ],
        generation_constraints=GenerationConstraints(
            **{
                name: True
                for name, field in GenerationConstraints.model_fields.items()
                if field.annotation is bool
            },
            citation_granularity_ceiling="article",
        ),
    )


def claim(text="A coordenação recebe o pedido.", quote=QUOTE, span_id=f"{BASE}:art7"):
    return Claim(
        text=text,
        role="conclusion",
        group=0,
        side=None,
        support=[Support(span_id=span_id, quote=quote)],
    )


def payload(item):
    return CitedAnswer(
        claims=[item], answer_type="answer", missing_user_fact=None
    ).model_dump_json()


def facts(temporal):
    return evidence_spans.temporal_fact_spans(temporal)


async def generate(client, chunks, temporal, question="Como apresentar o pedido?"):
    return await generate_cited(
        service(client, generation_mode="cited_v3"),
        question,
        chunks,
        context_notice="",
        grounding=temporal,
    )


@pytest.mark.parametrize("kind", ["AMENDED_BY", "REVOKED_BY"])
def test_registry_facts_use_application_text_and_stable_addresses(kind):
    c = chunk()
    temporal = grounding([c], [relation(kind)])
    spans = facts(temporal)
    rendered = render_temporal_statements(
        AllowedTemporalFacts(items=[TemporalFact(kind=kind, norm_id=BASE, target_norm=LATER)])
    )
    assert list(spans) == ["fato:1", "fato:2"]
    assert spans == facts(temporal)
    assert spans["fato:1"].kind == "fact"
    assert spans["fato:1"].text == (
        rendered + "\nDispositivo alterado: art. 7, § 3 da Resolução 901/2031."
    )
    status = AllowedTemporalFacts(items=[TemporalFact(kind="STATUS_UNKNOWN", norm_id=BASE)])
    assert spans["fato:2"].text == render_temporal_statements(status)


def test_fact_ids_are_independent_of_relation_and_state_order():
    chunks = [chunk(), chunk(LATER, "15", rank=2)]
    relations = [relation(), relation("REVOKED_BY", None, None)]
    a = grounding(chunks, relations)
    b = grounding(list(reversed(chunks)), list(reversed(relations)))
    assert facts(a) == facts(b)
    assert len(facts(a)) == 4


@pytest.mark.parametrize("kind", ["AMENDED_BY", "REVOKED_BY"])
def test_relation_claim_requires_its_fact(kind):
    temporal = grounding([chunk()], [relation(kind, None, None)])
    span = facts(temporal)["fato:1"]
    verb = "alterou o dispositivo da" if kind == "AMENDED_BY" else "revogou a"
    item = claim(
        text=f"A Resolução 902/2033 {verb} Resolução 901/2031.",
        quote=span.text,
        span_id=span.span_id,
    )
    assert verify_claim(item, facts(temporal)).status == "supported"
    text_spans = {s.span_id: s for s in segment_chunk(chunk(), BASE)}
    assert "locator_mismatch" in verify_claim(claim(text=item.text), text_spans).codes


@pytest.mark.parametrize("kind", ["AMENDED_BY", "REVOKED_BY"])
def test_relation_without_target_device_preserves_exact_rendered_text(kind):
    temporal = grounding([chunk()], [relation(kind, None, None)])
    expected = AllowedTemporalFacts(
        items=[TemporalFact(kind=kind, norm_id=BASE, target_norm=LATER)]
    )
    assert facts(temporal)["fato:1"].text == render_temporal_statements(expected)


def test_status_fact_is_citable_once_per_norm_without_registry_relations():
    temporal = grounding([chunk(), chunk(article="15", rank=2)])
    spans = facts(temporal)
    assert list(spans) == ["fato:1"]
    item = claim(
        text="Para a Resolução 901/2031, não se pode certificar a vigência atual.",
        quote=spans["fato:1"].text,
        span_id="fato:1",
    )
    assert verify_claim(item, spans).status == "supported"


def test_fact_locators_bind_the_affected_article_to_the_source_norm():
    spans = facts(grounding([chunk()], [relation()]))
    item = claim(
        text="O § 3 do art. 7 da Resolução 901/2031 foi alterado pela Resolução 902/2033.",
        quote="possui alteração parcial registrada por Resolução 902/2033",
        span_id="fato:1",
    )
    assert verify_claim(item, spans).status == "supported"
    wrong = item.model_copy(update={"text": "O § 3 do art. 7 da Resolução 902/2033 foi alterado."})
    assert "locator_mismatch" in verify_claim(wrong, spans).codes
    wrong = item.model_copy(update={"text": "O § 4 do art. 7 da Resolução 901/2031 foi alterado."})
    assert "locator_mismatch" in verify_claim(wrong, spans).codes
    answer = CitedAnswer(claims=[item], answer_type="answer", missing_user_fact=None)
    assert _permissions([], answer, [verify_claim(item, spans)], spans) == []


def test_facts_still_require_literal_quotes_and_quoted_numbers():
    spans = facts(grounding([chunk()], [relation()]))
    bad_quote = claim(quote="A relação foi totalmente inventada aqui.", span_id="fato:1")
    assert "quote_not_found" in verify_claim(bad_quote, spans).codes
    item = claim(text="Há 84 pedidos.", quote=spans["fato:1"].text, span_id="fato:1")
    assert "number_not_in_quotes" in verify_claim(item, spans).codes
    item = item.model_copy(update={"text": "O registro foi atualizado em 2033."})
    assert verify_claim(item, spans).status == "supported"
    item.support[0] = Support(
        span_id="fato:1", quote="isso não representa revogação total da norma-base."
    )
    assert "number_not_in_quotes" in verify_claim(item, spans).codes


@pytest.mark.asyncio
async def test_fact_does_not_authorize_current_validity_and_calls_stay_bounded():
    c = chunk()
    temporal = grounding([c], [relation()])
    item = claim(
        text="A norma está em vigor.", quote=facts(temporal)["fato:1"].text, span_id="fato:1"
    )
    client = Client(payload(item), payload(item))
    result = await generate(client, [c], temporal)
    assert result.citation_audit["action"] == "fallback"
    assert (
        "guard:unsupported_current_validity" in result.citation_audit["first_verdicts"][0]["codes"]
    )
    assert result.generation_attempts == len(client.calls) == 2
    assert result.output_audit.guard_version == "5"
    assert not any(
        p.subdivision_type == "fact" for p in result.output_audit.allowed_content_locators
    )


@pytest.mark.asyncio
async def test_prompt_exposes_fact_schema_and_each_evidence_role():
    chunks = [chunk(), chunk(LATER, "15", rank=2), chunk(OTHER, "19", rank=3)]
    temporal = grounding(chunks, [relation()], ["historical", "posterior", "eligible"])
    client = Client(payload(claim()))
    await generate(client, chunks, temporal)
    prompt = client.calls[0]["user_prompt"]
    assert "FATOS DO REGISTRO NORMATIVO" in prompt
    assert "Ao citar fatos do registro" in client.calls[0]["system_prompt"]
    for span in facts(temporal).values():
        assert f"[{span.span_id}]\n{span.text}" in prompt
        assert (
            span.span_id
            in client.calls[0]["schema"]["$defs"]["Support"]["properties"]["span_id"]["enum"]
        )
    for c, role in zip(
        chunks, ["redação histórica", "redação posterior ou ato alterador", "elegível"], strict=True
    ):
        header = prompt.split(f"[{c.norm_id}:art{c.article_number}]", 1)[0].split("\n")[-2]
        assert role in header and "historical_preserved" in header


@pytest.mark.asyncio
async def test_quote_only_rejection_does_not_repair_or_reassign_address():
    chunks = [
        chunk(),
        chunk(LATER, "15", "A secretaria recebe outro documento por escrito.", 2),
        chunk(OTHER, "19", "A comissão recebe o formulário eletrônico assinado.", 3),
    ]
    temporal = grounding(chunks, [relation()])
    quote = "A COMISSAO recebe o formulario\n eletrônico assinado."
    bad = claim(text="A comissão recebe o formulário.", quote=quote)
    client = Client(payload(bad))
    result = await generate(client, chunks, temporal)
    assert result.citation_audit["first_verdicts"][0]["status"] == "rejected"
    assert "quote_not_found" in result.citation_audit["first_verdicts"][0]["codes"]
    assert result.citation_audit["repair"] is None
    assert result.generation_attempts == len(client.calls) == 1
    assert result.citation_audit["action"] == "fallback"
    assert result.citation_audit["approved_claims"] == []


@pytest.mark.parametrize(
    "text,question,expected",
    [
        (
            "O pedido menciona 84 documentos.",
            "Apresentei oitenta e quatro documentos.",
            "supported",
        ),
        ("O pedido menciona 85 documentos.", "Apresentei 84 documentos.", "number_not_in_quotes"),
        (
            "O pedido menciona 80 documentos.",
            "Apresentei oitenta e quatro documentos.",
            "number_not_in_quotes",
        ),
        (
            "Se transcorreram 84 dias, apresente o pedido.",
            "Já passaram 84 dias úteis?",
            "supported",
        ),
        (
            "Se transcorreram 84 dias corridos, apresente o pedido.",
            "Já passaram 84 dias úteis?",
            "supported",
        ),
        (
            "Se transcorreram 85 dias, apresente o pedido.",
            "Já passaram 84 dias?",
            "number_not_in_quotes",
        ),
        (
            "O prazo é contado em dias corridos.",
            "Já passaram 84 dias corridos?",
            "deadline_qualifier_mismatch",
        ),
    ],
)
def test_user_values_are_premises_but_other_values_need_quotes(text, question, expected):
    spans = {s.span_id: s for s in segment_chunk(chunk(), BASE)}
    verdict = verify_claim(claim(text=text), spans, question=question)
    if expected == "supported":
        assert verdict.status == "supported"
    else:
        assert expected in verdict.codes


def test_question_deadline_exemption_does_not_cover_other_deadlines_or_invalid_quotes():
    c = chunk(text="O recurso tem prazo de 12 dias úteis.")
    spans = {s.span_id: s for s in segment_chunk(c, BASE)}
    item = claim(
        text="Há 84 dias corridos de espera e prazo de 12 dias corridos.",
        quote="O recurso tem prazo de 12 dias úteis.",
    )
    assert (
        "deadline_qualifier_mismatch"
        in verify_claim(item, spans, question="Esperei 84 dias.").codes
    )
    item = claim(text="Esperei 84 dias.", quote="Uma frase que não existe aqui.")
    assert "quote_not_found" in verify_claim(item, spans, question="Esperei 84 dias.").codes


@pytest.mark.asyncio
@pytest.mark.parametrize("repair", [False, True])
async def test_generation_passes_question_to_initial_and_repair_verification(repair):
    c = chunk()
    good = claim(text="Se foram apresentados 84 documentos, a coordenação recebe o pedido.")
    responses = (
        [payload(claim(text="Há 85 documentos.")), payload(good)] if repair else [payload(good)]
    )
    client = Client(*responses)
    result = await generate(
        client, [c], grounding([c]), "Apresentei 84 documentos; como apresentar o pedido?"
    )
    assert result.citation_audit["action"] == ("repaired" if repair else "accepted")
    assert result.generation_attempts == len(client.calls) == len(responses)


@pytest.mark.asyncio
async def test_no_temporal_facts_preserves_previous_prompt_and_behavior():
    from rag_baseline.cited_generation import CITED_INSTRUCTION

    c = chunk()
    temporal = grounding([c], unknown=False)
    assert allowed_temporal_facts(temporal).items == []
    assert facts(temporal) == {}
    client = Client(payload(claim()))
    result = await generate(client, [c], temporal)
    expected = (
        "CONTEXTO NORMATIVO (use somente como evidência):\n"
        + temporal.prompt_section()
        + "Resolução 901/2031, artigo 7\n[ufpi-901-2031:art7]\nArt. 7. "
        + QUOTE
        + "\n\nResolução 901/2031, artigo 7\n[ufpi-901-2031:art7:caput]\nArt. 7. "
        + QUOTE
        + "\n\nPERGUNTA:\nComo apresentar o pedido?"
    )
    assert client.calls[0]["user_prompt"] == expected
    assert client.calls[0]["system_prompt"] == service(client).system_prompt + CITED_INSTRUCTION
    assert result.citation_audit["action"] == "accepted"
    assert result.generation_attempts == 1
    assert FALLBACK_BODY not in result.answer


@pytest.mark.asyncio
async def test_repair_offers_registry_facts_when_a_relation_claim_lacks_its_source():
    # A relation stated against article text is rejected for numbers/locators; the
    # repair must be able to reach the registry fact that supports it.
    chunks = [chunk(), chunk(LATER, "15", "Nova redação do pedido por escrito.", rank=2)]
    temporal = grounding(chunks, [relation()])
    stated = claim(text=f"A {norm_name(LATER)} alterou o art. 7 da {norm_name(BASE)}.")
    client = Client(payload(stated), payload(stated))
    await generate(client, chunks, temporal)
    repair_prompt = client.calls[1]["user_prompt"]
    assert "fato:1" in repair_prompt
    assert "cite o fato do registro" in repair_prompt
