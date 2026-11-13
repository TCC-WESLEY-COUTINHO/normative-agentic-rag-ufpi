"""Generation contract from real frequency trace; keep locator guard fail-closed."""

import pytest
from test_normative_output import SequenceClient

from rag_baseline.content_locators import ContentLocatorPolicy
from rag_baseline.corpus import load_corpus
from rag_baseline.grounding import build_temporal_grounding
from rag_baseline.models import RetrievedChunk
from rag_baseline.normative_output import (
    NormativeOutputGuard,
    allowed_temporal_facts,
    normative_references,
)
from rag_baseline.service import RagService
from rag_baseline.versioning import REGISTRY_PATH, NormativeRegistry, TemporalIntent, VersionFilter

QUESTION = (
    "Qual é a frequência mínima que eu preciso ter nas aulas para não ser reprovado por falta?"
)


def context(articles=("112", "115")):
    corpus = REGISTRY_PATH.parent.parent / "evaluation/corpora/graduacao_setor_v2.json"
    chunks = [
        c for c in load_corpus(corpus, id_prefix="ufpi-177-2012") if c.article_number in articles
    ]
    chunks = [
        RetrievedChunk(**c.model_dump(), rank=i + 1, distance=None) for i, c in enumerate(chunks)
    ]
    registry = NormativeRegistry.load()
    chunks, audit = VersionFilter(registry).apply(
        chunks, temporal_intent=TemporalIntent(mode="current"), top_k=5
    )
    return chunks, build_temporal_grounding(chunks, audit, registry)


async def generate(outputs, question=QUESTION, articles=("112", "115")):
    chunks, grounding = context(articles)
    remote = SequenceClient(outputs)
    result = await RagService(
        openrouter=remote,
        vector_store=None,
        top_k=5,
        embedding_model="controlled",
        llm_model="controlled",
    ).generate(question, chunks, temporal_grounding=grounding)
    return result, remote


@pytest.mark.asyncio
async def test_frequency_generation_explicitly_uses_authorized_citation_forms():
    result, remote = await generate(
        [
            "A frequência mínima é de 75% da carga horária, conforme o art. 112 da Resolução 177/2012."
        ]
    )
    prompt = remote.calls[0]["user_prompt"]
    assert "FORMAS DE CITAÇÃO AUTORIZADAS" in prompt
    assert "Resolução 177/2012, art. 112" in prompt
    assert "Não copie subdivisões do texto da evidência" in prompt
    assert result.normative_output.status == "accepted"


@pytest.mark.asyncio
async def test_regeneration_explains_how_to_keep_supported_content_without_unauthorized_locator():
    raw = (
        "É necessário ter 75% de frequência, conforme o Art. 112, inciso IX, da Resolução 177/2012."
    )
    result, remote = await generate(
        [raw, "É necessário ter 75% de frequência, conforme o art. 112 da Resolução 177/2012."]
    )
    prompt = remote.calls[1]["user_prompt"]
    assert "unvalidated_subdivision" in prompt
    assert "omita a subdivisão não autorizada" in prompt
    assert result.normative_output.status == "regenerated"
    assert result.generation_attempts == 2
    assert result.output_audit.guard_violations[0].code == "unvalidated_subdivision"


@pytest.mark.asyncio
async def test_invented_subdivision_remains_blocked_when_provider_ignores_permissions():
    raw = "A frequência mínima é de 75%, conforme o Art. 112, inciso IX, da Resolução 177/2012."
    result, remote = await generate([raw, raw])
    assert result.normative_output.status == "fallback"
    assert len(remote.calls) == 2
    assert {v.code for v in result.output_audit.second_guard_violations} == {
        "unvalidated_subdivision"
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question,articles,body",
    [
        (
            QUESTION,
            ("112", "115"),
            "É necessária frequência de pelo menos 75% da carga horária, conforme o art. 112 da Resolução 177/2012.",
        ),
        (
            "Como se registra a presença do aluno na graduação?",
            ("114",),
            "A presença é registrada por frequência em cada 60 minutos de aula, conforme o art. 114.",
        ),
        (
            "Posso ser reprovado por faltas independentemente das notas?",
            ("115",),
            "A reprovação por falta independe dos resultados das avaliações, conforme o art. 115.",
        ),
    ],
)
async def test_direct_article_evidence_can_produce_substantive_accepted_body(
    question, articles, body
):
    result, _ = await generate([body], question, articles)
    assert result.normative_output.status == "accepted"
    assert body in result.answer
    assert all(r.evidence_text for r in result.normative_output.references)


def test_explicit_authorized_subdivision_still_works_and_other_locators_do_not():
    chunks, grounding = context()
    question = "O que diz o art. 112, inciso I, da Resolução 177/2012?"
    refs = normative_references(chunks, grounding)
    locators = ContentLocatorPolicy().build(question, grounding, refs)
    facts = allowed_temporal_facts(grounding)
    guard = NormativeOutputGuard()
    assert not guard.check(
        "Conforme art. 112, inciso I, da Resolução 177/2012, a frequência inferior a 75% reprova.",
        refs,
        facts,
        grounding,
        allowed_content_locators=locators,
    )
    for body in [
        "Conforme art. 999.",
        "Conforme art. 112, inciso II.",
        "A norma entrou em vigor em 2025.",
        "Resolução 999/2025.",
    ]:
        assert guard.check(body, refs, facts, grounding, allowed_content_locators=locators)


@pytest.mark.asyncio
async def test_insufficient_evidence_abstention_is_preserved():
    body = "Os trechos fornecidos não permitem responder ao prazo solicitado."
    result, _ = await generate([body], "Qual o prazo para recurso de uma bolsa externa?")
    assert body in result.answer
    assert "75%" not in result.answer


@pytest.mark.asyncio
async def test_article_only_generation_unambiguously_excludes_subdivision_citations():
    result, remote = await generate(
        ["A presença é registrada a cada 60 minutos de aula, conforme o art. 114."],
        "Explique o registro de frequência na graduação.",
        ("106", "112", "114", "115"),
    )
    # These articles declare subdivisions, so the prompt lists them instead of forbidding them.
    assert "GRANULARIDADE DESTA RESPOSTA: somente artigo" not in remote.calls[0]["user_prompt"]
    assert "Resolução 177/2012, art. 106: " in remote.calls[0]["user_prompt"]
    assert result.normative_output.status == "accepted"
