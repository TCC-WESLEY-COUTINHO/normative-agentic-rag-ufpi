"""Frozen finite probes: actual SQLite, controlled core, HTTP/SSE, external IO blocked."""

import asyncio
import hashlib
import json
import os
import socket
import tempfile
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["OPENAI_API_KEY"] = "sk-fake-openai-key"

import httpx
import pytest
import service.service as service_module
import test_conversation_memory_followups as memory
import test_retrieval_strategies as retrieval
from client import AgentClient
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from rag_baseline import conversation_graph as c
from rag_baseline.calculator_contracts import CalculatorToolResult
from rag_baseline.tool_facade import NormativeRagFacade
from schema import ChatMessage
from service import app
from service.normative_transport import project_integrated_state

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
AGENT = "chatbot_ufpi_integrated_v1"
PRIVATE = {
    "conversation_memory",
    "storage_key",
    "compatibility_stamp",
    "internal_audit",
    "last_normative_result_persistence",
    "calculator_request",
    "turn_audit",
}


def write(name, value):
    (OUT / name).write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def keys(value):
    if isinstance(value, dict):
        return set(value) | set().union(*(keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(keys(v) for v in value))
    return set()


def check_hashes(protocol):
    for path, expected in protocol["hashes"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path


async def run():
    protocol = json.loads((OUT / "technical_protocol.json").read_text(encoding="utf-8"))
    check_hashes(protocol)
    dataset = json.loads(
        (ROOT / "evaluation/datasets/tool_routing_calculator_v1.json").read_text(encoding="utf-8")
    )
    metrics, rows, external = defaultdict(lambda: [0, 0]), [], []
    monkey = pytest.MonkeyPatch()
    original_send = httpx.AsyncClient.send

    def forbidden(*args, **kwargs):
        external.append("blocked_external_attempt")
        raise AssertionError("External IO forbidden in frozen probes")

    monkey.setattr(socket.socket, "connect", forbidden)
    monkey.setattr(httpx.Client, "send", forbidden)
    monkey.setattr(httpx.AsyncClient, "send", forbidden)

    def measure(name, success):
        metrics[name][0] += int(success)
        metrics[name][1] += 1
        assert success, name

    with (OUT / "probe_rows.jsonl").open("xb") as journal:

        def save(name, state=None, payload=None, **details):
            payload = payload or project_integrated_state(state).model_dump(mode="json")
            measure("Private Field Exclusion", not keys(payload) & PRIVATE)
            if payload.get("calculator_result"):
                measure("Calculator External Call Avoidance", not external)
            row = dict(id=name, payload=payload, **details)
            if state is not None:
                row["audit"] = asdict(state["turn_audit"])
            rows.append(row)
            journal.write((json.dumps(row, ensure_ascii=False) + "\n").encode())
            journal.flush()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_name:
            temp = Path(temp_name)
            facade = memory.Facade()
            who = c.ConversationIdentity(user_id="A", agent_id=AGENT, thread_id="X")
            async with AsyncSqliteSaver.from_conn_string(str(temp / "cases.sqlite")) as saver:
                graph = memory.build(c, saver, facade)
                for case in dataset["cases"]:
                    identity = who.model_copy(update={"thread_id": case["id"]})
                    before = len(facade.calls)
                    state = await memory.turn(graph, identity, case["message"])
                    audit, result = state["turn_audit"], state.get("calculator_result")
                    measure(
                        "Tool Routing Accuracy",
                        audit.conversation_action == case["expected_action"],
                    )
                    measure(
                        "Tool Call Count Agreement",
                        audit.calculator_calls == case["expected_calculator_calls"]
                        and len(facade.calls) - before == case["expected_facade_calls"],
                    )
                    actual = result or state.get("normative_result")
                    if case["expected_status"] is not None:
                        assert actual.status == case["expected_status"]
                    if result:
                        assert result.operation_kind == case["expected_operation_kind"]
                        if case["expected_error_code"]:
                            assert result.error_code == case["expected_error_code"]
                    if case["purpose"] == "supported_math":
                        measure(
                            "Calculator Execution Accuracy",
                            result is not None and result.content == case["expected_content"],
                        )
                        measure("Calculator-to-Normative Route Avoidance", audit.facade_calls == 0)
                    if case["purpose"] == "normative_boundary":
                        measure(
                            "Normative-to-Calculator Route Avoidance",
                            result is None and audit.calculator_calls == 0,
                        )
                    if case["purpose"] == "unsafe_or_invalid":
                        measure("Unsafe Expression Rejection Rate", result.status == "ERROR")
                    if case["purpose"] == "ambiguous_date":
                        measure(
                            "Ambiguous Date Rule Rejection Rate",
                            result.error_code == "ambiguous_date_offset",
                        )
                    save(case["id"], state, message=case["message"])

            # Persist ANSWER and pending, close/reopen, interpose both success and error.
            facade = memory.Facade()
            async with AsyncSqliteSaver.from_conn_string(str(temp / "pending.sqlite")) as saver:
                graph = memory.build(c, saver, facade)
                await memory.turn(graph, who, "Pergunta original")
                facade.status = "CLARIFICATION"
                initial = await memory.turn(graph, who, "Posso cancelar uma disciplina?")
                original_memory = initial["conversation_memory"]
            async with AsyncSqliteSaver.from_conn_string(str(temp / "pending.sqlite")) as saver:
                graph = memory.build(c, saver, facade)
                for text in ["2+2", "1/0"]:
                    state = await memory.turn(graph, who, text)
                    measure(
                        "Calculator Memory Preservation Rate",
                        state["conversation_memory"] == original_memory,
                    )
                    measure(
                        "Pending Preservation Rate",
                        state["conversation_memory"].pending_clarification
                        == original_memory.pending_clarification,
                    )
                    save("pending_" + state["calculator_result"].status, state)
                facade.status = "ANSWER"
                continued = await memory.turn(graph, who, "graduação")
                measure(
                    "Clarification Correlation Continuity",
                    continued["normative_result"].correlation_id
                    == original_memory.pending_clarification.correlation_id
                    and facade.calls[-1]["question"]
                    == original_memory.pending_clarification.original_question
                    and facade.calls[-1]["clarification"] == "graduação",
                )
                save("pending_continued", continued)

            facade = memory.Facade()
            async with AsyncSqliteSaver.from_conn_string(str(temp / "follow.sqlite")) as saver:
                graph = memory.build(c, saver, facade, memory.Provider())
                initial = await memory.turn(graph, who, "Qual o prazo na graduação?")
                original = memory.source(initial)
                for text in ["2+2", "1/0"]:
                    state = await memory.turn(graph, who, text)
                    measure(
                        "Calculator Memory Preservation Rate",
                        state["conversation_memory"] == initial["conversation_memory"],
                    )
                    save("after_answer_" + state["calculator_result"].status, state)
                final = await memory.turn(graph, who, "Explique mais simples")
                derived = final["grounded_followup_result"]
                measure(
                    "Grounded Follow-up Source Preservation",
                    len(facade.calls) == 1
                    and derived.source_correlation_id == original.correlation_id
                    and derived.references == original.references
                    and derived.temporal_provenance == original.temporal_provenance,
                )
                save("grounded_after_calculator", final)

            # Controlled real Router/core, metadata_exact normative path beside two calculator operations.
            runtime = retrieval.runtime.__wrapped__(temp, retrieval.registry.__wrapped__())
            service, router, version_filter, provider, _ = runtime
            question = "Resolução 177/2012, art. 68"
            provider.scopes[question] = "graduacao"
            actual_facade = NormativeRagFacade(service, router, version_filter=version_filter)
            async with AsyncSqliteSaver.from_conn_string(str(temp / "concurrent.sqlite")) as saver:
                graph = memory.build(c, saver, actual_facade)
                states = await asyncio.gather(
                    *[
                        memory.turn(graph, who.model_copy(update={"user_id": user}), text)
                        for user, text in [
                            ("A", "2+2"),
                            ("B", question),
                            ("C", "Adicione 10 dias corridos a 05/11/2026"),
                        ]
                    ]
                )
                measure(
                    "Concurrent Result Isolation",
                    states[0]["calculator_result"].content == "4"
                    and states[1]["normative_result"].retrieval_strategy == "metadata_exact"
                    and states[2]["calculator_result"].content == "15/11/2026"
                    and states[0]["conversation_memory"] is states[2]["conversation_memory"] is None
                    and len(provider.routes) == 1
                    and not provider.embeddings,
                )
                for label, state in zip(["A", "B", "C"], states, strict=True):
                    save("concurrent_" + label, state)

            # ASGI in-process HTTP/SSE transport. No server/lifespan or external HTTP.
            real_client = httpx.AsyncClient
            transport = httpx.ASGITransport(app=app)

            async def local_send(client, request, *args, **kwargs):
                if request.url.host != "test" or client._transport is not transport:
                    return forbidden(client, request)
                return await original_send(client, request, *args, **kwargs)

            # Original unpatched method is restored only for this exact local transport.
            monkey.setattr(httpx.AsyncClient, "send", local_send)
            monkey.setattr(
                httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs)
            )
            monkey.setattr(service_module.settings, "AUTH_SECRET", None)
            monkey.setattr(service_module.settings, "LANGFUSE_TRACING", False)
            async with AsyncSqliteSaver.from_conn_string(str(temp / "http.sqlite")) as saver:
                facade = memory.Facade()
                graph = memory.build(c, saver, facade)
                monkey.setattr(service_module, "get_agent", lambda agent_id: graph)
                client = AgentClient(get_info=False, base_url="http://test")
                client.update_agent(AGENT, verify=False)
                invoked = await client.ainvoke("2+2", user_id="A", thread_id="invoke")
                streamed = [
                    m
                    async for m in client.astream(
                        "2+2", user_id="A", thread_id="stream", stream_tokens=True
                    )
                ]
                assert len(streamed) == 1
                for label, message in [("invoke", invoked), ("stream", streamed[0])]:
                    measure(
                        "Typed Calculator Transport Preservation",
                        isinstance(message.calculator_result, CalculatorToolResult)
                        and message.content == "4"
                        and message.normative_result is message.grounded_followup_result is None,
                    )
                    save("transport_" + label, payload=message.model_dump(mode="json"))
                measure(
                    "Invoke/Stream Calculator Agreement",
                    invoked.calculator_result == streamed[0].calculator_result,
                )
                async with httpx.AsyncClient() as web:
                    response = await web.post(
                        f"http://test/{AGENT}/stream",
                        json={
                            "message": "2+2",
                            "user_id": "A",
                            "thread_id": "raw",
                            "stream_tokens": True,
                        },
                    )
                data = [line for line in response.text.splitlines() if line.startswith("data:")]
                measure(
                    "SSE Complete Message and DONE",
                    len(data) == 2
                    and data[-1] == "data: [DONE]"
                    and json.loads(data[0][6:])["type"] == "message"
                    and not facade.calls,
                )
                raw = ChatMessage.model_validate(json.loads(data[0][6:])["content"])
                save("transport_raw_sse", payload=raw.model_dump(mode="json"))
            assert not external
            monkey.undo()
    check_hashes(protocol)
    write(
        "local_probes.json",
        dict(
            protocol_hash=hashlib.sha256(
                (OUT / "technical_protocol.json").read_bytes()
            ).hexdigest(),
            rows=len(rows),
            metrics=dict(metrics),
            external_call_attempts=len(external),
            all_hashes_unchanged=True,
        ),
    )
    print(
        json.dumps(
            dict(rows=len(rows), metrics=dict(metrics), external_call_attempts=len(external)),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(run())
