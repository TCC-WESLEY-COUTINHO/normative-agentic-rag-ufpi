"""Offline wiring probes, with replay vectors and controlled provider outputs."""

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from rag_baseline.agent_graph import build_integrated_graph
from rag_baseline.agent_policy import AgentActionPolicy
from rag_baseline.incremental_index import snapshot_collection
from rag_baseline.retrieval_policy import NormativeIdentityResolver
from rag_baseline.router import NormativeRouter
from rag_baseline.service import RagService
from rag_baseline.tool_contracts import NormativeToolResult
from rag_baseline.tool_facade import NormativeRagFacade
from rag_baseline.vector_store import ChromaVectorStore
from rag_baseline.versioning import NormativeRegistry, VersionFilter

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).parent


def save(name, value):
    (OUTPUT / name).write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


class Provider:
    llm_model = "offline-controlled"

    def __init__(self, seeds):
        self.seeds = seeds
        self.scopes = {}
        self.routes, self.embeddings, self.generations = [], [], []

    async def structured_chat(self, **payload):
        question = json.loads(payload["user_prompt"])["question"]
        self.routes.append(question)
        scope = self.scopes[question]
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
                }[scope],
            )
        )

    async def embed(self, texts):
        self.embeddings.extend(texts)
        await asyncio.sleep(0)
        return [
            self.seeds["ufpi-956-2025" if self.scopes[text] == "pos_graduacao" else "ufpi-177-2012"]
            for text in texts
        ]

    async def chat(self, **_):
        self.generations.append("controlled_generation")
        await asyncio.sleep(0)
        return "Conteúdo controlado para verificar a entrega do resultado."


class CountingFacade:
    def __init__(self, facade):
        self.facade, self.calls, self.results = facade, [], {}

    async def query(self, **kwargs):
        self.calls.append(str(kwargs["correlation_id"]))
        result = await self.facade.query(**kwargs)
        self.results[str(result.correlation_id)] = result
        return result


def row(name, state, facade):
    result = state["normative_result"]
    final = state["messages"][-1].content
    original = facade.results.get(str(result.correlation_id)) if result else None
    public = result.model_dump(mode="json") if result else None
    return dict(
        id=name,
        action=state["action"],
        audit=asdict(state["turn_audit"]),
        result=public,
        final_message=final,
        typed_result=isinstance(result, NormativeToolResult) if result else None,
        structured_preserved=(result.model_dump() == original.model_dump()) if original else None,
        answer_identical=(final == original.answer)
        if original and original.status == "ANSWER"
        else None,
        clarification_identical=(final == original.clarification_question)
        if original and original.status == "CLARIFICATION"
        else None,
        safe_message_identical=(final == original.safe_message)
        if original and original.status == "ERROR"
        else None,
    )


async def main():
    registry = NormativeRegistry.load()
    store = ChromaVectorStore(ROOT / "code/.local/chroma", "ufpi_duas_regulacoes_setor")
    before = snapshot_collection(store.collection)
    resolver = NormativeIdentityResolver(registry)
    data = store.collection.get(include=["metadatas", "embeddings"])
    seeds = {}
    for chunk_id, metadata, vector in zip(
        data["ids"], data["metadatas"], data["embeddings"], strict=True
    ):
        identity = resolver.resolve(chunk_id, metadata)
        seeds.setdefault(identity.norm_id, list(map(float, vector)))
    provider = Provider(seeds)
    service = RagService(
        openrouter=provider,
        vector_store=store,
        top_k=5,
        embedding_model="offline-replay",
        llm_model="offline-controlled",
    )
    facade = CountingFacade(
        NormativeRagFacade(service, NormativeRouter(provider), VersionFilter(registry))
    )
    graph = build_integrated_graph(facade)
    cases = [
        ("greeting", "Oi", "graduacao"),
        ("thanks", "Obrigado", "graduacao"),
        ("mixed", "Bom dia, posso cancelar uma disciplina na graduação?", "graduacao"),
        ("dense", "Como solicitar matrícula na graduação?", "graduacao"),
        ("exact", "Art. 68 da Resolução 177/2012", "graduacao"),
        (
            "filtered",
            "Na Resolução 956/2025, quais as regras de matrícula?",
            "pos_graduacao",
        ),
        ("clarification", "Qual é o prazo?", None),
        ("controlled_error", "Resolução 956/2025, art. 53 na graduação", "graduacao"),
    ]
    rows = []
    for name, question, scope in cases:
        provider.scopes[question] = scope
        counts = [
            len(provider.routes),
            len(provider.embeddings),
            len(provider.generations),
        ]
        state = await graph.ainvoke({"messages": [("human", question)]})
        record = row(name, state, facade)
        record["provider_calls"] = dict(
            zip(
                ["router", "embedding", "generation"],
                [
                    len(provider.routes) - counts[0],
                    len(provider.embeddings) - counts[1],
                    len(provider.generations) - counts[2],
                ],
                strict=True,
            )
        )
        rows.append(record)
    questions = ["Art. 69 da 177/2012", "Na 956/2025, quais as regras de matrícula?"]
    provider.scopes.update(dict(zip(questions, ["graduacao", "pos_graduacao"], strict=True)))
    states = await asyncio.gather(
        *(graph.ainvoke({"messages": [("human", question)]}) for question in questions)
    )
    rows.extend(
        row(name, state, facade)
        for name, state in zip(["concurrent_exact", "concurrent_filtered"], states, strict=True)
    )
    assert (
        states[0]["normative_result"].correlation_id != states[1]["normative_result"].correlation_id
    )
    assert rows[6]["result"]["status"] == "CLARIFICATION"
    assert rows[6]["provider_calls"] == {"router": 1, "embedding": 0, "generation": 0}
    assert rows[7]["result"]["status"] == "ERROR"
    assert rows[4]["result"]["retrieval_strategy"] == "metadata_exact"
    assert rows[5]["result"]["retrieval_strategy"] == "vector_filtered"
    assert rows[3]["result"]["retrieval_strategy"] == "dense_vector"
    assert all(
        r["answer_identical"] is not False and r["structured_preserved"] is not False for r in rows
    )
    assert snapshot_collection(store.collection) == before
    save(
        "local_probes.json",
        {
            "groups": 9,
            "executions": len(rows),
            "rows": rows,
            "index_unchanged": True,
            "index_sha256": before["sha256"],
            "real_api_calls": 0,
            "vector_relevance_evaluated": False,
        },
    )

    # The action dataset tests operational wiring using a typed facade double.
    from normative_facade_fixtures import answer_data

    class DatasetFacade:
        async def query(self, **kwargs):
            data = answer_data()
            data["correlation_id"] = kwargs["correlation_id"]
            return NormativeToolResult(**data)

    counted = CountingFacade(DatasetFacade())
    technical_graph = build_integrated_graph(counted)
    dataset = json.loads(
        (ROOT / "evaluation/datasets/agent_action_policy_v1.json").read_text("utf-8")
    )
    evaluations = []
    for case in dataset:
        state = await technical_graph.ainvoke({"messages": [("human", case["message"])]})
        evaluation = row(case["id"], state, counted)
        evaluation.update(
            expected_action=case["expected_action"],
            normative_question=case["purpose"]
            in {"social_plus_normative", "normative_conceptual", "explicit_article"},
        )
        assert evaluation["action"] == AgentActionPolicy().decide(case["message"]).action
        evaluations.append(evaluation)
    normative = [r for r in evaluations if r["expected_action"] == "NORMATIVE_RAG"]
    questions = [r for r in evaluations if r["normative_question"]]
    answers = [r for r in rows if r["answer_identical"] is not None] + [
        r for r in evaluations if r["answer_identical"] is not None
    ]
    structured = [r for r in rows + evaluations if r["result"]]
    clarifications = [r for r in rows if r["clarification_identical"] is not None]
    metrics = dict(
        action_policy_accuracy=[
            sum(r["action"] == r["expected_action"] for r in evaluations),
            len(evaluations),
        ],
        normative_bypass=[
            sum(r["audit"]["facade_calls"] == 0 for r in normative),
            len(normative),
        ],
        authoritative_answer_preservation=[
            sum(r["answer_identical"] for r in answers),
            len(answers),
        ],
        structured_result_preservation=[
            sum(r["typed_result"] and r["structured_preserved"] for r in structured),
            len(structured),
        ],
        clarification_preservation=[
            sum(r["clarification_identical"] for r in clarifications),
            len(clarifications),
        ],
        direct_false_allow=[
            sum(r["action"] == "DIRECT" for r in questions),
            len(questions),
        ],
        one_facade_call_per_normative_turn=[
            sum(r["audit"]["facade_calls"] == 1 for r in normative),
            len(normative),
        ],
    )
    assert metrics["normative_bypass"][0] == metrics["direct_false_allow"][0] == 0
    save(
        "technical_regression.json",
        {
            "metrics": metrics,
            "cases": evaluations,
            "scope": "Operational fixtures, not a scientific classifier benchmark or legal gold.",
        },
    )
    print(json.dumps(metrics, ensure_ascii=False))


if __name__ == "__main__":
    with (
        patch(
            "httpx.AsyncClient.send",
            side_effect=AssertionError("External HTTP forbidden"),
        ),
        patch("httpx.Client.send", side_effect=AssertionError("External HTTP forbidden")),
    ):
        asyncio.run(main())
