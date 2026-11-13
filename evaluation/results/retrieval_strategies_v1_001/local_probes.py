"""Offline structural/wiring verification on the existing, unmodified collection."""

import asyncio
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from rag_baseline.incremental_index import snapshot_collection
from rag_baseline.retrieval_engines import MetadataExactEngine
from rag_baseline.retrieval_policy import NormativeIdentityResolver, RetrievalStrategySelector
from rag_baseline.router import NormativeRouter
from rag_baseline.service import RagService
from rag_baseline.tool_contracts import NormativeToolResult
from rag_baseline.tool_facade import NormativeRagFacade
from rag_baseline.vector_store import ChromaVectorStore
from rag_baseline.versioning import NormativeRegistry, VersionFilter

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).parent


class Provider:
    llm_model = "offline-controlled"

    def __init__(self, scope, vector):
        self.scope, self.vector = scope, vector
        self.routing_calls = self.embedding_calls = self.generation_calls = 0

    async def structured_chat(self, **_):
        self.routing_calls += 1
        return json.dumps(
            dict(
                scope=self.scope,
                needs_clarification=self.scope is None,
                clarification_question="Graduação ou pós?" if self.scope is None else None,
                reason_code={
                    None: "insufficient_scope_signal",
                    "graduacao": "explicit_graduacao",
                    "pos_graduacao": "explicit_pos",
                    "ambas": "cross_norm_comparison",
                }[self.scope],
            )
        )

    async def embed(self, _):
        self.embedding_calls += 1
        return [self.vector]

    async def chat(self, **_):
        self.generation_calls += 1
        return "Verificação controlada de transporte."


def save(name, value):
    (OUTPUT / name).write_bytes(
        (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )


async def main():
    registry = NormativeRegistry.load()
    resolver = NormativeIdentityResolver(registry)
    selector = RetrievalStrategySelector(registry)
    store = ChromaVectorStore(ROOT / "code/.local/chroma", "ufpi_duas_regulacoes_setor")
    before = snapshot_collection(store.collection)
    assert before["count"] == 507
    rows = store.collection.get(include=["metadatas", "embeddings"])
    resolved, sources, methods, seeds = [], defaultdict(Counter), Counter(), {}
    for chunk_id, metadata, vector in zip(
        rows["ids"], rows["metadatas"], rows["embeddings"], strict=True
    ):
        identity = resolver.resolve(chunk_id, metadata)
        assert identity.norm_id is not None, chunk_id
        resolved.append(identity)
        methods[identity.method] += 1
        sources[identity.source][identity.norm_id] += 1
        seeds.setdefault(identity.norm_id, list(map(float, vector)))
    assert all(len(norms) == 1 for norms in sources.values())
    save(
        "identity_inventory.json",
        dict(
            records=507,
            resolved=507,
            methods=dict(methods),
            source_to_norm_counts={source: dict(counts) for source, counts in sources.items()},
            norm_counts=dict(Counter(i.norm_id for i in resolved)),
            metadata_updated=False,
            subdivision_metadata_validated=False,
        ),
    )
    dataset = json.loads(
        (ROOT / "evaluation/datasets/retrieval_strategy_regression_v1.json").read_text("utf-8")
    )
    selections, exacts = [], []
    for case in dataset:
        plan = selector.select(case["question"], scope=case["expected_domain"])
        selections.append(
            dict(
                id=case["id"],
                expected=case["expected_strategy"],
                actual=plan.strategy.value,
                correct=plan.strategy.value == case["expected_strategy"],
                consistency=plan.consistency,
            )
        )
        if case["expected_strategy"] == "metadata_exact":
            result = MetadataExactEngine(store.collection, resolver).retrieve(
                case["expected_norm"], case["expected_article"], top_k=5
            )
            found = any(
                resolver.resolve(c.id, c.model_dump()).norm_id == case["expected_norm"]
                and c.article_number == case["expected_article"]
                for c in result.chunks
            )
            exacts.append(
                dict(
                    id=case["id"],
                    found=found,
                    candidate_ids=[c.id for c in result.chunks],
                    distances=[c.distance for c in result.chunks],
                )
            )
    f2 = json.loads(
        (ROOT / "evaluation/results/failure_analysis_v1/f2_analysis.json").read_text("utf-8")
    )
    cases = [
        ("dense_grad", "Regras de matrícula na graduação?", "graduacao", "ufpi-177-2012", "ANSWER"),
        ("dense_pos", "Requisitos de defesa na pós?", "pos_graduacao", "ufpi-956-2025", "ANSWER"),
        (
            "exact_grad",
            "O que diz o art. 68 da Resolução 177/2012?",
            "graduacao",
            "ufpi-177-2012",
            "ANSWER",
        ),
        (
            "exact_pos",
            "Artigo 53 da Resolução 956/2025",
            "pos_graduacao",
            "ufpi-956-2025",
            "ANSWER",
        ),
        (
            "exact_old",
            "Segundo a 658/2024, como era o art. 37 na pós?",
            "pos_graduacao",
            "ufpi-658-2024",
            "ANSWER",
        ),
        (
            "exact_amending",
            "Art. 1 da Resolução 1.056/2026",
            "graduacao",
            "ufpi-1056-2026",
            "ANSWER",
        ),
        (
            "exact_paragraph",
            "Art. 68, §4º da 177/2012 na graduação",
            "graduacao",
            "ufpi-177-2012",
            "ANSWER",
        ),
        (
            "filtered_grad",
            "Na 177/2012, onde fala sobre estágio?",
            "graduacao",
            "ufpi-177-2012",
            "ANSWER",
        ),
        (
            "filtered_pos",
            "Na 956/2025, onde fala sobre defesa?",
            "pos_graduacao",
            "ufpi-956-2025",
            "ANSWER",
        ),
        (
            "filtered_old",
            "Segundo a 658/2024, como era a defesa?",
            "pos_graduacao",
            "ufpi-658-2024",
            "ANSWER",
        ),
        ("clarification", "Posso cancelar uma disciplina?", None, "ufpi-177-2012", "CLARIFICATION"),
        ("numeric", "nota 7/10", None, "ufpi-177-2012", "CLARIFICATION"),
        ("scope_conflict", "Art. 53 da 956/2025", "graduacao", "ufpi-956-2025", "ERROR"),
        (
            "current_old",
            "Qual a regra atual do art. 37 da 658/2024 na pós?",
            "pos_graduacao",
            "ufpi-658-2024",
            "ERROR",
        ),
        ("f2", f2["question"], "graduacao", "ufpi-177-2012", "ERROR"),
    ]
    probes = []
    with patch("httpx.AsyncClient.send", side_effect=AssertionError("No provider network allowed")):
        for case_id, question, scope, norm, expected in cases:
            provider = Provider(scope, seeds[norm])
            service = RagService(
                openrouter=provider,
                vector_store=store,
                top_k=5,
                embedding_model="offline-replayed-1536",
                llm_model=provider.llm_model,
            )
            result = await NormativeRagFacade(
                service, NormativeRouter(provider), VersionFilter(registry)
            ).query(question)
            audit = result.internal_audit.retrieval_audit
            comparison = None
            if case_id.startswith("dense_"):
                direct = await service.retrieve(
                    question,
                    sector=scope,
                    excluded_sources=audit["filter_applied"]["excluded_sources"],
                    query_embedding=seeds[norm],
                )
                comparison = [dict(id=c.id, rank=c.rank, distance=c.distance) for c in direct] == [
                    {k: c[k] for k in ("id", "rank", "distance")}
                    for c in audit["returned_candidates"]
                ]
            probes.append(
                dict(
                    id=case_id,
                    question=question,
                    controlled_scope=scope,
                    status=result.status.value,
                    expected_status=expected,
                    passed=result.status.value == expected,
                    strategy=result.retrieval_strategy.value,
                    retrieval_audit=audit,
                    routing_fixture_calls=provider.routing_calls,
                    embedding_fixture_calls=provider.embedding_calls,
                    generation_fixture_calls=provider.generation_calls,
                    result=result.model_dump(mode="json"),
                    persistence_roundtrip=NormativeToolResult.from_persistence(
                        result.to_persistence()
                    )
                    == result,
                    dense_ids_ranks_distances_preserved=comparison,
                )
            )
            save("local_probes.json", dict(complete=False, probes=probes))
    after = snapshot_collection(store.collection)
    assert before == after
    filtered = [
        p
        for p in probes
        if p["retrieval_audit"] and p["retrieval_audit"]["strategy"] == "vector_filtered"
    ]
    filtered_candidates = [
        (p, c) for p in filtered for c in p["retrieval_audit"]["returned_candidates"]
    ]
    metadata = [
        p
        for p in probes
        if p["retrieval_audit"]
        and p["retrieval_audit"]["executed"]
        and p["retrieval_audit"]["strategy"] == "metadata_exact"
    ]
    dense = [p for p in probes if p["dense_ids_ranks_distances_preserved"] is not None]

    def metric(n, d):
        return dict(numerator=n, denominator=d)

    metrics = dict(
        strategy_selection=metric(sum(r["correct"] for r in selections), len(selections)),
        exact_article_resolution=metric(sum(r["found"] for r in exacts), len(exacts)),
        norm_filter_purity=metric(
            sum(
                c["norm_id"] == p["retrieval_audit"]["parsed_reference"]["norm_ids"][0]
                for p, c in filtered_candidates
            ),
            len(filtered_candidates),
        ),
        dense_path_preservation=metric(
            sum(p["dense_ids_ranks_distances_preserved"] for p in dense), len(dense)
        ),
        embedding_avoidance=metric(
            sum(p["embedding_fixture_calls"] == 0 for p in metadata), len(metadata)
        ),
        router_scope_conflicts=metric(
            sum(
                p["retrieval_audit"] is not None
                and p["retrieval_audit"]["consistency"] == "scope_conflict"
                for p in probes
            ),
            len(probes),
        ),
    )
    save(
        "technical_regression.json",
        dict(
            scope="Engineering fixtures only; not legal gold",
            selections=selections,
            exact_lookups=exacts,
            metrics=metrics,
            f2_saved_evidence="evaluation/results/failure_analysis_v1/f2_analysis.json",
            f2_note="Article found structurally; facade still declines calendar applicability under frozen temporal policy",
        ),
    )
    save(
        "local_probes.json",
        dict(
            timestamp=datetime.now(UTC).isoformat(),
            complete=True,
            real_provider_calls=0,
            collection=store.collection_name,
            index_count=507,
            index_identical=True,
            before_sha256=before["sha256"],
            after_sha256=after["sha256"],
            controls="Scope JSON and generation are fake; vectors replay stored embeddings; no quality measurement",
            probes=probes,
            metrics=metrics,
        ),
    )
    assert all(p["passed"] and p["persistence_roundtrip"] for p in probes)
    assert all(r["correct"] for r in selections) and all(r["found"] for r in exacts)
    assert (
        metrics["norm_filter_purity"]["numerator"] == metrics["norm_filter_purity"]["denominator"]
    )
    print(
        json.dumps(
            dict(probes=len(probes), metrics=metrics, index_identical=True, real_provider_calls=0)
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
