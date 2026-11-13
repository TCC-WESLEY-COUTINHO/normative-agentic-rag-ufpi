"""Explicit levels cannot be undone by contradictory provider classifications."""

import json

import pytest
from test_temporal_grounding import Store, chunk

from rag_baseline.agentic import AgenticRagService
from rag_baseline.router import NormativeRouter
from rag_baseline.service import RagService
from rag_baseline.versioning import NormativeRegistry, VersionFilter

CASE_A = (
    "A Resolução 658/2024 ainda pode reger hoje a pós-graduação da UFPI ou foi revogada? "
    "Qual ato e dispositivo estabelecem isso?"
)


class Provider:
    llm_model = "controlled"

    def __init__(self):
        self.routes = []

    async def structured_chat(self, **kwargs):
        self.routes.append(json.loads(kwargs["user_prompt"]))
        # Actual contradictory schema returned in the initial Case A trace.
        return json.dumps(
            dict(
                scope="pos_graduacao",
                needs_clarification=False,
                clarification_question="O nível acadêmico é explicitamente pós-graduação.",
                reason_code="explicit_pos",
            )
        )

    async def embed(self, texts):
        return [[0.0]]

    async def chat(self, **kwargs):
        return "Conteúdo sustentado pelas evidências selecionadas."


async def query(question, *, clarification=None):
    provider = Provider()
    service = RagService(
        openrouter=provider,
        vector_store=Store([chunk("956-2025", "62")]),
        top_k=5,
        embedding_model="controlled",
        llm_model="controlled",
    )
    result = await AgenticRagService(
        service, NormativeRouter(provider), VersionFilter(NormativeRegistry.load())
    ).query(question, clarification=clarification)
    return result, provider


@pytest.mark.parametrize(
    "question,sector",
    [
        (CASE_A, "pos_graduacao"),
        ("Quanto tempo tenho para terminar o mestrado?", "pos_graduacao"),
        ("Faço mestrado e estou doente. Posso trancar o curso?", "pos_graduacao"),
        ("Como funciona a pós-graduação da UFPI?", "pos_graduacao"),
        ("como trancar a pós", "pos_graduacao"),
        ("Quais os prazos na graduação?", "graduacao"),
        ("Precisa de IRA na pós-graduação?", "pos_graduacao"),
    ],
)
@pytest.mark.asyncio
async def test_explicit_level_reaches_temporal_pipeline_without_router(question, sector):
    result, provider = await query(question)
    assert result.needs_clarification is False
    assert result.selected_scope == sector
    assert result.normative_output is not None
    assert provider.routes == []
    assert result.routing["explicit_sector_fast_path_used"] is True
    assert result.routing["resolved_sector"] == sector


@pytest.mark.parametrize(
    "question",
    [
        "efeito pós-recurso",
        "período pós-defesa",
        "alteração pós-2025",
        "situação pós-pandemia",
        "Qual a diferença entre as regras da graduação e da pós-graduação?",
        "graduação versus pós-graduação",
        "Qual a diferença entre graduação e pós?",
        "graduação versus pós",
        "Compare as regras da graduação e pós.",
        "Como funciona a pós‑graduação da UFPI?",
        "Como funciona a pós–graduação da UFPI?",
        "Posso cancelar uma disciplina?",
        "Como funciona o Exame Final?",
        "O que é a Láurea Universitária?",
        "Qual é meu IRA?",
    ],
)
@pytest.mark.asyncio
async def test_nonexplicit_or_comparison_queries_keep_real_router(question):
    result, provider = await query(question)
    assert provider.routes == [{"question": question}]
    assert result.needs_clarification
    assert result.route["reason_code"] == "invalid_model_decision"


@pytest.mark.asyncio
async def test_existing_clarification_is_not_silently_overridden_by_fast_path():
    result, provider = await query("Qual a regra da graduação?", clarification="pós-graduação")
    assert provider.routes[0]["clarification"] == "pós-graduação"
    assert result.needs_clarification
