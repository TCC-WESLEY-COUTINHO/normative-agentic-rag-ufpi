"""Frozen engineering probes: file checkpoints, typed transport, controlled providers."""

import asyncio
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("OPENAI_API_KEY", "sk-fake-openai-key")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb
import httpx
import pytest
import service.service as service_module
import test_conversation_memory_followups as tests
import test_retrieval_strategies as retrieval
from chromadb.config import Settings
from client import AgentClient
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from rag_baseline import conversation_graph as c
from rag_baseline.agent_graph import build_integrated_graph
from rag_baseline.tool_facade import NormativeRagFacade
from rag_baseline.versioning import NormativeRegistry
from schema import ChatMessage
from service import app
from service.normative_transport import project_integrated_state

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
AGENT = "chatbot_ufpi_integrated_v1"
FORBIDDEN = {
    "conversation_memory",
    "last_normative_result_persistence",
    "compatibility_stamp",
    "storage_key",
    "internal_audit",
    "output_audit",
    "checkpoint_id",
    "checkpoint_ns",
    "raw_answer",
    "regenerated_answer",
    "guard_violations",
}


def write(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def keys(value):
    if isinstance(value, dict):
        return set(value) | set().union(*(keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(keys(v) for v in value))
    return set()


async def run():
    protocol = json.loads((OUT / "technical_protocol.json").read_text(encoding="utf-8"))
    for path, expected in protocol["hashes"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    metrics = defaultdict(lambda: [0, 0])
    rows = []
    with (OUT / "probe_rows.jsonl").open("xb") as journal:

        def measure(name, success):
            metrics[name][0] += int(success)
            metrics[name][1] += 1
            assert success, name

        def save(name, state, **details):
            payload = project_integrated_state(state).model_dump(mode="json")
            leaked = bool(keys(payload) & FORBIDDEN)
            measure("Public Memory Field Exclusion", not leaked)
            row = dict(
                id=name,
                action=state["turn_audit"].conversation_action,
                memory_status=state["turn_audit"].memory_status,
                facade_calls=state["turn_audit"].facade_calls,
                payload=payload,
                **details,
            )
            rows.append(row)
            journal.write((json.dumps(row, ensure_ascii=False) + "\n").encode())
            journal.flush()

        def transform_metrics(state, original, before, facade):
            derived = state["grounded_followup_result"]
            measure("Grounded Transform Retrieval Avoidance", len(facade.calls) == before)
            measure(
                "Grounded Transform Source Preservation",
                derived.source_correlation_id == original.correlation_id
                and derived.references == original.references
                and derived.temporal_provenance == original.temporal_provenance,
            )

        # Actual protected index is read once, never re-embedded or modified.
        client = chromadb.PersistentClient(
            path=str(ROOT / "code/.local/chroma"), settings=Settings(anonymized_telemetry=False)
        )
        store = type(
            "IndexHandle", (), {"collection": client.get_collection("ufpi_duas_regulacoes_setor")}
        )()
        current = c.build_memory_stamp(store)
        who = c.ConversationIdentity(user_id="A", agent_id=AGENT, thread_id="X")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            temp = Path(temporary)
            facade = tests.Facade()
            provider = tests.Provider()

            def build(saver, selected=facade, stamp=current):
                return build_integrated_graph(
                    selected,
                    checkpointer=saver,
                    memory_stamp=stamp,
                    transformer=c.GroundedFollowUpTransformer(provider),
                )

            async with AsyncSqliteSaver.from_conn_string(str(temp / "repeat.sqlite")) as saver:
                initial = await tests.turn(build(saver), who, "Qual o prazo na graduação?")
                original = tests.source(initial)
            async with AsyncSqliteSaver.from_conn_string(str(temp / "repeat.sqlite")) as saver:
                graph = build(saver)
                restored = await tests.turn(graph, who, "Repita")
                measure("Memory Restore Rate", tests.source(restored) == original)
                transform_metrics(restored, original, 1, facade)
                save("01_reopen_repeat", restored)
                for name, request in [
                    ("02_rephrase", "Explique mais simples"),
                    ("03_summary", "Resuma"),
                ]:
                    before = len(facade.calls)
                    state = await tests.turn(graph, who, request)
                    transform_metrics(state, original, before, facade)
                    save(name, state)
                for dimension, value, name, metric in [
                    ("user_id", "B", "11_other_user", "Cross-User Isolation Rate"),
                    ("agent_id", "other-agent", "12_other_agent", "Cross-Agent Isolation Rate"),
                ]:
                    other = c.ConversationIdentity(**{**who.model_dump(), dimension: value})
                    state = await tests.turn(graph, other, "Repita")
                    isolated = (
                        state["conversation_memory"] is None
                        and state["grounded_followup_result"] is None
                    )
                    measure(metric, isolated)
                    measure("Memory Leakage Absence", isolated)
                    save(name, state)

            # Pending operation is restored after actual file close/reopen.
            facade = tests.Facade()
            facade.status = "CLARIFICATION"
            async with AsyncSqliteSaver.from_conn_string(str(temp / "pending.sqlite")) as saver:
                first = await tests.turn(
                    build(saver, facade), who, "Posso cancelar uma disciplina?"
                )
                pending = first["conversation_memory"].pending_clarification
            async with AsyncSqliteSaver.from_conn_string(str(temp / "pending.sqlite")) as saver:
                graph = build(saver, facade)
                social = await tests.turn(graph, who, "Obrigado")
                measure(
                    "Memory Restore Rate",
                    social["conversation_memory"].pending_clarification == pending,
                )
                save("07_social_pending", social)
                facade.status = "ANSWER"
                continued = await tests.turn(graph, who, "graduação")
                measure(
                    "Clarification Continuity Rate",
                    facade.calls[-1]["question"] == pending.original_question
                    and facade.calls[-1]["clarification"] == "graduação",
                )
                measure(
                    "Clarification Correlation Preservation",
                    continued["normative_result"].correlation_id == pending.correlation_id,
                )
                save("05_continue_pending", continued)
                facade.status = "CLARIFICATION"
                await tests.turn(graph, who, "Outra pergunta ambígua")
                facade.status = "ANSWER"
                other = c.ConversationIdentity(**{**who.model_dump(), "thread_id": "Y"})
                state = await tests.turn(graph, other, "pós-graduação")
                isolated = (
                    facade.calls[-1]["question"] == "pós-graduação"
                    and facade.calls[-1]["clarification"] is None
                )
                measure("Cross-Thread Isolation Rate", isolated)
                measure("Memory Leakage Absence", isolated)
                save("06_other_thread_reply", state)
                cancelled = await tests.turn(graph, who, "Cancelar")
                assert cancelled["conversation_memory"].pending_clarification is None
                assert tests.source(cancelled) == tests.source(continued)
                save("08_cancel_pending", cancelled)

                changed = current.model_copy(update={"registry_fingerprint": "c" * 64})
                stale_graph = build(saver, facade, changed)
                stale = await tests.turn(stale_graph, who, "Explique melhor")
                measure(
                    "Stale Memory Rejection Rate",
                    stale["turn_audit"].memory_status == "STALE"
                    and stale["grounded_followup_result"] is None
                    and stale["normative_result"] is None,
                )
                save("09_stale_transform", stale)
                fresh = await tests.turn(stale_graph, who, "Nova pergunta completa na graduação")
                assert fresh["conversation_memory"].compatibility_stamp == changed
                assert fresh["turn_audit"].replaced_incompatible_memory
                save("10_stale_fresh_query", fresh)

            for name, core_status, text in [
                ("13_core_fallback", "fallback", "Resumo sem expansão."),
                ("14_new_date", "accepted", "O prazo passou a valer em 20 de maio de 2099."),
            ]:
                facade = tests.Facade()
                facade.core_status = core_status
                provider = tests.Provider(text)
                async with AsyncSqliteSaver.from_conn_string(str(temp / f"{name}.sqlite")) as saver:
                    graph = build(saver, facade)
                    first = await tests.turn(graph, who, "Pergunta completa")
                    original = tests.source(first)
                    state = await tests.turn(graph, who, "Explique melhor")
                    transform_metrics(state, original, 1, facade)
                    assert state["grounded_followup_result"].content == original.answer
                    assert state["grounded_followup_result"].guard_status == "FALLBACK_TO_SOURCE"
                    if core_status == "fallback":
                        assert not provider.calls
                    else:
                        measure(
                            "Transform Expansion Block Rate",
                            bool(state["turn_audit"].transform_violations),
                        )
                    save(name, state)

            # Three controlled concurrency cases: distinct users, threads, and pending/fresh.
            facade = tests.Facade()
            async with AsyncSqliteSaver.from_conn_string(str(temp / "concurrent.sqlite")) as saver:
                graph = build(saver, facade)
                for suffix, dimension in [("users", "user_id"), ("threads", "thread_id")]:
                    left = c.ConversationIdentity(
                        **{**who.model_dump(), "thread_id": "concurrent-" + suffix}
                    )
                    right = c.ConversationIdentity(**{**left.model_dump(), dimension: "B-or-Y"})
                    pair = await asyncio.gather(
                        tests.turn(graph, left, "Pergunta A"),
                        tests.turn(graph, right, "Pergunta B"),
                    )
                    measure(
                        "Memory Leakage Absence",
                        pair[0]["normative_result"].correlation_id
                        != pair[1]["normative_result"].correlation_id
                        and pair[0]["conversation_memory"].conversation_identity == left
                        and pair[1]["conversation_memory"].conversation_identity == right,
                    )
                    for i, state in enumerate(pair):
                        save("15_concurrent_" + suffix + str(i), state)
                facade.status = "CLARIFICATION"
                pending_state = await tests.turn(graph, who, "Pergunta pendente A")
                facade.status = "ANSWER"
                other = c.ConversationIdentity(**{**who.model_dump(), "user_id": "B"})
                a, b = await asyncio.gather(
                    tests.turn(graph, who, "graduação"),
                    tests.turn(graph, other, "Pergunta fresca B"),
                )
                measure(
                    "Memory Leakage Absence",
                    a["normative_result"].correlation_id
                    == pending_state["normative_result"].correlation_id
                    and b["conversation_memory"].last_normative_question == "Pergunta fresca B",
                )
                save("16_pending_concurrent_A", a)
                save("16_pending_concurrent_B", b)

            # Router, retrieval, temporal filter, grounding and V2 are actual; provider is fake.
            service, router, version_filter, core_provider, _ = retrieval.runtime.__wrapped__(
                temp / "core", NormativeRegistry.load()
            )
            core = NormativeRagFacade(service, router, version_filter=version_filter)
            question = "Posso cancelar uma disciplina na graduação?"
            canonical = c.ContextualNormativeQueryResolver().resolve(
                "E na pós?", question, "graduacao"
            )
            core_provider.scopes.update({question: "graduacao", canonical: "pos_graduacao"})
            async with AsyncSqliteSaver.from_conn_string(str(temp / "core.sqlite")) as saver:
                graph = build(saver, core)
                first = await tests.turn(graph, who, question)
                shifted = await tests.turn(graph, who, "E na pós?")
                measure(
                    "Contextual RAG Re-entry Rate",
                    len(core_provider.routes) == 2
                    and shifted["normative_result"].domain == "pos_graduacao"
                    and shifted["normative_result"].correlation_id
                    != first["normative_result"].correlation_id,
                )
                assert all(
                    r.norm_id != "ufpi-177-2012" for r in shifted["normative_result"].references
                )
                save("04_domain_shift_core", shifted, canonical_question=canonical)

            # Actual HTTP/SSE + AgentClient, no lifespan and no public registry modification.
            facade = tests.Facade()
            provider = tests.Provider()
            async with AsyncSqliteSaver.from_conn_string(str(temp / "http.sqlite")) as saver:
                graph = build(saver, facade)
                with pytest.MonkeyPatch.context() as patch:
                    patch.setattr(service_module, "get_agent", lambda _: graph)
                    patch.setattr(service_module.settings, "AUTH_SECRET", None)
                    patch.setattr(service_module.settings, "LANGFUSE_TRACING", False)
                    real_client = httpx.AsyncClient
                    patch.setattr(
                        httpx,
                        "AsyncClient",
                        lambda **kw: real_client(transport=httpx.ASGITransport(app=app), **kw),
                    )
                    agent = AgentClient("http://test", get_info=False)
                    agent.update_agent(AGENT, verify=False)
                    answer = await agent.ainvoke("Pergunta completa", user_id="A", thread_id="HTTP")
                    for name, mode, request in [
                        ("17_http_summary", "invoke", "Resuma"),
                        ("18_http_repeat", "stream", "Repita"),
                    ]:
                        if mode == "invoke":
                            value = await agent.ainvoke(request, user_id="A", thread_id="HTTP")
                        else:
                            values = [
                                m
                                async for m in agent.astream(
                                    request, user_id="A", thread_id="HTTP", stream_tokens=True
                                )
                            ]
                            assert len(values) == 1
                            value = values[0]
                        derived = value.grounded_followup_result
                        measure(
                            "Typed Follow-up Transport Preservation",
                            isinstance(derived, c.GroundedFollowUpResult)
                            and derived.source_correlation_id
                            == answer.normative_result.correlation_id
                            and derived.references == answer.normative_result.references
                            and derived.temporal_provenance
                            == answer.normative_result.temporal_provenance,
                        )
                        measure(
                            "Public Memory Field Exclusion",
                            not bool(keys(value.model_dump(mode="json")) & FORBIDDEN),
                        )
                        row = {
                            "id": name,
                            "payload": value.model_dump(mode="json"),
                            "transport": mode,
                        }
                        rows.append(row)
                        journal.write((json.dumps(row, ensure_ascii=False) + "\n").encode())
                        journal.flush()
                        assert isinstance(
                            ChatMessage.model_validate_json(value.model_dump_json()), ChatMessage
                        )
        for path, expected in protocol["hashes"].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
        write(
            OUT / "local_probes.json",
            dict(
                rows=rows,
                metrics=dict(metrics),
                compatibility_stamp=current.model_dump(),
                external_http_calls=0,
                limitations="Controlled engineering results; no legal or linguistic quality evaluation.",
            ),
        )
        print(json.dumps(dict(metrics=metrics, rows=len(rows)), ensure_ascii=False))


if __name__ == "__main__":

    def blocked(*_args, **_kwargs):
        raise AssertionError("External HTTP is blocked in this harness.")

    # ASGITransport bypasses these network transports; no remote API is permitted.
    httpx.HTTPTransport.handle_request = blocked
    httpx.AsyncHTTPTransport.handle_async_request = blocked
    asyncio.run(run())
