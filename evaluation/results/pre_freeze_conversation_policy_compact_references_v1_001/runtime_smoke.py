"""Controlled pre-freeze smoke using the normal configured runtime/provider/index.

Run inside the local API container; only final output and categorical counters are saved.
No model payloads, credentials or raw drafts are recorded.
"""

import asyncio
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from rag_baseline.conversation_contracts import ConversationIdentity
from rag_baseline.incremental_index import snapshot_collection
from rag_baseline.integrated_runtime import AGENT_ID, build_integrated_agent_runtime
from rag_baseline.scope_gate import SCOPE_GATE_PROMPT
from service.normative_transport import project_integrated_state

EXTERNAL = "quantos anos tem a cidade mais antiga do piauí?"
NEW_QUERY = (
    "Faço mestrado e estou doente. Qual é a diferença entre cancelar uma matéria e trancar o curso?"
)


async def main():
    path = Path(sys.argv[1])
    if path.exists():
        raise FileExistsError("Refuse to overwrite an operational smoke")
    output = dict(
        kind="Technical pre-freeze smoke; no legal correctness scoring",
        started_at=datetime.now(UTC).isoformat(),
        probes=[],
    )

    def save():
        path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    async with build_integrated_agent_runtime(InMemorySaver()) as runtime:
        provider = runtime.service.openrouter
        destination = urlparse(provider.base_url)
        assert destination.scheme == "https" and destination.hostname == "openrouter.ai"
        output["config"] = dict(
            llm_model=provider.llm_model,
            router_model=runtime.router.model,
            scope_gate_model=runtime.router.model,
            scope_prompt_sha256=hashlib.sha256(SCOPE_GATE_PROMPT.encode()).hexdigest(),
            temperature=provider.llm_temperature,
            max_tokens=provider.llm_max_tokens,
            embedding_model=provider.embedding_model,
            top_k=runtime.service.top_k,
            routing_mode="intent_v1",
            provider_host=destination.hostname,
        )
        output["index_before"] = {
            key: value
            for key, value in snapshot_collection(runtime.index.store.collection).items()
            if key in ["count", "sha256"]
        }
        output["production_hashes"] = {
            str(path.relative_to("/app")): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in Path("/app/code/src").rglob("*.py")
        }
        calls = {
            "router": [],
            "retrieval": [],
            "provider": [],
            "scope_provider": [],
            "normative_provider": [],
        }
        native_route, native_retrieve, native_post = (
            runtime.router.route,
            runtime.service.retrieve,
            provider._post,
        )
        native_structured = provider.structured_chat
        scope_active = False

        async def structured(**kwargs):
            nonlocal scope_active
            is_scope = "decision" in kwargs["schema"].get("properties", {})
            scope_active = is_scope
            try:
                return await native_structured(**kwargs)
            finally:
                scope_active = False

        async def route(question, *, clarification=None):
            start = time.monotonic()
            row = dict(question=question, clarification=clarification)
            calls["router"].append(row)
            decision = await native_route(question, clarification=clarification)
            row.update(
                latency_ms=(time.monotonic() - start) * 1000,
                finished=time.monotonic(),
                decision=decision.model_dump(),
            )
            return decision

        async def retrieve(question, **kwargs):
            calls["retrieval"].append(dict(question=question, started=time.monotonic()))
            return await native_retrieve(question, **kwargs)

        async def post(endpoint, payload):
            row = dict(endpoint=endpoint, role="scope" if scope_active else "normative")
            calls["provider"].append(row)
            calls["scope_provider" if scope_active else "normative_provider"].append(row)
            try:
                return await native_post(endpoint, payload)
            finally:
                row["finished"] = time.monotonic()

        (
            runtime.router.route,
            runtime.service.retrieve,
            provider._post,
            provider.structured_chat,
        ) = route, retrieve, post, structured
        states = {}

        def who():
            return ConversationIdentity(
                user_id="pre-freeze-policy-smoke",
                agent_id=AGENT_ID,
                thread_id=str(uuid4()),
            )

        def pending(state):
            memory = state.get("conversation_memory") if state else None
            return (
                memory.pending_clarification.model_dump(mode="json")
                if memory and memory.pending_clarification
                else None
            )

        async def turn(identity, question, expected):
            started = time.monotonic()
            before = pending(states.get(identity.thread_id))
            counts = {key: len(value) for key, value in calls.items()}
            state = await asyncio.wait_for(
                runtime.graph.ainvoke(
                    {
                        "messages": [("human", question)],
                        "conversation_identity": identity,
                    },
                    {"configurable": {"thread_id": identity.storage_key()}},
                ),
                timeout=120,
            )
            states[identity.thread_id] = state
            message = project_integrated_state(state)
            result = state.get("normative_result")
            correlation = state["turn_audit"].correlation_id
            row = dict(
                question=question,
                expected_action=expected,
                observed_action=state["turn_audit"].conversation_action,
                router_calls=len(calls["router"]) - counts["router"],
                retrieval_calls=len(calls["retrieval"]) - counts["retrieval"],
                provider_calls=len(calls["provider"]) - counts["provider"],
                provider_endpoints=calls["provider"][counts["provider"] :],
                router_inputs=calls["router"][counts["router"] :],
                pending_before=before,
                pending_after=pending(state),
                correlation=correlation,
                correlation_changed=(correlation != before["correlation_id"])
                if before and correlation
                else None,
                final_message=message.model_dump(mode="json"),
                normative_status=result.status if result else None,
                core_status=result.core_status if result else None,
            )
            turn_audit = state["turn_audit"]
            current_router = calls["router"][counts["router"] :]
            current_retrieval = calls["retrieval"][counts["retrieval"] :]
            current_scope = calls["scope_provider"][counts["scope_provider"] :]
            pre_end = (
                current_retrieval[0]["started"]
                if current_retrieval
                else current_router[-1]["finished"]
                if current_router
                else current_scope[-1]["finished"]
                if current_scope
                else started
            )
            row.update(
                scope_decision=turn_audit.scope_gate_decision,
                scope_status=turn_audit.scope_gate_status,
                scope_provider_calls=len(current_scope),
                normative_provider_calls=len(calls["normative_provider"])
                - counts["normative_provider"],
                scope_gate_latency_ms=turn_audit.scope_gate_latency_ms,
                router_latency_ms=sum(item["latency_ms"] for item in current_router),
                total_pre_retrieval_latency_ms=(pre_end - started) * 1000,
            )
            output["probes"].append(row)
            save()
            assert row["observed_action"] == expected, row
            if expected in [
                "ABOUT_ASSISTANT",
                "OUT_OF_SCOPE",
                "SAFE_DIRECT",
                "CLEAR_PENDING",
            ]:
                assert (
                    row["router_calls"],
                    row["retrieval_calls"],
                    row["normative_provider_calls"],
                ) == (0, 0, 0)
                assert row["scope_provider_calls"] == int(expected == "OUT_OF_SCOPE")
            if expected == "NORMATIVE_RAG":
                assert row["scope_decision"] != "OUT_OF_SCOPE" and row["router_calls"] == 1
            print(
                json.dumps(
                    {
                        key: row[key]
                        for key in [
                            "question",
                            "observed_action",
                            "scope_decision",
                            "scope_provider_calls",
                            "router_calls",
                            "retrieval_calls",
                            "provider_calls",
                            "normative_status",
                            "core_status",
                            "correlation_changed",
                        ]
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            return row

        for question in [
            "quem é você?",
            "o que você faz?",
            EXTERNAL,
            "qual o cardápio do RU?",
        ]:
            await turn(
                who(),
                question,
                "OUT_OF_SCOPE"
                if question in [EXTERNAL, "qual o cardápio do RU?"]
                else "ABOUT_ASSISTANT",
            )
        for question in [
            "posso trancar uma disciplina?",
            "Quanto tempo tenho para terminar o mestrado?",
            "essa resolução ainda vale?",
        ]:
            await turn(who(), question, "NORMATIVE_RAG")
        identity = who()
        initial = await turn(identity, "Posso cancelar uma disciplina?", "NORMATIVE_RAG")
        assert initial["pending_after"], (
            "Normal Router did not clarify the planned ambiguous question"
        )
        for question, expected in [
            ("obrigado", "SAFE_DIRECT"),
            ("quem é você?", "ABOUT_ASSISTANT"),
            (EXTERNAL, "OUT_OF_SCOPE"),
        ]:
            interruption = await turn(identity, question, expected)
            assert interruption["pending_after"] == initial["pending_after"]
        continued = await turn(identity, "pós", "CONTINUE_CLARIFICATION")
        assert continued["correlation"] == initial["pending_after"]["correlation_id"]
        identity = who()
        old = await turn(identity, "Posso cancelar uma disciplina?", "NORMATIVE_RAG")
        assert old["pending_after"]
        new = await turn(identity, NEW_QUERY, "NORMATIVE_RAG")
        assert (
            new["correlation_changed"]
            and new["router_inputs"][0]["question"] == NEW_QUERY
            and new["router_inputs"][0]["clarification"] is None
        )
        identity = who()
        await turn(identity, "Posso cancelar uma disciplina?", "NORMATIVE_RAG")
        cancelled = await turn(identity, "cancele", "CLEAR_PENDING")
        assert cancelled["pending_after"] is None
        output["index_after"] = {
            key: value
            for key, value in snapshot_collection(runtime.index.store.collection).items()
            if key in ["count", "sha256"]
        }
        assert (
            output["index_before"] == output["index_after"]
            and output["index_after"]["count"] == 507
        )
        output.update(
            completed_at=datetime.now(UTC).isoformat(),
            success=True,
            legal_review="NOT_PERFORMED; terminal ANSWER is not legal correctness",
            raw_draft_exposed=False,
        )
        save()


if __name__ == "__main__":
    asyncio.run(main())
