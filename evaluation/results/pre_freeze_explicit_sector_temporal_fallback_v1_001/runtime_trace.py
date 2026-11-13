"""Read-only technical traces through the normal runtime; no prompt/payload logging."""

# ruff: noqa: E402

import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

import rag_baseline

# An isolated probe process can load the exact checkout changes without replacing
# files in the running API/UI or altering provider/index configuration.
OVERLAY = os.environ.get("TRACE_SOURCE_OVERLAY")
if OVERLAY:
    rag_baseline.__path__.insert(0, OVERLAY)

import rag_baseline.agentic as agentic
from rag_baseline.conversation_contracts import ConversationIdentity
from rag_baseline.incremental_index import snapshot_collection
from rag_baseline.integrated_runtime import AGENT_ID, build_integrated_agent_runtime
from rag_baseline.routing import question_sector
from rag_baseline.routing_normalization import routing_question
from service.normative_transport import project_integrated_state

QUESTIONS = {
    "A": "A Resolução 658/2024 ainda pode reger hoje a pós-graduação da UFPI ou foi revogada? Qual ato e dispositivo estabelecem isso?",
    "B": "Em um curso de graduação da UFPI ofertado por programa institucional, um professor selecionado por edital, sem vínculo efetivo com a universidade, pode ser coordenador de estágio?",
    "B_exact_block": "Em um curso de graduação da UFPI ofertado por programa institucional,\num professor selecionado por edital, sem vínculo efetivo com a\nuniversidade, pode ser coordenador de estágio?",
}


async def main():
    target = Path(sys.argv[1])
    if target.exists():
        raise FileExistsError("Trace must never overwrite an earlier run")
    output = dict(kind="development technical regression; candidate, not legal gold", cases=[])
    active = {}

    def save():
        target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", "utf-8")

    async with build_integrated_agent_runtime(InMemorySaver()) as runtime:
        provider, vf = runtime.service.openrouter, runtime.facade._version_filter
        output.update(
            timestamp=datetime.now(UTC).isoformat(),
            config=dict(
                llm_model=provider.llm_model,
                router_model=runtime.router.model,
                temperature=provider.llm_temperature,
                max_tokens=provider.llm_max_tokens,
                embedding_model=provider.embedding_model,
                top_k=runtime.service.top_k,
                collection=runtime.index.store.collection.name,
            ),
            source_hashes={
                str(p.relative_to("/app")): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in Path("/app/code/src").rglob("*.py")
            },
        )
        output["index_before"] = {
            k: v
            for k, v in snapshot_collection(runtime.index.store.collection).items()
            if k in {"count", "sha256"}
        }
        output["source_overlay"] = {}
        if OVERLAY:
            for path in Path(OVERLAY).glob("*.py"):
                name = "code/src/rag_baseline/" + path.name
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                output["source_overlay"][name] = digest
                output["source_hashes"][name] = digest
        native_structured, native_route = provider.structured_chat, runtime.router.route
        native_chat = provider.chat
        replay_path = os.environ.get("TRACE_REPLAY_FIRST_GENERATION")
        replay_raw = None
        if replay_path:
            record = json.loads(Path(replay_path).read_text("utf-8"))["relevant_cases"][0]
            replay_raw = record["matching_private_envelope_audit"]["output_audit"]["raw_answer"]
            output["replay_first_generation"] = dict(
                kind="Recorded failing first generation; actual configured provider handles retry",
                artifact_sha256=hashlib.sha256(Path(replay_path).read_bytes()).hexdigest(),
            )
        chat_calls = 0
        native_apply, native_generate = vf.apply, runtime.service.generate
        native_intent, native_core_query = (
            agentic.classify_temporal_intent,
            agentic.AgenticRagService.query,
        )

        async def structured(**kwargs):
            raw = await native_structured(**kwargs)
            if "scope" in kwargs["schema"].get("properties", {}):
                active["router_raw_output"] = raw
            return raw

        async def chat(**kwargs):
            nonlocal chat_calls
            chat_calls += 1
            if replay_raw is not None and chat_calls == 1:
                active["first_generation_source"] = "recorded_manual_failure"
                return replay_raw
            return await native_chat(**kwargs)

        async def route(question, *, clarification=None):
            active["router_inputs"].append(dict(question=question, clarification=clarification))
            decision = await native_route(question, clarification=clarification)
            active["router_validated_decision"] = decision.model_dump(mode="json")
            return decision

        def intent(*args, **kwargs):
            result = native_intent(*args, **kwargs)
            active["temporal_intents"].append(result.model_dump(mode="json"))
            return result

        def apply(chunks, **kwargs):
            active["versionfilter_input"] = [c.model_dump(mode="json") for c in chunks]
            kept, audit = native_apply(chunks, **kwargs)
            active["versionfilter_output"] = [c.model_dump(mode="json") for c in kept]
            active["versionfilter_audit"] = audit.model_dump(mode="json")
            return kept, audit

        async def generate(question, chunks, **kwargs):
            active["eligible_final_chunks"] = [c.model_dump(mode="json") for c in chunks]
            grounding = kwargs.get("temporal_grounding")
            active["temporal_grounding"] = grounding.model_dump(mode="json") if grounding else None
            result = await native_generate(question, chunks, **kwargs)
            active["generation_audit"] = (
                result.output_audit.model_dump(mode="json") if result.output_audit else None
            )
            return result

        async def core_query(self, *args, **kwargs):
            result = await native_core_query(self, *args, **kwargs)
            active["core_result"] = result.model_dump(mode="json")
            return result

        provider.structured_chat, runtime.router.route = structured, route
        provider.chat = chat
        vf.apply, runtime.service.generate = apply, generate
        agentic.classify_temporal_intent, agentic.AgenticRagService.query = intent, core_query
        selected = sys.argv[2:] or ["A", "B"]
        for case in selected:
            question = QUESTIONS[case]
            identity = ConversationIdentity(
                user_id="explicit-temporal-development", agent_id=AGENT_ID, thread_id=str(uuid4())
            )
            active = dict(
                case=case,
                question=question,
                thread_id=identity.thread_id,
                pending_before=None,
                detected_sector=question_sector(routing_question(question)),
                router_inputs=[],
                temporal_intents=[],
            )
            state = await runtime.graph.ainvoke(
                {"messages": [("human", question)], "conversation_identity": identity},
                {"configurable": {"thread_id": identity.storage_key()}},
            )
            audit, result = state["turn_audit"], state.get("normative_result")
            memory = state.get("conversation_memory")
            active.update(
                conversation_action=audit.conversation_action,
                scope_decision=audit.scope_gate_decision,
                scope_calls=audit.scope_gate_provider_calls,
                correlation_id=audit.correlation_id,
                pending_after=memory.pending_clarification.model_dump(mode="json")
                if memory and memory.pending_clarification
                else None,
                final_message=project_integrated_state(state).model_dump(mode="json"),
                final_result=result.model_dump(mode="json") if result else None,
                internal_audit=result.internal_audit.model_dump(mode="json")
                if result and result.internal_audit
                else None,
            )
            output["cases"].append(active)
            save()
            print(
                json.dumps(
                    dict(
                        case=case,
                        detected_sector=active["detected_sector"],
                        scope=active["scope_decision"],
                        router=active.get("router_validated_decision"),
                        status=result.status if result else None,
                        core_status=result.core_status if result else None,
                    )
                ),
                flush=True,
            )
        output["index_after"] = {
            k: v
            for k, v in snapshot_collection(runtime.index.store.collection).items()
            if k in {"count", "sha256"}
        }
        assert output["index_before"] == output["index_after"]
        save()


if __name__ == "__main__":
    asyncio.run(main())
