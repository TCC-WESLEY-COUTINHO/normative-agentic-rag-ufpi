"""Frozen registered-runtime probes, real local core/SQLite and controlled providers."""

import asyncio
import hashlib
import json
import os
import shutil
import socket
import tempfile
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

os.environ["OPENAI_API_KEY"] = "sk-fake-openai-key"
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

import httpx
import pytest
import service.service as service_module
import test_integrated_runtime as tests
import test_retrieval_strategies as retrieval
import test_runtime_packaging as packaging
from agents.agents import DEFAULT_AGENT, agents, get_agent
from chromadb.api.shared_system_client import SharedSystemClient
from client import AgentClient
from core.settings import DatabaseType
from rag_baseline.conversation_contracts import ConversationIdentity

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
AGENT = "chatbot_ufpi_integrated_v1"
PRIVATE = {
    "conversation_memory",
    "last_normative_result_persistence",
    "compatibility_stamp",
    "storage_key",
    "internal_audit",
    "api_key",
    "OPENROUTER_API_KEY",
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
    audit = json.loads((OUT / "runtime_audit.json").read_text(encoding="utf-8"))
    packaging_audit = json.loads((OUT / "packaging_audit.json").read_text(encoding="utf-8"))
    metrics, external, rows = defaultdict(lambda: [0, 0]), [], []
    monkey = pytest.MonkeyPatch()
    real_client, real_send = httpx.AsyncClient, httpx.AsyncClient.send
    local_transport = httpx.ASGITransport(app=service_module.app)

    def forbidden(*args, **kwargs):
        external.append("blocked_external_attempt")
        raise AssertionError("External IO forbidden")

    async def send(client, request, *args, **kwargs):
        if request.url.host != "test" or client._transport is not local_transport:
            return forbidden(client, request)
        return await real_send(client, request, *args, **kwargs)

    monkey.setattr(socket.socket, "connect", forbidden)
    monkey.setattr(httpx.Client, "send", forbidden)
    monkey.setattr(httpx.AsyncClient, "send", send)
    monkey.setattr(
        httpx, "AsyncClient", lambda **kwargs: real_client(transport=local_transport, **kwargs)
    )
    monkey.setattr(service_module.settings, "DATABASE_TYPE", DatabaseType.SQLITE)
    monkey.setattr(service_module.settings, "AUTH_SECRET", None)
    monkey.setattr(service_module.settings, "LANGFUSE_TRACING", False)
    saver_factory = service_module.initialize_database
    savers, providers = [], []

    @asynccontextmanager
    async def observed_saver():
        async with saver_factory() as saver:
            savers.append(saver)
            yield saver

    monkey.setattr(service_module, "initialize_database", observed_saver)

    def provider_factory(settings):
        provider = tests.Provider()
        providers.append(provider)
        return provider

    def measure(name, success):
        metrics[name][0] += int(success)
        metrics[name][1] += 1
        assert success, name

    with (OUT / "probe_rows.jsonl").open("xb") as journal:

        def save(name, payload, **details):
            if hasattr(payload, "model_dump"):
                payload = payload.model_dump(mode="json")
            measure("Private Field Exclusion", not (keys(payload) & PRIVATE))
            row = dict(id=name, payload=payload, **details)
            journal.write((json.dumps(row, ensure_ascii=False) + "\n").encode())
            journal.flush()
            rows.append(row)

        def typed(message, kind):
            expected = {
                "normative": "normative_result",
                "grounded": "grounded_followup_result",
                "calculator": "calculator_result",
            }[kind]
            measure(
                "Runtime Typed Transport Preservation",
                getattr(message, expected) is not None
                and sum(
                    getattr(message, name) is not None
                    for name in (
                        "normative_result",
                        "grounded_followup_result",
                        "calculator_result",
                    )
                )
                == 1,
            )

        async def memory(user="A", thread="X"):
            who = ConversationIdentity(user_id=user, agent_id=AGENT, thread_id=thread)
            state = await agents[AGENT].graph.aget_state(
                {"configurable": {"thread_id": who.storage_key()}}
            )
            return state.values.get("conversation_memory")

        async def metadata(web, expected_ready, code=None, unique_legacy=False):
            info = (await web.get("/info")).json()
            measure(
                "Default Preservation", info["default_agent"] == DEFAULT_AGENT == "chatbot_ufpi_v2"
            )
            if unique_legacy:
                actual = {a["key"]: a["description"] for a in info["agents"]}
                for key, description in audit["legacy_agents"].items():
                    measure("Legacy Agent Registry Preservation", actual.get(key) == description)
            ready = (await web.get(f"/agents/{AGENT}/readiness")).json()
            measure(
                "Integrated Readiness Checks",
                ready["ready"] == expected_ready
                and ready["registered"]
                and (code is None or ready["reason_code"] == code),
            )
            return info, ready

        async def close_checks(built, provider):
            measure(
                "Resource Close Success",
                built.index.closed
                and built.index.key not in SharedSystemClient._identifier_to_system,
            )
            measure("Resource Close Success", provider.closed)

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_name:
            temp = Path(temp_name)
            core = retrieval.runtime.__wrapped__(temp, retrieval.registry.__wrapped__())
            directory = temp / "owned-runtime-index"
            shutil.copytree(core[0].vector_store.persist_dir, directory)
            current_settings = tests.options(core, temp, CHROMA_PERSIST_DIR=directory)
            monkey.setattr(service_module.settings, "SQLITE_DB_PATH", str(temp / "service.sqlite"))
            monkey.setattr(
                service_module.app.state,
                "agent_runtime_options",
                {AGENT: {"settings": current_settings, "provider_factory": provider_factory}},
                raising=False,
            )
            assert service_module.get_agent is get_agent
            client = AgentClient(base_url="http://test", get_info=False)
            client.update_agent(AGENT, verify=False)

            async with service_module.app.router.lifespan_context(service_module.app):
                built, provider = agents[AGENT].runtime, providers[-1]
                measure(
                    "Runtime Build Success",
                    built is not None and built.graph is get_agent(AGENT) and built.index.owned,
                )
                measure("Registered Agent Availability", get_agent(AGENT) is built.graph)
                measure(
                    "Startup External Call Avoidance",
                    not external
                    and not provider.routes
                    and not provider.prompts
                    and not provider.embeddings,
                )
                save("01_startup", built.readiness())
                async with httpx.AsyncClient(base_url="http://test") as web:
                    info, ready = await metadata(web, True, unique_legacy=True)
                    save("02_info", info)
                    health = (await web.get("/health")).json()
                    assert health["status"] == "ok" and health["integrated_agent"]["ready"]
                    save("03_health", health)
                direct = await client.ainvoke("Oi", user_id="A", thread_id="X")
                assert (
                    direct.normative_result
                    is direct.grounded_followup_result
                    is direct.calculator_result
                    is None
                )
                assert not provider.routes
                save("04_direct", direct)
                first = await client.ainvoke(
                    "Posso cancelar uma disciplina na graduação?", user_id="A", thread_id="X"
                )
                typed(first, "normative")
                before = await memory()
                save("05_normative", first)
                follow = await client.ainvoke("Explique mais simples", user_id="A", thread_id="X")
                typed(follow, "grounded")
                measure(
                    "Runtime Memory Continuity",
                    await memory() == before
                    and follow.grounded_followup_result.source_correlation_id
                    == first.normative_result.correlation_id,
                )
                save("06_grounded", follow)
                calculated = await client.ainvoke("2+2", user_id="A", thread_id="X")
                typed(calculated, "calculator")
                measure(
                    "Runtime Memory Continuity",
                    await memory() == before and calculated.content == "4",
                )
                save("07_calculator", calculated)
                shifted = await client.ainvoke("E na pós?", user_id="A", thread_id="X")
                typed(shifted, "normative")
                measure(
                    "Runtime Memory Continuity",
                    shifted.normative_result.domain == "pos_graduacao"
                    and shifted.normative_result.correlation_id
                    != first.normative_result.correlation_id,
                )
                save("08_domain_shift", shifted)
                streamed = [
                    m
                    async for m in client.astream(
                        "Resolução 177/2012, art. 68",
                        user_id="S",
                        thread_id="X",
                        stream_tokens=True,
                    )
                ]
                assert len(streamed) == 1
                typed(streamed[0], "normative")
                assert streamed[0].normative_result.retrieval_strategy == "metadata_exact"
                save("09_normative_stream", streamed[0])
                pending = await client.ainvoke(
                    "Posso cancelar uma disciplina?", user_id="A", thread_id="P"
                )
                typed(pending, "normative")
                assert pending.normative_result.status == "CLARIFICATION"
                save("10_clarification", pending)
                pending_memory = await memory(thread="P")
                error = await client.ainvoke("1/0", user_id="A", thread_id="P")
                typed(error, "calculator")
                measure(
                    "Runtime Memory Continuity",
                    await memory(thread="P") == pending_memory
                    and error.calculator_result.status == "ERROR",
                )
                save("11_pending_calculator", error)
                continued = await client.ainvoke("graduação", user_id="A", thread_id="P")
                typed(continued, "normative")
                measure(
                    "Runtime Memory Continuity",
                    continued.normative_result.status == "ANSWER"
                    and continued.normative_result.correlation_id
                    == pending.normative_result.correlation_id,
                )
                save("12_continued", continued)
                other = await client.ainvoke("Repita", user_id="B", thread_id="X")
                measure(
                    "Runtime Isolation",
                    other.grounded_followup_result is None and await memory(user="B") is None,
                )
                save("13_cross_user", other)
                concurrent = await asyncio.gather(
                    *[
                        client.ainvoke(text, user_id=user, thread_id="X")
                        for user, text in [
                            ("C", "Resolução 177/2012, art. 68"),
                            ("D", "2+2"),
                            ("E", "Adicione 10 dias corridos a 05/11/2026"),
                        ]
                    ]
                )
                measure(
                    "Runtime Isolation",
                    concurrent[0].normative_result.retrieval_strategy == "metadata_exact"
                    and concurrent[1].calculator_result.content == "4"
                    and concurrent[2].calculator_result.content == "15/11/2026"
                    and await memory(user="D") is None
                    and await memory(user="E") is None,
                )
                for label, message, kind in zip(
                    ["C", "D", "E"],
                    concurrent,
                    ["normative", "calculator", "calculator"],
                    strict=True,
                ):
                    typed(message, kind)
                    save("14_concurrent_" + label, message)
                final_memory = await memory()
            await close_checks(built, provider)
            save(
                "15_shutdown",
                {
                    "runtime_closed": built.closed,
                    "provider_closed": provider.closed,
                    "index_closed": built.index.closed,
                },
            )

            async with service_module.app.router.lifespan_context(service_module.app):
                rebuilt, new_provider = agents[AGENT].runtime, providers[-1]
                measure("Runtime Build Success", rebuilt is not built and rebuilt.index.owned)
                measure("Registered Agent Availability", get_agent(AGENT) is rebuilt.graph)
                measure("Startup External Call Avoidance", not external and not new_provider.routes)
                async with httpx.AsyncClient(base_url="http://test") as web:
                    _, ready = await metadata(web, True)
                save("16_restart", ready)
                repeated = await client.ainvoke("Repita", user_id="A", thread_id="X")
                typed(repeated, "grounded")
                measure(
                    "Runtime Memory Continuity",
                    await memory() == final_memory
                    and repeated.grounded_followup_result.source_correlation_id
                    == shifted.normative_result.correlation_id
                    and not new_provider.routes,
                )
                save("17_restore_repeat", repeated)
            await close_checks(rebuilt, new_provider)
            save(
                "18_shutdown_reopened",
                {
                    "runtime_closed": rebuilt.closed,
                    "provider_closed": new_provider.closed,
                    "index_closed": rebuilt.index.closed,
                },
            )

            for failure, code in [
                ("index", "index_unavailable"),
                ("registry", "registry_invalid"),
                ("provider", "provider_not_configured"),
            ]:
                values = {"settings": current_settings, "provider_factory": provider_factory}
                if failure == "index":
                    values["settings"] = current_settings.model_copy(
                        update={"CHROMA_PERSIST_DIR": temp / "missing"}
                    )
                elif failure == "registry":
                    path = temp / "invalid_registry.json"
                    path.write_bytes(b"{}")
                    values["registry_path"] = path
                else:
                    values["settings"] = current_settings.model_copy(
                        update={"OPENROUTER_API_KEY": None}
                    )
                service_module.app.state.agent_runtime_options[AGENT] = values
                async with service_module.app.router.lifespan_context(service_module.app):
                    measure("Startup External Call Avoidance", not external)
                    async with httpx.AsyncClient(base_url="http://test") as web:
                        info, ready = await metadata(web, False, code)
                        denied = await web.post(f"/{AGENT}/invoke", json={"message": "2+2"})
                        measure(
                            "Unavailable Configuration Rejection",
                            denied.status_code == 503
                            and code in denied.text
                            and not next(a for a in info["agents"] if a["key"] == AGENT)[
                                "available"
                            ],
                        )
                        health = (await web.get("/health")).json()
                        assert health["status"] == "ok" and not health["integrated_agent"]["ready"]
                        save(
                            "19_unavailable_" + failure,
                            {
                                "readiness": ready,
                                "response": denied.json(),
                                "process_status": health["status"],
                            },
                        )

            for saver in savers:
                try:
                    await saver.conn.execute("SELECT 1")
                except ValueError:
                    measure("Resource Close Success", True)
                else:
                    measure("Resource Close Success", False)
            for declaration in packaging_audit["declarations"]:
                measure(
                    "Packaging Completeness",
                    declaration
                    in (ROOT / "code/docker/Dockerfile.service").read_text(encoding="utf-8"),
                )
            save(
                "20_packaging",
                {
                    "declarations_checked": len(packaging_audit["declarations"]),
                    "docker_build": packaging_audit["docker_build"],
                    "container_smoke": packaging_audit["container_smoke"],
                },
            )
            smoke_dir = temp / "import-smoke"
            smoke_dir.mkdir()
            packaging.test_simulated_container_layout_imports_registry_and_validates_all_assets(
                smoke_dir
            )
            measure("Import Smoke Success", True)
            save(
                "21_import_smoke",
                {"filesystem_layout_import_passed": True, "container_executed": False},
            )
    monkey.undo()
    check_hashes(protocol)
    write(
        "local_probes.json",
        dict(
            rows=len(rows),
            metrics=dict(metrics),
            external_call_attempts=len(external),
            startup_count=len(savers),
            providers_created=len(providers),
            all_hashes_unchanged=True,
            docker_build=packaging_audit["docker_build"],
            container_smoke=packaging_audit["container_smoke"],
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
