"""Generation mode and requested comparison coverage remain explicit at runtime."""

import logging
from types import SimpleNamespace

import pytest

from rag_baseline import api
from rag_baseline.agentic import AgenticRagService, build_graph
from rag_baseline.config import BaselineSettings
from rag_baseline.models import QueryResult
from rag_baseline.versioning import NormativeRegistry, VersionFilter
from tests.rag_baseline.test_citation_side_coverage import GRAD_CLAIM, graduation
from tests.rag_baseline.test_citation_temporal import grounding
from tests.rag_baseline.test_citation_v3_3 import answer
from tests.rag_baseline.test_cited_generation import Client, service


@pytest.mark.asyncio
async def test_cited_fallback_records_effective_mode_and_reason():
    result = await service(Client(), generation_mode="cited_v3").generate(
        "Pergunta", [graduation()]
    )
    serialized = result.model_dump()
    assert serialized.get("effective_generation_mode") == "free_text_v2"
    assert serialized.get("generation_fallback_reason") == "missing_temporal_grounding"
    assert result.citation_audit is None
    assert result.answer == "Texto livre antigo."


@pytest.mark.asyncio
async def test_cited_fallback_warns_once_per_service(caplog):
    svc = service(Client(), generation_mode="cited_v3")
    with caplog.at_level(logging.WARNING, logger="rag_baseline.service"):
        await svc.generate("Pergunta", [graduation()])
        await svc.generate("Outra pergunta", [graduation()])
    warnings = [record for record in caplog.records if record.name == "rag_baseline.service"]
    assert len(warnings) == 1
    assert "cited_v3" in warnings[0].message
    assert "free_text_v2" in warnings[0].message
    assert "temporal" in warnings[0].message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,grounded", [("free_text_v2", False), ("free_text_v2", True), ("cited_v3", True)]
)
async def test_normal_generation_has_no_mode_fallback(mode, grounded, caplog):
    c = graduation()
    client = Client(answer(GRAD_CLAIM).model_dump_json())
    with caplog.at_level(logging.WARNING, logger="rag_baseline.service"):
        result = await service(client, generation_mode=mode).generate(
            "Como apresentar o pedido?",
            [c],
            temporal_grounding=grounding([c]) if grounded else None,
        )
    serialized = result.model_dump()
    assert "effective_generation_mode" not in serialized
    assert "generation_fallback_reason" not in serialized
    assert not [record for record in caplog.records if record.name == "rag_baseline.service"]
    if mode == "cited_v3":
        assert result.citation_audit["action"] == "accepted"
    else:
        assert result.citation_audit is None


class LegacyService:
    top_k = 3
    llm_model = "llm"
    embedding_model = "embed"

    async def retrieve(self, question, *, sector=None, excluded_sources=None):
        return [graduation()]

    async def generate(self, question, chunks, *, context_notice=None, temporal_grounding=None):
        return QueryResult(
            answer="Resposta.", references=[], llm_model="llm", embedding_model="embed"
        )


class CitedService(LegacyService):
    generation_mode = "cited_v3"

    def __init__(self):
        self.calls = []

    async def generate(self, question, chunks, **kwargs):
        self.calls.append(kwargs)
        return await super().generate(
            question,
            chunks,
            context_notice=kwargs.get("context_notice"),
            temporal_grounding=kwargs.get("temporal_grounding"),
        )


def pipeline(svc):
    return AgenticRagService(svc, object(), VersionFilter(NormativeRegistry(norms=[])))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question", ["Qual é a regra na graduação?", "Qual é o prazo para recurso?"]
)
async def test_default_both_scope_does_not_request_comparison_coverage(question):
    svc = CitedService()
    await pipeline(svc).query(question, scope="ambas")
    assert "expected_sides" not in svc.calls[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        "Compare graduação e pós-graduação.",
        "Compare graduação e mestrado.",
        "Quais são as regras na graduação e no stricto sensu?",
    ],
)
async def test_explicit_comparison_requests_both_sides(question):
    svc = CitedService()
    await pipeline(svc).query(question, scope="ambas")
    assert svc.calls[0]["expected_sides"] == ["graduacao", "pos_graduacao"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [None, "free_text_v2"])
async def test_free_generation_preserves_legacy_injected_signature(mode):
    svc = LegacyService()
    if mode is not None:
        svc.generation_mode = mode
    result = await pipeline(svc).query("Compare graduação e pós-graduação.", scope="ambas")
    assert result.answer == "Resposta."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "profile,collection",
    [
        (None, "ufpi_duas_regulacoes_setor_v4"),
        ("duas-regulacoes", "ufpi_duas_regulacoes_setor"),
        ("duas-regulacoes-v4", "ufpi_duas_regulacoes_setor_v4"),
    ],
)
async def test_legacy_graph_applies_configured_corpus_profile(profile, collection, monkeypatch):
    if profile is None:
        monkeypatch.delenv("CORPUS_PROFILE", raising=False)
    else:
        monkeypatch.setenv("CORPUS_PROFILE", profile)
    monkeypatch.setattr(
        "rag_baseline.config.BaselineSettings", lambda: BaselineSettings(_env_file=None)
    )
    settings_seen = []
    configured = SimpleNamespace(
        service=LegacyService(),
        router=object(),
        version_filter=VersionFilter(NormativeRegistry(norms=[])),
    )

    class Runtime:
        def __init__(self, settings):
            settings_seen.append(settings)

        def agentic(self):
            return configured

    monkeypatch.setattr(api, "_Runtime", Runtime)
    completed = await build_graph().ainvoke(
        {"question": "Regra na graduação?", "manual_scope": "graduacao"}
    )
    assert completed["result"].answer == "Resposta."
    assert settings_seen[0].CHROMA_COLLECTION == collection
