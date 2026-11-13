"""Structural selection and retrieval boundaries; providers are controlled fakes."""

import asyncio
import importlib
import json

import pytest

from rag_baseline.agentic import AgenticRagService
from rag_baseline.corpus import load_corpus
from rag_baseline.models import RetrievedChunk
from rag_baseline.router import NormativeRouter
from rag_baseline.service import RagService, _reference
from rag_baseline.tool_contracts import NormativeToolResult
from rag_baseline.tool_facade import NormativeRagFacade
from rag_baseline.vector_store import ChromaVectorStore
from rag_baseline.versioning import REGISTRY_PATH, NormativeRegistry, VersionFilter

ROOT = REGISTRY_PATH.parent.parent


@pytest.fixture
def policy():
    name = "rag_baseline.retrieval_policy"
    if importlib.util.find_spec(name) is None:

        class Missing:
            def __getattr__(self, _):
                pytest.fail("Retrieval policy is not implemented")

        return Missing()
    return importlib.import_module(name)


@pytest.fixture
def engines():
    name = "rag_baseline.retrieval_engines"
    if importlib.util.find_spec(name) is None:

        class Missing:
            def __getattr__(self, _):
                pytest.fail("Retrieval engines are not implemented")

        return Missing()
    return importlib.import_module(name)


@pytest.fixture
def registry():
    return NormativeRegistry.load()


@pytest.mark.parametrize(
    "query,norm,article",
    [
        ("Resolução 177/2012, art. 68", "ufpi-177-2012", "68"),
        ("Resolução nº 177/2012, art 68", "ufpi-177-2012", "68"),
        ("artigo 53 da Resolução 956/2025", "ufpi-956-2025", "53"),
        ("Art. 37 da 658/2024", "ufpi-658-2024", "37"),
        ("1.056/2026, artigo 1", "ufpi-1056-2026", "1"),
        ("1056/2026, art. 2", "ufpi-1056-2026", "2"),
        ("art. 68, §4º da 177/2012", "ufpi-177-2012", "68"),
    ],
)
def test_reference_parser_recognizes_bound_document_article(policy, registry, query, norm, article):
    parsed = policy.NormativeQueryReferenceParser(registry).parse(query)
    assert parsed.norm_id == norm and parsed.article == article
    assert not parsed.ambiguous
    assert parsed.raw_norm_references and parsed.raw_article_references


@pytest.mark.parametrize("query", ["faltam 20%", "10 dias", "turma 2025", "nota 7/10"])
def test_non_normative_numbers_are_not_norms(policy, registry, query):
    parsed = policy.NormativeQueryReferenceParser(registry).parse(query)
    assert parsed.norm_id is None and not parsed.raw_norm_references


@pytest.mark.parametrize(
    "query,strategy",
    [
        ("Posso cancelar uma disciplina?", "dense_vector"),
        ("O que diz o art. 68?", "dense_vector"),
        ("§4º", "dense_vector"),
        ("na resolução antiga", "dense_vector"),
        ("Resolução 956/2025", "dense_vector"),
        ("Na Resolução 956/2025, onde fala sobre cancelamento?", "vector_filtered"),
        ("Resolução 177/2012, art. 68", "metadata_exact"),
        ("Compare a 658/2024 com a 956/2025.", "dense_vector"),
        ("Compare os arts. 52 e 53 da Resolução 956/2025.", "dense_vector"),
        ("Compare os artigos 52 a 54 da Resolução 956/2025.", "dense_vector"),
        ("Art. 68 na graduação; a Resolução 956/2025 trata de outro assunto?", "dense_vector"),
        ("Art. 1 da Resolução 999/2099", "dense_vector"),
        ("Art. 1 da Resolução 01056/2026", "dense_vector"),
    ],
)
def test_selector_is_conservative_without_unique_binding(policy, registry, query, strategy):
    plan = policy.RetrievalStrategySelector(registry).select(query, scope="ambas")
    assert plan.strategy.value == strategy


@pytest.mark.parametrize(
    "scope,consistency",
    [
        ("graduacao", "scope_conflict"),
        ("pos_graduacao", "consistent"),
        ("ambas", "consistent"),
        (None, "router_clarification"),
    ],
)
def test_selector_does_not_correct_router_scope(policy, registry, scope, consistency):
    plan = policy.RetrievalStrategySelector(registry).select("956/2025, art. 53", scope=scope)
    assert plan.consistency == consistency


def test_unknown_norm_is_reported_without_guessing(policy, registry):
    plan = policy.RetrievalStrategySelector(registry).select(
        "Art. 3 da 999/2099", scope="graduacao"
    )
    assert plan.consistency == "unknown_norm" and plan.reference.norm_id is None


@pytest.mark.parametrize(
    "kind,method",
    [
        ("explicit", "metadata"),
        ("id", "chunk_id"),
        ("source", "source"),
        ("unknown", "unknown"),
    ],
)
def test_identity_uses_structural_priority_without_status(policy, registry, kind, method):
    source = registry.norms[0].sources[0]
    row = dict(source=source, sector="graduacao", article_number="68")
    chunk_id = "unrelated-id"
    if kind == "explicit":
        row["norm_id"] = "ufpi-177-2012"
    if kind == "id":
        chunk_id = "ufpi-177-2012-art-68-0000"
    if kind == "unknown":
        row["source"] = "unknown source"
    identity = policy.NormativeIdentityResolver(registry).resolve(chunk_id, row)
    assert identity.method == method
    assert identity.norm_id == (None if kind == "unknown" else "ufpi-177-2012")
    assert row.get("norm_id") == ("ufpi-177-2012" if kind == "explicit" else None)


@pytest.mark.parametrize("conflict", ["id", "sector"])
def test_conflicting_identity_is_not_used(policy, registry, conflict):
    row = dict(
        norm_id="ufpi-177-2012",
        source=registry.norms[0].sources[0],
        sector="pos_graduacao" if conflict == "sector" else "graduacao",
        article_number="68",
    )
    chunk_id = "ufpi-956-2025-art-68-0000" if conflict == "id" else "ufpi-177-2012-art-68-0000"
    identity = policy.NormativeIdentityResolver(registry).resolve(chunk_id, row)
    assert identity.norm_id is None and identity.method == "conflict"


class Provider:
    llm_model = "controlled"

    def __init__(self):
        self.scopes = {}
        self.embeddings, self.prompts, self.routes = [], [], []

    async def structured_chat(self, **payload):
        data = json.loads(payload["user_prompt"])
        self.routes.append(data)
        scope = self.scopes[data["question"]]
        await asyncio.sleep(0)
        return json.dumps(
            dict(
                scope=scope,
                needs_clarification=scope is None,
                clarification_question="Graduação ou pós?" if scope is None else None,
                reason_code={
                    None: "insufficient_scope_signal",
                    "graduacao": "explicit_graduacao",
                    "pos_graduacao": "explicit_pos",
                    "ambas": "cross_norm_comparison",
                }[scope],
            )
        )

    async def embed(self, texts):
        self.embeddings.extend(texts)
        await asyncio.sleep(0)
        return [[1.0, 0.0] for _ in texts]

    async def chat(self, **payload):
        self.prompts.append(payload)
        await asyncio.sleep(0)
        return "Conteúdo controlado."


@pytest.fixture
def runtime(tmp_path, registry):
    store = ChromaVectorStore(tmp_path / "index", "retrieval_strategy_test")
    specs = [
        ("177-2012", "graduacao_setor_v2.json", ["68", "69", "70"]),
        ("956-2025", "pos_graduacao_setor_v2.json", ["52", "53", "54"]),
        ("658-2024", "658_2024_temporal_v1.json", ["37", "43"]),
        ("1056-2026", "1056_2026_temporal_v1.json", ["1", "2"]),
    ]
    chunks = []
    for norm, filename, articles in specs:
        chunks.extend(
            c
            for c in load_corpus(ROOT / "evaluation/corpora" / filename, id_prefix=f"ufpi-{norm}")
            if c.article_number in articles
        )
    assert len(chunks) == 10
    vectors = [
        [1.0, i / 30] if c.sector == "graduacao" else [0.01 + i / 30, 1.0]
        for i, c in enumerate(chunks)
    ]
    store.upsert(chunks, vectors)
    provider = Provider()
    service = RagService(
        openrouter=provider,
        vector_store=store,
        top_k=2,
        embedding_model="controlled",
        llm_model="controlled",
    )
    return service, NormativeRouter(provider), VersionFilter(registry), provider, chunks


@pytest.mark.parametrize(
    "norm,article",
    [
        ("ufpi-177-2012", "68"),
        ("ufpi-956-2025", "53"),
        ("ufpi-658-2024", "37"),
        ("ufpi-1056-2026", "1"),
    ],
)
def test_metadata_exact_finds_real_articles_without_vector_score(
    engines, policy, registry, runtime, norm, article
):
    service, _, _, provider, _ = runtime
    found = engines.MetadataExactEngine(
        service.vector_store.collection, policy.NormativeIdentityResolver(registry)
    ).retrieve(norm, article, top_k=5)
    assert len(found.chunks) == 1
    chunk = found.chunks[0]
    assert chunk.id.startswith(norm + "-art-") and chunk.article_number == article
    assert chunk.rank == 1 and chunk.distance is None
    assert _reference(chunk).distance is None
    assert provider.embeddings == provider.prompts == []


def test_metadata_rank_is_structural_not_vector_ranking(engines, policy, registry, runtime):
    service, _, _, _, chunks = runtime
    original = next(
        c for c in chunks if c.id.startswith("ufpi-177-2012") and c.article_number == "68"
    )
    duplicate = original.model_copy(update={"id": original.id + "-copy", "original_index": -1})
    service.vector_store.upsert([duplicate], [[0.0, 1.0]])
    engine = engines.MetadataExactEngine(
        service.vector_store.collection, policy.NormativeIdentityResolver(registry)
    )
    found = engine.retrieve("ufpi-177-2012", "68", top_k=5)
    assert [c.id for c in found.chunks] == [duplicate.id, original.id]
    assert [c.rank for c in found.chunks] == [1, 2]
    assert all(c.distance is None for c in found.chunks)


@pytest.mark.parametrize(
    "norm,sector",
    [
        ("ufpi-177-2012", "graduacao"),
        ("ufpi-956-2025", "pos_graduacao"),
        ("ufpi-658-2024", "pos_graduacao"),
    ],
)
@pytest.mark.asyncio
async def test_filtered_query_restricts_ids_before_topk(
    engines, policy, registry, runtime, norm, sector
):
    service, _, _, provider, _ = runtime
    engine = engines.FilteredVectorEngine(service, policy.NormativeIdentityResolver(registry))
    found = await engine.retrieve("Tema semântico", norm, sector=sector)
    assert len(found.chunks) == 2
    assert all(c.id.startswith(norm + "-art-") for c in found.chunks)
    assert all(isinstance(c.distance, float) for c in found.chunks)
    assert [c.rank for c in found.chunks] == [1, 2]
    assert len(provider.embeddings) == 1
    ids = found.filters["ids"]
    direct = service.vector_store.collection.query(
        query_embeddings=[[1.0, 0.0]], ids=ids, n_results=2, include=["distances"]
    )
    assert [c.id for c in found.chunks] == direct["ids"][0]
    assert [c.distance for c in found.chunks] == direct["distances"][0]


@pytest.mark.asyncio
async def test_filtered_reuses_supplied_embedding(engines, policy, registry, runtime):
    service, _, _, provider, _ = runtime
    found = await engines.FilteredVectorEngine(
        service, policy.NormativeIdentityResolver(registry)
    ).retrieve("Tema", "ufpi-956-2025", query_embedding=[1.0, 0.0])
    assert found.chunks and provider.embeddings == []


def test_metadata_respects_temporal_exclusions(engines, policy, registry, runtime):
    service, _, vf, _, _ = runtime
    source = next(n.sources[0] for n in registry.norms if n.norm_id == "ufpi-658-2024")
    found = engines.MetadataExactEngine(
        service.vector_store.collection, policy.NormativeIdentityResolver(registry)
    ).retrieve("ufpi-658-2024", "37", top_k=5, excluded_sources=[source])
    assert found.chunks == []


@pytest.mark.parametrize(
    "query,router_query,scope,strategy",
    [
        ("Requisitos na graduação?", "Requisitos na graduação?", "graduacao", "dense_vector"),
        (
            "Art. 68 da 177/2012 na graduação",
            "Art. 68 da 177/2012 na graduação",
            "graduacao",
            "metadata_exact",
        ),
        (
            "Na 956/2025, tema de defesa na pós",
            "Na 956/2025, tema de defesa na pós-graduação",
            "pos_graduacao",
            "vector_filtered",
        ),
        ("Art. 53 da 956/2025", "Art. 53 da 956/2025", "pos_graduacao", "metadata_exact"),
    ],
)
@pytest.mark.asyncio
async def test_facade_reports_actual_strategy_and_same_v2(
    runtime, query, router_query, scope, strategy
):
    service, router, vf, provider, _ = runtime
    provider.scopes[router_query] = scope
    result = await NormativeRagFacade(service, router, vf).query(query)
    # A declared level or a single cited norm settles the domain without the router.
    assert provider.routes == []
    assert result.status.value == "ANSWER" and result.retrieval_strategy.value == strategy
    assert result.internal_audit.output_audit.guard_version == "5"
    assert result.temporal_provenance.evidence_states
    assert result.internal_audit.retrieval_audit["strategy"] == strategy
    candidates = result.internal_audit.retrieval_audit["returned_candidates"]
    assert len(candidates) == result.internal_audit.retrieval_audit["returned_count"]
    assert all(c["id"] and c["norm_id"] and c["article"] for c in candidates)
    assert all((c["distance"] is None) == (strategy == "metadata_exact") for c in candidates)
    assert "retrieval_audit" not in result.model_dump_json()
    assert NormativeToolResult.from_persistence(result.to_persistence()) == result
    assert len(provider.embeddings) == (0 if strategy == "metadata_exact" else 1)


@pytest.mark.asyncio
async def test_router_conflict_stops_all_retrieval(runtime):
    service, router, vf, provider, _ = runtime
    query = "Art. 53 da 956/2025 na graduação"
    result = await NormativeRagFacade(service, router, vf).query(query)
    assert result.status.value == "ERROR" and result.answer is None
    assert result.internal_audit.retrieval_audit["consistency"] == "scope_conflict"
    assert result.internal_audit.retrieval_audit["routed_scope"] == "graduacao"
    assert not result.internal_audit.retrieval_audit["executed"]
    assert provider.embeddings == provider.prompts == []


@pytest.mark.asyncio
async def test_router_clarification_skips_every_strategy(runtime, monkeypatch):
    service, router, vf, provider, _ = runtime
    query = "Qual é o prazo?"
    provider.scopes[query] = None

    def forbidden(*args, **kwargs):
        pytest.fail("No collection access before clarification")

    monkeypatch.setattr(service.vector_store.collection, "get", forbidden)
    result = await NormativeRagFacade(service, router, vf).query(query)
    assert result.status.value == "CLARIFICATION"
    assert provider.embeddings == provider.prompts == []


@pytest.mark.parametrize("strategy", ["metadata_exact", "vector_filtered"])
@pytest.mark.asyncio
async def test_same_revoked_norm_current_vs_historical_uses_temporal_pipeline(runtime, strategy):
    service, router, vf, provider, _ = runtime
    locator = "art. 37 " if strategy == "metadata_exact" else "tema de defesa "
    historical = f"Segundo a 658/2024, como era {locator}na pós?"
    current = f"Qual a regra atual de {locator}da 658/2024 na pós?"
    provider.scopes.update(
        {
            f"Segundo a 658/2024, como era {locator}na pós-graduação?": "pos_graduacao",
            f"Qual a regra atual de {locator}da 658/2024 na pós-graduação?": "pos_graduacao",
        }
    )
    facade = NormativeRagFacade(service, router, vf)
    past = await facade.query(historical)
    assert past.status.value == "ANSWER" and past.retrieval_strategy.value == strategy
    assert all(s.temporal_role == "historical" for s in past.temporal_provenance.evidence_states)
    count = len(provider.prompts)
    now = await facade.query(current)
    # A deliberate refusal is a normal decision, without a generation.
    assert now.status.value == "ANSWER" and now.core_status == "abstained"
    assert len(provider.prompts) == count


@pytest.mark.parametrize("query", ["Regra na graduação?", "Compare graduação e pós."])
@pytest.mark.asyncio
async def test_dense_path_equivalent_to_previous_core(runtime, query):
    service, router, vf, provider, _ = runtime
    provider.scopes[query] = "ambas" if query.startswith("Compare") else "graduacao"
    direct = await AgenticRagService(service, router, vf).query(query)
    after = await NormativeRagFacade(service, router, vf).query(query)
    assert after.answer == direct.answer and after.retrieval_strategy.value == "dense_vector"
    assert [r.model_dump() for r in after.references] == [
        r.model_dump() for r in direct.normative_output.references
    ]
    assert provider.embeddings == [query, query]


@pytest.mark.asyncio
async def test_dense_adapter_preserves_exact_retrieve_arguments(policy, runtime):
    from rag_baseline.retrieval_service import RetrievalExecution, StrategyRagService

    service, _, vf, provider, _ = runtime
    execution = RetrievalExecution()
    adapter = StrategyRagService(service, vf, execution)
    expected = await service.retrieve(
        "Regra?", sector="graduacao", excluded_sources=["excluded"], query_embedding=[1.0, 0.0]
    )
    actual = await adapter.retrieve(
        "Regra?", sector="graduacao", excluded_sources=["excluded"], query_embedding=[1.0, 0.0]
    )
    assert [c.model_dump() for c in actual] == [c.model_dump() for c in expected]
    assert provider.embeddings == []


@pytest.mark.parametrize("pair", ["mixed", "two_filtered"])
@pytest.mark.asyncio
async def test_concurrent_requests_do_not_share_strategy_or_norm_filters(runtime, pair):
    service, router, vf, provider, _ = runtime
    a = "Art. 68 da 177/2012" if pair == "mixed" else "Na 177/2012, regras de estágio"
    b = "Regras na pós?" if pair == "mixed" else "Na 956/2025, regras de defesa"
    router_b = "Regras na pós-graduação?" if pair == "mixed" else b
    provider.scopes.update({a: "graduacao", router_b: "pos_graduacao"})
    facade = NormativeRagFacade(service, router, vf)
    first, second = await asyncio.gather(facade.query(a), facade.query(b))
    assert first.status.value == second.status.value == "ANSWER"
    assert first.retrieval_strategy.value == (
        "metadata_exact" if pair == "mixed" else "vector_filtered"
    )
    assert second.retrieval_strategy.value == (
        "dense_vector" if pair == "mixed" else "vector_filtered"
    )
    amending = {"ufpi-1056-2026"} if pair == "mixed" else set()
    assert {r.norm_id for r in first.references} <= {"ufpi-177-2012", *amending}
    assert all(r.norm_id == "ufpi-956-2025" for r in second.references)
    assert first.correlation_id != second.correlation_id


@pytest.mark.parametrize(
    "override", ["retrieval_strategy", "metadata_exact", "backend", "filter", "article", "norm_id"]
)
@pytest.mark.asyncio
async def test_public_caller_cannot_inject_strategy(runtime, override):
    service, router, vf, _, _ = runtime
    with pytest.raises(TypeError):
        await NormativeRagFacade(service, router, vf).query("Pergunta", **{override: "override"})


def test_metadata_evidence_and_legacy_reference_allow_missing_distance(runtime):
    *_, chunks = runtime
    evidence = RetrievedChunk(**chunks[0].model_dump(), rank=1, distance=None)
    assert evidence.model_dump()["distance"] is None
    assert _reference(evidence).model_dump()["distance"] is None


@pytest.mark.parametrize(
    "query",
    [
        "Compare os artigos 52 ou 53 da Resolução 956/2025.",
        "Compare os arts. 52/53 da Resolução 956/2025.",
        "Art. 68-A da Resolução 177/2012",
        "Art. 68.1 da Resolução 177/2012",
        "Arts. 68 e seguintes da Resolução 177/2012",
        "Compare os artigos 52–54 da 956/2025",
        "Compare os artigos 52—54 da 956/2025",
        "Compare os arts. 52 & 53 da 956/2025",
    ],
)
def test_unsupported_article_expression_does_not_become_single_exact_lookup(
    policy, registry, query
):
    assert (
        policy.RetrievalStrategySelector(registry).select(query, scope="ambas").strategy.value
        == "dense_vector"
    )


def test_unknown_norm_does_not_mask_known_router_conflict(policy, registry):
    plan = policy.RetrievalStrategySelector(registry).select(
        "177/2012 e 999/2099, quais regras de defesa?", scope="pos_graduacao"
    )
    assert plan.consistency == "scope_conflict"


@pytest.mark.parametrize("query", ["Art. 53 da 956/2025", "Regras de defesa na 956/2025"])
@pytest.mark.asyncio
async def test_empty_index_has_same_error_for_new_strategies(runtime, query):
    service, router, vf, provider, _ = runtime
    collection = service.vector_store.collection
    collection.delete(ids=collection.get()["ids"])
    provider.scopes[query] = "pos_graduacao"
    result = await NormativeRagFacade(service, router, vf).query(query)
    assert result.status.value == "ERROR" and result.error_code.value == "index_unavailable"
    assert provider.embeddings == provider.prompts == []
