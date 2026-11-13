"""Reproducible local wiring checks, not retrieval/answer quality evaluation.

Run from the repository with code/src and existing dependencies on PYTHONPATH.
The selected embedding is replayed from the existing index. All router/provider
responses are controlled fixtures; HTTP provider requests are forbidden.
"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import chromadb
from chromadb.config import Settings
from rag_baseline.incremental_index import snapshot_collection
from rag_baseline.router import NormativeRouter
from rag_baseline.service import RagService
from rag_baseline.tool_contracts import NormativeToolResult
from rag_baseline.tool_facade import NormativeRagFacade
from rag_baseline.vector_store import ChromaVectorStore
from rag_baseline.versioning import NormativeRegistry, VersionFilter

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).with_name("local_probes.json")


class Provider:
    llm_model = "offline-controlled"

    def __init__(self, scope, embedding):
        self.scope, self.embedding = scope, embedding
        self.routing_calls = self.embedding_calls = self.generation_calls = 0

    async def structured_chat(self, **_):
        self.routing_calls += 1
        return json.dumps(
            dict(
                scope=self.scope,
                needs_clarification=self.scope is None,
                clarification_question="Graduação ou pós-graduação?"
                if self.scope is None
                else None,
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
        return [self.embedding]

    async def chat(self, **_):
        self.generation_calls += 1
        return "Verificação controlada do transporte de resultado."


class ObservedStore(ChromaVectorStore):
    def __init__(self, *args):
        super().__init__(*args)
        self.calls = []

    def query(self, embedding, top_k, *, sector=None, excluded_sources=None):
        self.calls.append(dict(top_k=top_k, sector=sector, excluded_sources=excluded_sources))
        return super().query(embedding, top_k, sector=sector, excluded_sources=excluded_sources)


async def main():
    client = chromadb.PersistentClient(
        path=str(ROOT / "code/.local/chroma"), settings=Settings(anonymized_telemetry=False)
    )
    collection = client.get_collection("ufpi_duas_regulacoes_setor")
    before = snapshot_collection(collection)
    assert before["count"] == 507
    rows = collection.get(include=["metadatas", "embeddings"])
    seeds = {
        scope: next(
            list(map(float, vector))
            for metadata, vector in zip(rows["metadatas"], rows["embeddings"], strict=True)
            if metadata.get("sector") == scope and metadata.get("article_number") == article
        )
        for scope, article in [("graduacao", "69"), ("pos_graduacao", "53")]
    }
    probes = []
    with patch("httpx.AsyncClient.send", side_effect=AssertionError("Network forbidden in probes")):
        for scope, question in [
            ("graduacao", "Qual é a regra atual do art. 69 na graduação?"),
            ("pos_graduacao", "Quais os requisitos atuais de defesa na pós-graduação?"),
            ("ambas", "Compare as regras de graduação e pós-graduação."),
            (None, "Posso cancelar uma disciplina?"),
        ]:
            provider = Provider(scope, seeds.get(scope, seeds["graduacao"]))
            store = ObservedStore(ROOT / "code/.local/chroma", collection.name)
            service = RagService(
                openrouter=provider,
                vector_store=store,
                top_k=5,
                embedding_model="offline-replayed-1536",
                llm_model=provider.llm_model,
            )
            facade = NormativeRagFacade(
                service, NormativeRouter(provider), VersionFilter(NormativeRegistry.load())
            )
            result = await facade.query(question)
            expected = "CLARIFICATION" if scope is None else "ANSWER"
            assert result.status.value == expected, (scope, result.model_dump())
            assert result.domain == scope and provider.routing_calls == 1
            if scope is None:
                assert (
                    store.calls == [] and provider.embedding_calls == provider.generation_calls == 0
                )
            else:
                assert len(store.calls) == 1 and store.calls[0]["top_k"] == 5
                assert store.calls[0]["sector"] == (None if scope == "ambas" else scope)
                assert result.internal_audit.output_audit.guard_version == "2"
                assert result.temporal_provenance.evidence_states
            assert NormativeToolResult.from_persistence(result.to_persistence()) == result
            probes.append(
                dict(
                    scope=scope,
                    question=question,
                    status=result.status.value,
                    routing_calls=provider.routing_calls,
                    embedding_fixture_calls=provider.embedding_calls,
                    generation_fixture_calls=provider.generation_calls,
                    vector_calls=store.calls,
                    result=result.model_dump(mode="json"),
                    persistence_roundtrip_equal=True,
                )
            )
    after = snapshot_collection(collection)
    assert before == after
    artifact = dict(
        timestamp=datetime.now(UTC).isoformat(),
        purpose="Offline wiring only, not quality evaluation",
        real_router_llm_calls=0,
        real_embedding_calls=0,
        real_generation_calls=0,
        embedding="Replay of existing 1536-dimensional vector, not semantic query embedding",
        scope_decisions="Controlled provider JSON consumed by real NormativeRouter V1",
        collection=collection.name,
        index_count=after["count"],
        before_sha256=before["sha256"],
        after_sha256=after["sha256"],
        index_identical=before == after,
        probes=probes,
    )
    OUTPUT.write_bytes((json.dumps(artifact, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(
        json.dumps(
            {
                "probes": len(probes),
                "index_identical": True,
                "statuses": [p["status"] for p in probes],
                "real_provider_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
