"""A comparison answer that covers only one requested level says so explicitly."""

import pytest

from rag_baseline.cited_generation import generate_cited
from tests.rag_baseline.test_citation_temporal import chunk, grounding
from tests.rag_baseline.test_citation_v3_3 import answer, claim
from tests.rag_baseline.test_cited_generation import Client, service

LATER = "ufpi-902-2033"
POS_QUOTE = "O discente apresenta o pedido ao colegiado do programa."


def graduation():
    return chunk().model_copy(update={"sector": "graduacao"})


def postgraduate():
    return chunk(LATER, "15", POS_QUOTE).model_copy(update={"sector": "pos_graduacao"})


async def run(items, chunks, expected_sides):
    client = Client(answer(*items).model_dump_json())
    result = await generate_cited(
        service(client, generation_mode="cited_v3"),
        "Compare as regras nos dois níveis.",
        chunks,
        context_notice="",
        grounding=grounding(chunks),
        expected_sides=expected_sides,
    )
    return result, client


GRAD_CLAIM = claim(side="graduacao", group=1)
POS_CLAIM = claim(
    "O discente apresenta o pedido.",
    side="pos_graduacao",
    group=2,
    quote=POS_QUOTE,
    span_id=f"{LATER}:art15",
)


@pytest.mark.asyncio
async def test_missing_requested_level_becomes_a_caveat():
    result, _ = await run(
        [GRAD_CLAIM], [graduation(), postgraduate()], ["graduacao", "pos_graduacao"]
    )
    audit = result.citation_audit
    assert audit["action"] == "partial"
    assert any("pós-graduação" in c for c in audit["caveats"])
    assert "side_not_covered:pos_graduacao" in audit["disposition_codes"]
    assert "pós-graduação" in result.answer


@pytest.mark.asyncio
async def test_missing_level_is_flagged_even_without_its_evidence():
    # Retrieval may bring only one level; the answer must not look complete.
    result, _ = await run([GRAD_CLAIM], [graduation()], ["graduacao", "pos_graduacao"])
    assert "side_not_covered:pos_graduacao" in result.citation_audit["disposition_codes"]


@pytest.mark.asyncio
async def test_both_levels_covered_need_no_caveat():
    result, _ = await run(
        [GRAD_CLAIM, POS_CLAIM], [graduation(), postgraduate()], ["graduacao", "pos_graduacao"]
    )
    assert result.citation_audit["action"] == "accepted"
    assert not any(
        code.startswith("side_not_covered") for code in result.citation_audit["disposition_codes"]
    )


@pytest.mark.asyncio
async def test_without_expected_sides_nothing_changes():
    result, _ = await run([GRAD_CLAIM], [graduation(), postgraduate()], None)
    assert result.citation_audit["action"] == "accepted"
    assert result.citation_audit["caveats"] == []


@pytest.mark.asyncio
async def test_service_forwards_expected_sides(monkeypatch):
    seen = {}

    async def fake(service_, question, chunks, **kwargs):
        seen.update(kwargs)
        return "ok"

    monkeypatch.setattr("rag_baseline.cited_generation.generate_cited", fake)
    svc = service(Client(), generation_mode="cited_v3")
    c = graduation()
    await svc.generate("q", [c], temporal_grounding=grounding([c]), expected_sides=["graduacao"])
    assert seen["expected_sides"] == ["graduacao"]
    # The free-text path accepts and ignores it.
    seen.clear()
    client = Client()
    free = service(client, generation_mode="free_text_v2")
    result = await free.generate(
        "q", [c], temporal_grounding=grounding([c]), expected_sides=["graduacao"]
    )
    assert result.answer
    assert client.calls
    assert seen == {}
    assert all("expected_sides" not in call for call in client.calls)


@pytest.mark.asyncio
async def test_side_caveat_is_not_duplicated_when_the_side_was_already_omitted():
    rejected_pos = claim(
        "O discente apresenta o pedido.",
        side="pos_graduacao",
        group=2,
        quote="Texto que não existe no artigo citado de forma alguma.",
        span_id=f"{LATER}:art15",
    )
    result, _ = await run(
        [GRAD_CLAIM, rejected_pos], [graduation(), postgraduate()], ["graduacao", "pos_graduacao"]
    )
    caveats = [c.casefold() for c in result.citation_audit["caveats"]]
    assert sum("regra para pós-graduação" in c for c in caveats) == 1
