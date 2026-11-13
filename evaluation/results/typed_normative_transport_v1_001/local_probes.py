"""Frozen offline ASGI transport probes. No server, persistence or external HTTP."""

import asyncio
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx
import pytest
import test_typed_normative_transport as fixtures
from langgraph.graph import END, START, StateGraph
from rag_baseline.agent_graph import IntegratedAgentState
from rag_baseline.tool_contracts import NormativeToolResult
from rag_baseline.tool_facade import NormativeRagFacade
from schema import ChatMessage

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent


def save(name, value):
    (OUT / name).write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


async def main():
    protocol = json.loads((OUT / "technical_protocol.json").read_text("utf-8"))
    for file, digest in protocol["frozen_hashes"].items():
        assert hashlib.sha256((ROOT / file).read_bytes()).hexdigest() == digest, file
    rows, pairs = [], []
    with (
        TemporaryDirectory(prefix="typed-transport-", ignore_cleanup_errors=True) as temp,
        pytest.MonkeyPatch.context() as mp,
    ):
        runtime = fixtures.runtime.__wrapped__(Path(temp), fixtures.registry.__wrapped__())
        service, router, vf, provider, _ = runtime
        h = fixtures.harness.__wrapped__(mp)
        h.facade.delegate = NormativeRagFacade(service, router, vf)
        state = {"mode": "normal", "generation_count": 0}
        raw = "Art. 999 da Resolução 177/2012. RAW_UNSUPPORTED_DRAFT."

        async def chat(**payload):
            provider.prompts.append(payload)
            state["generation_count"] += 1
            await asyncio.sleep(0)
            if state["mode"] == "fallback" or (
                state["mode"] == "regenerated" and state["generation_count"] == 1
            ):
                return raw
            return "Conteúdo controlado para verificar transporte."

        provider.chat = chat

        def record(case_id, mode, message, payload, original, events):
            normative = original is not None
            assert isinstance(message, ChatMessage)
            preserved = (
                normative
                and isinstance(message.normative_result, NormativeToolResult)
                and message.normative_result.model_dump() == original.model_dump()
            )
            expected_content = fixtures.content(original) if normative else "Olá!"
            forbidden = sorted(fixtures.keys(payload) & fixtures.PRIVATE_KEYS)
            raw_exposed = any(
                marker in json.dumps(payload, ensure_ascii=False)
                for marker in protocol["private_sentinels"]
            )
            item = dict(
                id=case_id,
                mode=mode,
                normative=normative,
                public_payload=payload,
                typed_preserved=preserved if normative else message.normative_result is None,
                content_preserved=message.content == expected_content,
                references_preserved=message.normative_result.references == original.references
                if normative
                else None,
                provenance_preserved=message.normative_result.temporal_provenance
                == original.temporal_provenance
                if normative
                else None,
                correlation_preserved=message.normative_result.correlation_id
                == original.correlation_id
                if normative
                else None,
                forbidden_keys=forbidden,
                raw_exposed=raw_exposed,
                events=events,
                source_public=original.model_dump(mode="json") if normative else None,
            )
            rows.append(item)
            with (OUT / "probe_rows.jsonl").open("a", encoding="utf-8", newline="\n") as journal:
                journal.write(json.dumps(item, ensure_ascii=False) + "\n")
            assert item["typed_preserved"] and item["content_preserved"]
            assert not forbidden and not raw_exposed
            return item

        async def execute(case):
            case_id, mode, question, scope, core_mode = case
            provider.scopes[question] = scope
            state.update(mode=core_mode, generation_count=0)
            before = len(h.facade.results)
            if mode == "invoke":
                message = await h.client.ainvoke(question)
                payload, events = message.model_dump(mode="json"), ["http_final"]
            else:
                # Read actual HTTP/SSE bytes, then the AgentClient parser.
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"http://test/{fixtures.AGENT}/stream",
                        json={"message": question, "stream_tokens": True},
                    )
                response.raise_for_status()
                lines = [line for line in response.text.splitlines() if line]
                envelopes = [
                    json.loads(line[6:])
                    for line in lines
                    if line.startswith("data: ") and line != "data: [DONE]"
                ]
                assert len(envelopes) == 1 and envelopes[0]["type"] == "message"
                assert lines[-1] == "data: [DONE]"
                message = h.client._parse_stream_line("data: " + json.dumps(envelopes[0]))
                payload, events = envelopes[0]["content"], [e["type"] for e in envelopes] + ["DONE"]
                assert "RAW_UNSUPPORTED_DRAFT" not in response.text
            original = h.facade.results[-1] if len(h.facade.results) > before else None
            return record(case_id, mode, message, payload, original, events)

        for case in protocol["cases"]:
            await execute(case)

        state.update(mode="normal", generation_count=0)
        exact = "Art. 68 da 177/2012"
        filtered = "Na 956/2025, quais as regras de matrícula?"
        provider.scopes.update({exact: "graduacao", filtered: "pos_graduacao"})

        async def streamed():
            return [m async for m in h.client.astream(filtered)]

        a, streamed_messages = await asyncio.gather(h.client.ainvoke(exact), streamed())
        assert len(streamed_messages) == 1
        b = streamed_messages[0]
        assert a.normative_result.correlation_id != b.normative_result.correlation_id
        assert a.normative_result.retrieval_strategy == "metadata_exact"
        assert b.normative_result.retrieval_strategy == "vector_filtered"
        originals = {r.correlation_id: r for r in h.facade.results}
        for case_id, mode, message in [
            ("concurrent_exact", "invoke", a),
            ("concurrent_filtered", "stream", b),
        ]:
            record(
                case_id,
                mode,
                message,
                message.model_dump(mode="json"),
                originals[message.normative_result.correlation_id],
                ["http_final"] if mode == "invoke" else ["message", "DONE"],
            )

        # Same completed execution, replayed solely across the two transport paths.
        # Production does not cache/replay results or reuse operation correlations.
        for status in ["ANSWER", "CLARIFICATION", "ERROR"]:
            h.facade.delegate = None
            h.facade.status = status
            source = await h.graph.ainvoke({"messages": [("human", "Controlled agreement source")]})
            replay = StateGraph(IntegratedAgentState)
            replay.add_node("completed_execution", lambda incoming, source=source: source)
            replay.add_edge(START, "completed_execution")
            replay.add_edge("completed_execution", END)
            graph = replay.compile(name=fixtures.AGENT)
            mp.setattr(fixtures.service_module, "get_agent", lambda agent_id, graph=graph: graph)
            first = await h.client.ainvoke("replay")
            second_messages = [m async for m in h.client.astream("replay")]
            assert len(second_messages) == 1
            second = second_messages[0]
            identical = (
                first.normative_result.model_dump() == second.normative_result.model_dump()
                and first.content == second.content
            )
            assert identical
            pairs.append(
                dict(
                    status=status,
                    agreement=identical,
                    correlation_id=str(first.normative_result.correlation_id),
                    semantics=first.normative_result.model_dump(mode="json"),
                )
            )
            for mode, message in [("invoke", first), ("stream", second)]:
                record(
                    f"agreement_{status}_{mode}",
                    mode,
                    message,
                    message.model_dump(mode="json"),
                    source["normative_result"],
                    ["http_final"] if mode == "invoke" else ["message", "DONE"],
                )

        legacy_payloads = [
            {"type": kind, "content": "legacy"} for kind in ["human", "ai", "tool", "custom"]
        ]
        legacy = []
        for payload in legacy_payloads:
            message = h.client._parse_stream_line(
                "data: " + json.dumps(dict(type="message", content=payload))
            )
            legacy.append(
                isinstance(message, ChatMessage)
                and message.content == "legacy"
                and message.normative_result is None
            )
        legacy.append(
            h.client._parse_stream_line('data: {"type":"token","content":"legacy-token"}')
            == "legacy-token"
        )
        h.web.close()

    normative = [r for r in rows if r["normative"]]
    answers = [r for r in normative if r["source_public"]["status"] == "ANSWER"]
    metrics = dict(
        typed_transport=[sum(r["typed_preserved"] for r in normative), len(normative)],
        authoritative_content=[sum(r["content_preserved"] for r in normative), len(normative)],
        official_references=[sum(r["references_preserved"] for r in answers), len(answers)],
        temporal_provenance=[sum(r["provenance_preserved"] for r in answers), len(answers)],
        correlation=[sum(r["correlation_preserved"] for r in normative), len(normative)],
        private_field_leakage=[sum(bool(r["forbidden_keys"]) for r in rows), len(rows)],
        normative_raw_exposure=[sum(r["raw_exposed"] for r in normative), len(normative)],
        legacy_compatibility=[sum(legacy), len(legacy)],
        invoke_stream_agreement=[sum(p["agreement"] for p in pairs), len(pairs)],
        default_drift=[int(fixtures.DEFAULT_AGENT != "chatbot_ufpi_v2"), 1],
    )
    for file, digest in protocol["frozen_hashes"].items():
        assert hashlib.sha256((ROOT / file).read_bytes()).hexdigest() == digest, file
    save(
        "local_probes.json",
        dict(
            primary_groups=11,
            primary_executions=12,
            agreement_requests=6,
            executions=len(rows),
            rows=rows,
            agreement_pairs=pairs,
            legacy_cases=legacy,
            metrics=metrics,
            real_api_calls=0,
            fixture_index="Temporary local Chroma, 10 corpus chunks, controlled 2D vectors; no relevance claim.",
        ),
    )
    print(json.dumps(metrics, ensure_ascii=False))


if __name__ == "__main__":
    with (
        patch(
            "httpx.HTTPTransport.handle_request",
            side_effect=AssertionError("External HTTP forbidden"),
        ),
        patch(
            "httpx.AsyncHTTPTransport.handle_async_request",
            side_effect=AssertionError("External HTTP forbidden"),
        ),
    ):
        asyncio.run(main())
