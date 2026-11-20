"""Synthetic regressions for deterministic citation delivery and bounded repair."""

import json

import pytest
from pydantic import ValidationError

from rag_baseline.citation_contracts import CitedAnswer, Claim, Support, cited_answer_schema
from rag_baseline.citation_verifier import disposition, snap_quote, verify_claim
from rag_baseline.cited_generation import CITED_INSTRUCTION, _compose
from rag_baseline.evidence_spans import segment_chunk
from rag_baseline.normative_output import FALLBACK_BODY, NormativeOutputGuard, norm_name
from tests.rag_baseline.test_citation_temporal import BASE, chunk, generate, grounding
from tests.rag_baseline.test_cited_generation import Client

QUOTE = "A coordenação recebe o pedido por escrito."
ROOT = f"{BASE}:art7"


def claim(
    text="A coordenação recebe o pedido.",
    *,
    role="conclusion",
    group=0,
    side=None,
    quote=QUOTE,
    span_id=ROOT,
):
    return Claim(
        text=text,
        role=role,
        group=group,
        side=side,
        support=[Support(span_id=span_id, quote=quote)],
    )


def answer(*claims, **kwargs):
    return CitedAnswer(
        claims=list(claims),
        answer_type=kwargs.get("answer_type", "answer"),
        missing_user_fact=kwargs.get("missing_user_fact"),
    )


def decide(*claims):
    spans = {s.span_id: s for s in segment_chunk(chunk(), BASE)}
    verdicts = [verify_claim(c, spans, i) for i, c in enumerate(claims)]
    return disposition(answer(*claims), verdicts, spans=spans)


async def run(client, c=None):
    c = c or chunk()
    return await generate(client, [c], grounding([c]))


def test_schema_requires_group_and_nullable_side():
    schema = cited_answer_schema()["$defs"]["Claim"]
    assert set(schema["required"]) == set(schema["properties"])
    assert {"type": "null"} in schema["properties"]["side"]["anyOf"]
    data = claim().model_dump()
    for key in ("group", "side"):
        with pytest.raises(ValidationError):
            Claim.model_validate({k: v for k, v in data.items() if k != key})
    assert "group" in CITED_INSTRUCTION and "side" in CITED_INSTRUCTION


def test_snap_preserves_already_normalized_literal_and_is_pure():
    quote = "A COORDENACAO recebe o pedido por escrito."
    assert snap_quote(quote, QUOTE) == (quote, 1.0)
    assert snap_quote("", QUOTE) == ("", 1.0)
    assert snap_quote(QUOTE, "") == (None, 0.0)


@pytest.mark.parametrize(
    "quote",
    [
        "I. A coordenação recebe o pedido por escrito.",
        "I - A coordenação recebe, o pedido por escrito.",
        "I - A coordenação recebe o pedido por  escrito!",
    ],
)
@pytest.mark.asyncio
async def test_snap_is_audited_and_keeps_claim_text(quote):
    original = "I - A coordenação recebe o pedido por escrito."
    c = chunk(text=original)
    item = claim(quote=quote)
    client = Client(answer(item).model_dump_json())
    result = await run(client, c)
    assert result.citation_audit["action"] == "accepted"
    assert len(client.calls) == 1
    (record,) = result.citation_audit["snapped_quotes"]
    assert record["claim_index"] == 0 and record["span_id"] == ROOT
    assert record["original"] == quote
    assert record["snapped"] in c.content
    assert record["similarity"] >= 0.90
    (approved,) = result.citation_audit["approved_claims"]
    assert approved["text"] == item.text
    assert approved["quotes"] == [record["snapped"]]


@pytest.mark.asyncio
async def test_below_threshold_stays_rejected_without_repair():
    quote = "O candidato entrega formulário eletrônico assinado."
    snapped, similarity = snap_quote(quote, QUOTE)
    assert snapped is None and similarity < 0.90
    result = await run(Client(answer(claim(quote=quote)).model_dump_json()))
    assert "quote_not_found" in result.citation_audit["first_verdicts"][0]["codes"]
    assert result.citation_audit["snapped_quotes"] == []
    assert result.citation_audit["repair"] is None
    assert result.generation_attempts == 1
    assert FALLBACK_BODY in result.answer


@pytest.mark.asyncio
async def test_snapped_quote_cannot_authorize_a_changed_number():
    item = claim(
        text="São recebidos 99 pedidos por escrito.",
        quote="A coordenação recebe 99 pedidos por escrito.",
    )
    c = chunk(text="A coordenação recebe 10 pedidos por escrito.")
    client = Client(answer(item).model_dump_json(), answer(item).model_dump_json())
    result = await run(client, c)
    assert result.citation_audit["snapped_quotes"]
    codes = result.citation_audit["first_verdicts"][0]["codes"]
    assert "number_not_in_quotes" in codes and "quote_not_found" not in codes
    assert item.text not in result.answer
    assert result.generation_attempts == 2


@pytest.mark.asyncio
async def test_short_quote_still_rejected_and_never_repaired():
    item = claim(quote="recebe o pedido")
    result = await run(Client(answer(item).model_dump_json()))
    assert result.citation_audit["first_verdicts"][0]["codes"] == ["quote_too_short"]
    assert result.generation_attempts == 1


def test_threshold_is_inclusive_and_counts_all_essential_claims():
    bad = claim("Uma condição não verificada.", role="condition", quote="Texto ausente.")
    half = decide(claim(), bad)
    below = decide(claim(), bad, bad.model_copy(update={"role": "exception"}))
    assert half.action == "partial"
    assert half.approved_indices == [0]
    assert bad.text not in half.body
    assert below.action == "fallback" and below.body == FALLBACK_BODY


def test_group_without_verified_conclusion_is_discarded_even_with_verified_qualifier():
    good = claim()
    rejected = claim("Regra não comprovada.", group=1, quote="Texto completamente ausente.")
    qualifier = claim("Qualificador do grupo descartado.", group=1, role="condition")
    final = decide(good, rejected, qualifier)
    assert final.action == "partial"
    assert final.approved_indices == [0] and final.omitted_indices == [1, 2]
    assert rejected.text not in final.body and qualifier.text not in final.body
    assert any("há regra em Resolução 901/2031, art. 7" in c for c in final.caveats)
    assert decide(rejected, qualifier).action == "fallback"


@pytest.mark.parametrize(
    "role,label", [("condition", "condição"), ("exception", "exceção"), ("deadline", "prazo")]
)
@pytest.mark.asyncio
async def test_caveats_name_address_deduplicate_and_bypass_guard(monkeypatch, role, label):
    c = chunk(
        text=QUOTE + "\n§ 2º Uma condição documental deve ser observada.\n"
        "II - O documento deve ser assinado pelo requerente."
    )
    bad = claim(
        "TEXTO REJEITADO QUE NUNCA PODE APARECER.",
        role=role,
        span_id=ROOT + ":p2:incII",
        quote="Esta citação foi totalmente inventada.",
    )
    seen = []
    original = NormativeOutputGuard.check

    def check(self, text, *args, **kwargs):
        seen.append(text)
        return original(self, text, *args, **kwargs)

    monkeypatch.setattr(NormativeOutputGuard, "check", check)
    # Two verified conclusions keep the essential fraction exactly at the threshold.
    client = Client(answer(claim(), claim(), bad, bad).model_dump_json())
    result = await run(client, c)
    (caveat,) = result.citation_audit["caveats"]
    assert caveat == (
        f"Ressalva: há {label} em Resolução 901/2031, art. 7, § 2, inciso II "
        "que não pôde ser verificada literalmente nos trechos recuperados; "
        "consulte o dispositivo."
    )
    assert caveat in result.answer and result.answer.count(caveat) == 1
    assert bad.text not in result.answer
    assert all("Ressalva:" not in text for text in seen)
    assert result.citation_audit["action"] == "partial"
    assert len(client.calls) == 1


def test_unknown_span_caveat_does_not_invent_a_device():
    bad = claim(role="condition", span_id="unknown")
    final = decide(claim(), bad)
    assert final.caveats == [
        "Ressalva: há condição nos trechos recuperados que não pôde ser verificada "
        "literalmente nos trechos recuperados; consulte o dispositivo."
    ]


@pytest.mark.parametrize(
    "sides,headers",
    [
        (("graduacao", "pos_graduacao"), ("Graduação:", "Pós-graduação:")),
        ((BASE, "pos_graduacao"), (norm_name(BASE) + ":", "Pós-graduação:")),
    ],
)
@pytest.mark.asyncio
async def test_comparisons_have_sections_and_correct_audit_offsets(sides, headers):
    first = claim("Regra do primeiro lado.", side=sides[0])
    second = claim("Regra do segundo lado.", side=sides[1])
    last = claim("Outra unidade do primeiro lado.", side=sides[0], group=1)
    result = await run(Client(answer(first, second, last).model_dump_json()))
    assert result.citation_audit["action"] == "accepted"
    assert result.answer.index(headers[0]) < result.answer.index(headers[1])
    assert result.answer.index(last.text) < result.answer.index(headers[1])
    body, _ = _compose([first, second, last], [0, 1, 2])
    for item in result.citation_audit["approved_claims"]:
        assert body[item["start"] : item["end"]] == item["text"]


@pytest.mark.parametrize("reject_both", [False, True])
@pytest.mark.asyncio
async def test_comparison_threshold_is_per_side(reject_both):
    first = claim(side="graduacao", quote="Ausência literal completa." if reject_both else QUOTE)
    second = claim("Regra ausente do outro lado.", side="pos_graduacao", quote="Frase ausente.")
    result = await run(Client(answer(first, second).model_dump_json()))
    if reject_both:
        assert result.citation_audit["action"] == "fallback"
        assert FALLBACK_BODY in result.answer
    else:
        assert result.citation_audit["action"] == "partial"
        assert "Graduação:" in result.answer and "Pós-graduação:" not in result.answer
        assert second.text not in result.answer
        assert (
            "Não foi possível verificar a regra para Pós-graduação nos trechos recuperados."
            in result.answer
        )


def test_comparison_low_fraction_is_omitted_despite_verified_conclusion():
    first = claim(side="graduacao")
    second = claim(side="pos_graduacao")
    bad = claim(role="condition", side="pos_graduacao", quote="Texto inexistente.")
    final = decide(first, second, bad, bad.model_copy(update={"role": "exception"}))
    assert final.action == "partial" and final.approved_indices == [0]
    assert any("Pós-graduação" in c for c in final.caveats)


@pytest.mark.parametrize(
    "bad_text,code",
    [
        ("Há 99 documentos.", "number_not_in_quotes"),
        ("O art. 99 prevê o pedido.", "locator_mismatch"),
        ("A norma está em vigor.", "guard:unsupported_current_validity"),
    ],
)
@pytest.mark.asyncio
async def test_repair_includes_only_eligible_essential_claims(bad_text, code):
    quote_only = claim("Qualificação não verificada.", role="condition", quote="Texto ausente.")
    peripheral = claim("Há 98 documentos.", role="context")
    bad = claim(bad_text, group=1)
    replacement = claim("A coordenação recebe o pedido corrigido.", group=1)
    client = Client(
        answer(claim(), quote_only, peripheral, bad).model_dump_json(),
        answer(replacement).model_dump_json(),
    )
    result = await run(client)
    request = result.citation_audit["repair"]["request"]
    assert [entry["index"] for entry in request["rejected_claims"]] == [3]
    assert code in request["rejected_claims"][0]["codes"]
    assert quote_only.text not in client.calls[1]["user_prompt"]
    assert peripheral.text not in client.calls[1]["user_prompt"]
    assert result.generation_attempts == len(client.calls) == 2
    assert result.citation_audit["action"] == "partial"
    assert bad_text not in result.answer


@pytest.mark.asyncio
async def test_snap_runs_on_repair_and_cannot_change_rule_membership():
    bad = claim("Há 99 documentos.", side="graduacao", group=8)
    replacement = claim(quote=QUOTE.replace("recebe", "recebe,"), side="graduacao", group=8)
    client = Client(answer(bad).model_dump_json(), answer(replacement).model_dump_json())
    result = await run(client)
    assert result.citation_audit["action"] == "repaired"
    assert result.citation_audit["snapped_quotes"][0]["claim_index"] == 0
    changed = replacement.model_copy(update={"side": "pos_graduacao"})
    result = await run(Client(answer(bad).model_dump_json(), answer(changed).model_dump_json()))
    assert result.citation_audit["action"] == "fallback"


@pytest.mark.asyncio
async def test_guard_still_blocks_unsupported_current_validity():
    item = claim("A norma está em vigor.")
    client = Client(answer(item).model_dump_json(), answer(item).model_dump_json())
    result = await run(client)
    assert result.citation_audit["action"] == "fallback"
    assert result.output_audit.guard_version == "5"
    assert result.generation_attempts == len(client.calls) == 2
    assert item.text not in result.answer


@pytest.mark.asyncio
async def test_invalid_structure_gets_one_full_retry_then_falls_back():
    # Truncated or malformed output is retried once; a second invalid output falls back.
    invalid = json.dumps({"claims": "invalid"})
    result = await run(Client(invalid, invalid))
    assert result.citation_audit["action"] == "fallback"
    assert result.citation_audit["structured_output_error"]
    assert result.generation_attempts == 2


@pytest.mark.parametrize("items", [[], [claim(role="context")], [claim(role="condition")]])
@pytest.mark.asyncio
async def test_needs_user_fact_preserves_verified_guidance_without_conclusion(items):
    client = Client(
        answer(
            *items, answer_type="needs_user_fact", missing_user_fact="Informe o curso."
        ).model_dump_json()
    )
    result = await run(client)
    assert result.citation_audit["action"] == "needs_user_fact"
    assert "Dado necessário: Informe o curso." in result.answer
    assert result.generation_attempts == 1


def test_discarded_comparison_group_also_marks_the_side_as_omitted():
    good_side = claim(side="graduacao")
    other_side = claim(side="pos_graduacao")
    rejected = claim(side="pos_graduacao", quote="Uma frase totalmente ausente.")
    result = decide(good_side, other_side, rejected)
    assert result.action == "partial" and result.approved_indices == [0]
    assert (
        "Não foi possível verificar a regra para Pós-graduação nos trechos recuperados."
        in result.caveats
    )
