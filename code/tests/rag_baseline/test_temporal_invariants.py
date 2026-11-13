"""Technical regressions over documentary relations; not a legally validated gold."""

import json

import pytest
from fastapi.testclient import TestClient

from rag_baseline.agentic import AgenticRagService, is_historical_question
from rag_baseline.api import create_app
from rag_baseline.config import BaselineSettings
from rag_baseline.corpus import load_corpus
from rag_baseline.models import RetrievedChunk
from rag_baseline.prompts import V2_SYSTEM_PROMPT
from rag_baseline.router import NormativeRouter
from rag_baseline.service import RagService
from rag_baseline.versioning import REGISTRY_PATH, NormativeRegistry, VersionFilter

ROOT = REGISTRY_PATH.parent.parent


def real_chunk(norm, article, rank=1):
    names = {
        "177-2012": "graduacao_setor_v2.json",
        "956-2025": "pos_graduacao_setor_v2.json",
        "658-2024": "658_2024_temporal_v1.json",
        "1056-2026": "1056_2026_temporal_v1.json",
    }
    corpus = load_corpus(ROOT / "evaluation/corpora" / names[norm], id_prefix=f"ufpi-{norm}")
    original = next(c for c in corpus if c.article_number == article)
    return RetrievedChunk(**original.model_dump(), rank=rank, distance=0.1)


class Remote:
    llm_model = "test"

    def __init__(self, scope):
        self.scope = scope
        self.prompts = []
        self.routes = []

    async def structured_chat(self, **payload):
        self.routes.append(payload)
        return json.dumps(
            dict(
                scope=self.scope,
                needs_clarification=self.scope is None,
                clarification_question="Qual nível?" if self.scope is None else None,
                reason_code={
                    None: "ambiguous_academic_level",
                    "graduacao": "explicit_graduacao",
                    "pos_graduacao": "explicit_pos",
                    "ambas": "cross_norm_comparison",
                }[self.scope],
            )
        )

    async def embed(self, texts):
        return [[1.0, 0.0]]

    async def chat(self, **payload):
        self.prompts.append(payload)
        return "Resposta de teste."


class Candidates:
    """An alternate retrieval path deliberately ignores the prefilter."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.filters = []

    def count(self):
        return len(self.chunks) or 1

    def query(self, embedding, top_k, **filters):
        self.filters.append(filters)
        return [
            c for c in self.chunks if not filters.get("sector") or c.sector == filters["sector"]
        ][:top_k]


def pipeline(chunks, scope="pos_graduacao", **kwargs):
    remote = Remote(scope)
    store = Candidates(chunks)
    service = RagService(
        openrouter=remote,
        vector_store=store,
        top_k=5,
        embedding_model="test",
        llm_model="test",
        system_prompt=V2_SYSTEM_PROMPT,
    )
    agent = AgenticRagService(
        service, NormativeRouter(remote), VersionFilter(NormativeRegistry.load()), **kwargs
    )
    return service, remote, store, agent


@pytest.mark.parametrize(
    "question",
    [
        "Qual era a regra na 658/2024 e qual é a regra atual na 956/2025?",
        "Como era o §4º do art. 68 antes da alteração de 2026?",
    ],
)
def test_explicit_comparison_or_before_amendment_needs_historical_evidence(question):
    assert is_historical_question(question, obsolete_norm_ids=["ufpi-658-2024"])


def test_amendment_is_idempotent_and_does_not_discard_already_filtered_context():
    vf = VersionFilter(NormativeRegistry.load())
    original = real_chunk("177-2012", "68")
    first, _ = vf.apply([original])
    second, audit = vf.apply(first)
    assert len(second) == 1
    assert second[0].content == first[0].content
    assert second[0].id == original.id
    assert not audit.removed_references
    assert second[0].content.count("independentemente de seu vínculo com a UFPI") == 1


@pytest.mark.asyncio
async def test_comparison_preserves_revoked_text_and_current_text_in_captured_prompt():
    _, remote, store, agent = pipeline(
        [real_chunk("658-2024", "43"), real_chunk("956-2025", "53", 2)]
    )
    result = await agent.query("Qual era a regra na 658/2024 e qual é a regra atual na 956/2025?")
    assert {r.source for r in result.references} == {
        "Resolução CEPEX/UFPI nº 658/2024",
        "Resolução CEPEX/UFPI nº 956/2025",
    }
    assert not store.filters[0].get("excluded_sources")
    assert "COMPARAÇÃO TEMPORAL" in remote.prompts[0]["user_prompt"]
    assert result.version_filter["temporal_intent"]["mode"] == "comparison"


@pytest.mark.asyncio
async def test_before_amendment_does_not_send_later_act_to_generator():
    base = real_chunk("177-2012", "68")
    _, remote, _, agent = pipeline([base, real_chunk("1056-2026", "1", 2)], "graduacao")
    result = await agent.query("Como era o §4º do art. 68 antes da alteração de 2026?")
    assert len(result.references) == 1
    assert result.references[0].content == base.content
    assert "independentemente de seu vínculo com a UFPI" not in remote.prompts[0]["user_prompt"]
    assert "CONSULTA HISTÓRICA" in remote.prompts[0]["user_prompt"]
    assert "contextualize temporalmente" in remote.prompts[0]["user_prompt"]


@pytest.mark.asyncio
async def test_validity_uses_registry_evidence_even_when_dense_retrieval_misses_article_62():
    _, remote, _, agent = pipeline([real_chunk("658-2024", "43")])
    result = await agent.query("A Resolução 658/2024 ainda está vigente na pós-graduação?")
    assert result.references and result.references[0].article_number == "62"
    assert result.references[0].source == "Resolução CEPEX/UFPI nº 956/2025"
    assert "VI -a Resolução CEPEX/UFPI Nº 658" in remote.prompts[0]["user_prompt"]
    assert "658-2024-art-43" not in {c["id"] for c in result.version_filter["final_references"]}


@pytest.mark.asyncio
async def test_unknown_status_is_disclosed_to_generator_without_claim_of_current_validity():
    _, remote, _, agent = pipeline([real_chunk("956-2025", "53")])
    await agent.query("Qual é a regra atual no mestrado?")
    prompt = remote.prompts[0]["user_prompt"]
    assert "desconhecida" in prompt
    assert "não certifica vigência" in prompt


@pytest.mark.asyncio
async def test_unresolved_amendment_abstains_even_if_unrelated_chunks_remain():
    broken = real_chunk("177-2012", "68").model_copy(
        update={"content": "Art. 68. Conversão incompleta."}
    )
    _, remote, _, agent = pipeline([broken, real_chunk("177-2012", "69", 2)], "graduacao")
    result = await agent.query("Como é atualmente o §4º do art. 68 na graduação?")
    assert result.generation_attempts == 0
    assert result.references == []
    assert remote.prompts == []
    assert result.version_filter["removed_references"][0]["reason"] == "amendment_unresolved"


@pytest.mark.parametrize("scope", ["graduacao", "pos_graduacao", "ambos"])
def test_manual_api_uses_temporal_filter_without_calling_router(scope):
    service, remote, store, agent = pipeline(
        [real_chunk("658-2024", "43"), real_chunk("177-2012", "68", 2)]
    )
    client = TestClient(
        create_app(
            BaselineSettings(_env_file=None),
            service=service,
            vector_store=store,
            agentic_service=agent,
        )
    )
    response = client.post("/query", json={"question": "Qual a regra atual?", "sector": scope})
    assert response.status_code == 200
    result = response.json()
    assert "version_filter" in result
    assert all(r["source"] != "Resolução CEPEX/UFPI nº 658/2024" for r in result["references"])
    assert remote.routes == []
    assert "route" not in result


@pytest.mark.asyncio
async def test_default_v1_clarifies_without_running_probe_or_generator():
    _, remote, store, agent = pipeline([real_chunk("956-2025", "53")], None)
    result = await agent.query("Posso cancelar uma disciplina?")
    assert result.needs_clarification
    assert store.filters == remote.prompts == []
    assert BaselineSettings(_env_file=None).ROUTING_MODE == "intent_v1"


@pytest.mark.asyncio
async def test_current_safety_check_keeps_only_eligible_chunks_and_references():
    _, remote, _, agent = pipeline([real_chunk("956-2025", "53"), real_chunk("658-2024", "43", 2)])
    result = await agent.query("Qual é atualmente a regra no mestrado?")
    assert len(result.references) == 1
    assert result.references[0].article_number == "53"
    assert "Artigo: Art. 43" not in remote.prompts[0]["user_prompt"]
    assert result.version_filter["removed_references"][0]["reason"] == "revogada"


@pytest.mark.asyncio
async def test_historical_revoked_context_remains_citable():
    old = real_chunk("658-2024", "43")
    _, remote, _, agent = pipeline([old])
    result = await agent.query("Segundo a Resolução 658/2024, como era a regra no mestrado?")
    assert result.references[0].content == old.content
    assert "CONSULTA HISTÓRICA" in remote.prompts[0]["user_prompt"]


@pytest.mark.asyncio
async def test_empty_context_never_invokes_generator():
    _, remote, _, agent = pipeline([])
    result = await agent.query("Qual a regra atual no mestrado?")
    assert result.references == [] and result.generation_attempts == 0
    assert remote.prompts == []


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Qual é a regra hoje?", "current"),
        ("Como era a regra na 658/2024?", "historical"),
        ("Antes da alteração de 2026, qual era a redação do §4º do art. 68?", "historical"),
        ("Qual era a regra na 658/2024 e qual é a posterior na 956/2025?", "comparison"),
        ("A Resolução 658/2024 ainda está vigente?", "validity"),
        ("Qual a regra de frequência?", "indeterminate"),
        ("Compare a frequência na graduação e na pós.", "indeterminate"),
        ("A regra antiga é aplicável atualmente?", "current"),
    ],
)
def test_temporal_states_are_explicit_and_do_not_confuse_domain_comparison(question, expected):
    from rag_baseline.agentic import classify_temporal_intent

    result = classify_temporal_intent(question, registry=NormativeRegistry.load())
    assert result.mode == expected


@pytest.mark.asyncio
async def test_amendment_question_uses_documentary_basis_without_general_article_lookup():
    _, remote, _, agent = pipeline([real_chunk("177-2012", "69")], "graduacao")
    result = await agent.query("Qual norma alterou o §4º do art. 68 da graduação?")
    assert result.references[0].source == "Resolução CEPEX/UFPI nº 1.056/2026"
    assert result.references[0].article_number == "1"
    assert "independentemente de seu vínculo com a UFPI" in remote.prompts[0]["user_prompt"]


@pytest.mark.asyncio
async def test_both_retains_eligible_evidence_from_each_domain():
    _, _, _, agent = pipeline(
        [
            real_chunk("177-2012", "69"),
            real_chunk("956-2025", "53", 2),
            real_chunk("658-2024", "43", 3),
        ],
        "ambas",
    )
    result = await agent.query("Compare atualmente as regras da graduação e da pós.")
    assert {r.sector for r in result.references} == {"graduacao", "pos_graduacao"}
    assert len(result.references) == 2


def test_provenance_distinguishes_exclusion_overlay_and_untouched_evidence():
    vf = VersionFilter(NormativeRegistry.load())
    final, audit = vf.apply(
        [
            real_chunk("177-2012", "68"),
            real_chunk("658-2024", "43", 2),
            real_chunk("956-2025", "53", 3),
        ]
    )
    actions = {p.temporal_action for p in audit.provenance}
    assert {"amendment_applied", "excluded_revoked", "kept_current"} <= actions
    assert len(final) == 2
    assert all(p.source_norm and p.source_article for p in audit.provenance)
    assert all(p.relation_source for p in audit.provenance if p.temporal_action != "kept_current")


@pytest.mark.asyncio
async def test_citation_granularity_prompt_and_reference_metadata_remain_article_only():
    _, remote, _, agent = pipeline([real_chunk("177-2012", "68")], "graduacao")
    result = await agent.query("Como é atualmente o §4º do art. 68 na graduação?")
    assert "só cite parágrafo, inciso ou alínea" in remote.prompts[0]["system_prompt"]
    fields = result.references[0].model_dump()
    assert fields["article_number"] == "68"
    assert not {"paragraph", "inciso", "alinea"} & fields.keys()


@pytest.mark.asyncio
async def test_calendar_history_abstains_when_effective_dates_are_not_documented():
    _, remote, _, agent = pipeline(
        [real_chunk("177-2012", "68"), real_chunk("1056-2026", "1", 2)], "graduacao"
    )
    result = await agent.query("Em 2025, como era o §4º do art. 68 da graduação?")
    assert result.generation_attempts == 0
    assert result.references == [] and remote.prompts == []
    assert result.version_filter["insufficient_reason"] == "chronology_unresolved"


@pytest.mark.asyncio
async def test_historical_prefilter_exclusions_are_recorded_in_audit():
    _, _, store, agent = pipeline([real_chunk("177-2012", "68")], "graduacao")
    result = await agent.query("Como era o §4º do art. 68 antes da alteração de 2026?")
    assert "Resolução CEPEX/UFPI nº 1.056/2026" in store.filters[0]["excluded_sources"]
    assert result.version_filter["prefilter_excluded_norm_ids"] == ["ufpi-1056-2026"]


@pytest.mark.asyncio
async def test_registry_relation_evidence_respects_resolved_domain():
    _, remote, _, agent = pipeline([], "pos_graduacao")
    result = await agent.query("Qual norma alterou o parágrafo 4 do art. 68 da pós-graduação?")
    assert result.references == [] and remote.prompts == []


@pytest.mark.asyncio
async def test_historical_target_without_norm_number_excludes_known_later_wording():
    _, remote, _, agent = pipeline(
        [real_chunk("177-2012", "68"), real_chunk("1056-2026", "1", 2)], "graduacao"
    )
    result = await agent.query("Como era o parágrafo 4 do art. 68 da graduação?")
    assert len(result.references) == 1
    assert "independentemente de seu vínculo com a UFPI" not in remote.prompts[0]["user_prompt"]


@pytest.mark.asyncio
async def test_comparison_with_one_missing_side_abstains_before_generation():
    _, remote, _, agent = pipeline([real_chunk("658-2024", "43")])
    result = await agent.query("Qual era a regra na 658/2024 e qual é a regra atual na 956/2025?")
    assert result.generation_attempts == 0 and result.references == []
    assert remote.prompts == []
    assert result.version_filter["insufficient_reason"] == "comparison_evidence_missing"


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Compare a redação antiga da 658/2024 com a atual da 956/2025.", "comparison"),
        ("Não quero a regra atual; como era a regra na 658/2024?", "historical"),
    ],
)
def test_old_wording_and_negated_current_request_preserve_temporal_intent(question, expected):
    from rag_baseline.agentic import classify_temporal_intent

    assert classify_temporal_intent(question, registry=NormativeRegistry.load()).mode == expected


@pytest.mark.asyncio
async def test_metric_does_not_treat_unknown_or_unexpected_norm_as_temporal_violation():
    from rag_baseline.temporal_evaluation import DATASET, inspect_case

    item = next(
        q
        for q in json.loads(DATASET.read_text(encoding="utf-8"))["items"]
        if q["id"] == "G2_unaffected"
    )
    _, _, _, agent = pipeline([real_chunk("1056-2026", "1")], "graduacao")
    result = await agent.query(item["question"])
    row = inspect_case(item, result, NormativeRegistry.load(), live=True)
    assert row["measurements"]["final_eligible_n"] == 1
    assert row["measurements"]["reference_eligible_n"] == 1
    assert row["measurements"]["obsolete_n"] == 0
    assert "VERSION_FILTER" not in row["failure_layers"]
    assert "RETRIEVAL" in row["failure_layers"]


def test_metric_empty_denominators_are_null_instead_of_perfect_scores():
    from rag_baseline.temporal_evaluation import summarize

    metrics = summarize([])["metrics"]
    assert metrics["obsolete_context_exposure_rate"] == {
        "numerator": 0,
        "denominator": 0,
        "value": None,
    }
    assert metrics["historical_preservation_rate"]["value"] is None


@pytest.mark.asyncio
async def test_metric_does_not_blame_retrieval_when_router_stops_pipeline():
    from rag_baseline.temporal_evaluation import DATASET, inspect_case

    item = next(
        q
        for q in json.loads(DATASET.read_text(encoding="utf-8"))["items"]
        if q["id"] == "G1_current"
    )
    # Exercise an actual Router stop; declared levels now resolve before it.
    item = {**item, "question": "Como funciona atualmente a coordenação de estágio?"}
    _, _, _, agent = pipeline([real_chunk("177-2012", "68")], None)
    result = await agent.query(item["question"])
    row = inspect_case(item, result, NormativeRegistry.load(), live=True)
    assert row["failure_layers"] == ["ROUTER"]
    assert not row["measurements"]["amendment_applicable"]


@pytest.mark.asyncio
async def test_metric_attributes_missing_explicit_article_to_retrieval():
    from rag_baseline.temporal_evaluation import DATASET, inspect_case

    item = next(
        q
        for q in json.loads(DATASET.read_text(encoding="utf-8"))["items"]
        if q["id"] == "G2_unaffected"
    )
    _, _, _, agent = pipeline([real_chunk("177-2012", "101")], "graduacao")
    result = await agent.query(item["question"])
    row = inspect_case(item, result, NormativeRegistry.load(), live=True)
    assert row["failure_layers"] == ["RETRIEVAL"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case_id,norm,article,scope",
    [
        ("P1_current", "658-2024", "43", "pos_graduacao"),
        ("G3_historical", "1056-2026", "1", "graduacao"),
    ],
)
async def test_reference_metric_requires_temporally_eligible_context(case_id, norm, article, scope):
    from rag_baseline.temporal_evaluation import DATASET, inspect_case

    item = next(
        q for q in json.loads(DATASET.read_text(encoding="utf-8"))["items"] if q["id"] == case_id
    )
    _, _, _, agent = pipeline([real_chunk(norm, article)], scope)
    result = await agent.query(item["question"], use_version_filter=False)
    row = inspect_case(item, result, NormativeRegistry.load(), live=True)
    assert row["measurements"]["reference_n"] == 1
    assert row["measurements"]["reference_eligible_n"] == 0
