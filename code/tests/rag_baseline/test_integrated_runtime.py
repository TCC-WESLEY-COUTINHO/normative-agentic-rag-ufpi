"""Operational assembly and registered service boundaries; providers are controlled."""

import asyncio
import importlib
import json
import os
import subprocess
import sys

import httpx
import pytest
import test_retrieval_strategies as retrieval
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from rag_baseline.config import BaselineSettings
from rag_baseline.versioning import REGISTRY_PATH

ROOT = REGISTRY_PATH.parent.parent
AGENT = "chatbot_ufpi_integrated_v1"
LEGACY = {"chatbot_ufpi", "chatbot_ufpi_v2", "chatbot_generic", "chatbot_ufpi_agentic"}
registry = retrieval.registry
runtime = retrieval.runtime


@pytest.fixture
def assembly():
    name = "rag_baseline.integrated_runtime"
    if importlib.util.find_spec(name) is None:
        pytest.fail("Integrated runtime assembly is not implemented")
    return importlib.import_module(name)


class Provider(retrieval.Provider):
    llm_model = "qwen/qwen3-30b-a3b-instruct-2507"

    def __init__(self):
        super().__init__()
        self.closed = False
        self.scope_calls = []
        self.scopes.update(
            {
                "Posso cancelar uma disciplina na graduação?": "graduacao",
                "Na pós-graduação, posso cancelar uma disciplina ?": "pos_graduacao",
                "Resolução 177/2012, art. 68": "graduacao",
            }
        )

    async def structured_chat(self, **kwargs):
        data = json.loads(kwargs["user_prompt"])
        if "decision" in kwargs["schema"].get("properties", {}):
            self.scope_calls.append(dict(question=data["question"], model=kwargs["model"]))
            return json.dumps({"decision": "IN_SCOPE_NORMATIVE"})
        if data["question"] == "Posso cancelar uma disciplina?":
            scope = "graduacao" if data.get("clarification") == "graduação" else None
            self.scopes[data["question"]] = scope
        return await super().structured_chat(**kwargs)

    async def aclose(self):
        self.closed = True


def options(runtime, tmp_path, **changes):
    service, _, _, _, _ = runtime
    return BaselineSettings(
        _env_file=None,
        **{
            "OPENROUTER_API_KEY": "controlled-not-a-real-key",
            "CHROMA_PERSIST_DIR": service.vector_store.persist_dir,
            "CHROMA_COLLECTION": service.vector_store.collection_name,
            **changes,
        },
    )


def test_registry_keeps_default_and_all_existing_ids():
    from agents.agents import DEFAULT_AGENT, agents, get_all_agent_info

    assert AGENT in agents
    assert LEGACY <= agents.keys()
    assert DEFAULT_AGENT == "chatbot_ufpi_v2"
    infos = get_all_agent_info()
    assert len({i.key for i in infos}) == len(infos)
    integrated = next(i for i in infos if i.key == AGENT)
    assert integrated.experimental and not integrated.available


def test_imports_do_not_construct_resources_or_unused_supervisor():
    script = """
import sys, httpx, chromadb
from rag_baseline.openrouter import OpenRouterClient
def fail(*args, **kwargs):
    raise AssertionError("resource created at import")
chromadb.PersistentClient = fail
OpenRouterClient.__init__ = fail
httpx.Client.send = fail
httpx.AsyncClient.send = fail
import rag_baseline.integrated_runtime
import agents.agents
assert "agents.langgraph_supervisor_agent" not in sys.modules
assert "agents.tools" not in sys.modules
print("import isolated")
"""
    run = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT / "code",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT / "code/src") + os.pathsep + os.environ.get("PYTHONPATH", ""),
        },
    )
    assert run.returncode == 0, run.stdout.decode(errors="replace")
    assert b"import isolated" in run.stdout


@pytest.mark.asyncio
async def test_factory_builds_real_core_once_and_borrows_saver(assembly, runtime, tmp_path):
    provider, calls = Provider(), []

    def provider_factory(settings):
        calls.append(settings)
        return provider

    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "saver.sqlite")) as saver:
        async with assembly.build_integrated_agent_runtime(
            saver, settings=options(runtime, tmp_path), provider_factory=provider_factory
        ) as built:
            assert built.graph.checkpointer is saver
            assert built.readiness()["ready"]
            assert built.memory_stamp.corpus_fingerprint
            assert built.service.openrouter is provider
            assert built.router.model == built.service.llm_model
            assert built.service.top_k == 5
            assert built.service.generation_mode == "cited_v3"
            assert built.graph.name == AGENT
            assert provider.routes == provider.embeddings == provider.prompts == []
            assert len(calls) == 1
        assert built.closed and provider.closed
        # Runtime must not close the borrowed application saver.
        await saver.aget_tuple({"configurable": {"thread_id": "still-open"}})


@pytest.mark.parametrize(
    "failure,code",
    [
        ("missing_index", "index_unavailable"),
        ("missing_collection", "index_unavailable"),
        ("empty_collection", "index_empty"),
        ("invalid_registry", "registry_invalid"),
        ("missing_registry_evidence", "registry_invalid"),
        ("missing_provider", "provider_not_configured"),
    ],
)
@pytest.mark.asyncio
async def test_expected_startup_failures_are_safe_and_never_create_index(
    assembly, runtime, tmp_path, failure, code
):
    changes, registry_path = {}, None
    if failure == "missing_index":
        changes["CHROMA_PERSIST_DIR"] = tmp_path / "missing"
    elif failure == "missing_collection":
        changes["CHROMA_COLLECTION"] = "does_not_exist"
    elif failure == "empty_collection":
        store = runtime[0].vector_store
        store.client.create_collection("empty_collection", embedding_function=None)
        changes["CHROMA_COLLECTION"] = "empty_collection"
    elif failure in {"invalid_registry", "missing_registry_evidence"}:
        registry_path = tmp_path / "assets/data/normative_registry.json"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_bytes(
            b"{}" if failure == "invalid_registry" else REGISTRY_PATH.read_bytes()
        )
    else:
        changes["OPENROUTER_API_KEY"] = None
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "fail.sqlite")) as saver:
        with pytest.raises(assembly.RuntimeBuildError) as error:
            async with assembly.build_integrated_agent_runtime(
                saver, settings=options(runtime, tmp_path, **changes), registry_path=registry_path
            ):
                pytest.fail("Invalid runtime became ready")
        assert error.value.code == code
        assert "controlled-not-a-real-key" not in str(error.value)
    assert not (tmp_path / "missing").exists()
    assert "does_not_exist" not in [
        c.name for c in runtime[0].vector_store.client.list_collections()
    ]


@pytest.mark.asyncio
async def test_owned_chroma_system_and_provider_close_on_shutdown(assembly, runtime, tmp_path):
    import shutil

    from chromadb.api.shared_system_client import SharedSystemClient

    # A distinct copied disk index has no process-cached client and is owned by runtime.
    target = tmp_path / "owned-index"
    shutil.copytree(runtime[0].vector_store.persist_dir, target)
    provider = Provider()
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "close.sqlite")) as saver:
        async with assembly.build_integrated_agent_runtime(
            saver,
            settings=options(runtime, tmp_path, CHROMA_PERSIST_DIR=target),
            provider_factory=lambda _: provider,
        ) as built:
            assert built.index.owned
            assert str(target.resolve()) in SharedSystemClient._identifier_to_system
        assert built.index.closed and provider.closed
        assert str(target.resolve()) not in SharedSystemClient._identifier_to_system


@pytest.mark.asyncio
async def test_factory_is_independent_of_current_directory(
    assembly, runtime, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "cwd.sqlite")) as saver:
        async with assembly.build_integrated_agent_runtime(
            saver, settings=options(runtime, tmp_path), provider_factory=lambda _: Provider()
        ) as built:
            assert built.readiness()["registry_valid"] and built.readiness()["index_available"]


@pytest.fixture
def registered(assembly, runtime, tmp_path, monkeypatch):
    import service.service as service_module
    from agents.agents import agents
    from core.settings import DatabaseType

    provider = Provider()
    monkeypatch.setattr(service_module.settings, "DATABASE_TYPE", DatabaseType.SQLITE)
    monkeypatch.setattr(
        service_module.settings, "SQLITE_DB_PATH", str(tmp_path / "registered.sqlite")
    )
    monkeypatch.setattr(service_module.settings, "AUTH_SECRET", None)
    monkeypatch.setattr(service_module.settings, "LANGFUSE_TRACING", False)
    monkeypatch.setattr(
        service_module.app.state,
        "agent_runtime_options",
        {
            AGENT: {
                "settings": options(
                    runtime,
                    tmp_path,
                    GENERATION_MODE="free_text_v2",
                    CORPUS_PROFILE="duas-regulacoes",
                ),
                "provider_factory": lambda _: provider,
            }
        },
        raising=False,
    )
    # No graph/facade/get_agent replacement. Normal lifespan and registry own construction.
    return service_module, provider, agents[AGENT]


async def request(web, text, user="A", thread="X", mode="invoke", **kwargs):
    from schema import ChatMessage

    response = await web.post(
        f"/{AGENT}/{mode}", json={"message": text, "user_id": user, "thread_id": thread, **kwargs}
    )
    assert response.status_code == 200, response.text
    if mode == "stream":
        lines = [line for line in response.text.splitlines() if line.startswith("data:")]
        assert len(lines) == 2 and lines[-1] == "data: [DONE]"
        return ChatMessage.model_validate(json.loads(lines[0][6:])["content"])
    return ChatMessage.model_validate(response.json())


@pytest.mark.asyncio
async def test_registered_info_readiness_direct_calculator_and_shutdown(registered):
    service_module, provider, entry = registered
    async with service_module.app.router.lifespan_context(service_module.app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=service_module.app), base_url="http://test"
        ) as web:
            info = (await web.get("/info")).json()
            assert info["default_agent"] == "chatbot_ufpi_v2"
            item = next(i for i in info["agents"] if i["key"] == AGENT)
            assert item["available"] and item["experimental"]
            assert (await web.get("/health")).json()["status"] == "ok"
            ready = (await web.get(f"/agents/{AGENT}/readiness")).json()
            assert ready["ready"] and ready["registered"] and ready["provider_configured"]
            direct = await request(web, "Oi")
            assert (
                direct.normative_result
                is direct.calculator_result
                is direct.grounded_followup_result
                is None
            )
            calculated = await request(web, "2+2")
            assert calculated.calculator_result.content == "4"
            assert provider.routes == provider.prompts == provider.embeddings == []
            assert entry.runtime.graph is entry.graph
    assert entry.runtime is None and entry.graph is None and provider.closed


@pytest.mark.parametrize("mode", ["invoke", "stream"])
@pytest.mark.asyncio
async def test_registered_multiturn_normative_followup_calculator_domain_and_model_boundary(
    registered, mode
):
    service_module, provider, entry = registered
    async with service_module.app.router.lifespan_context(service_module.app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=service_module.app), base_url="http://test"
        ) as web:
            first = await request(
                web, "Posso cancelar uma disciplina na graduação?", mode=mode, model="gpt-4o"
            )
            assert first.normative_result.status == "ANSWER"
            original = first.normative_result
            follow = await request(web, "Explique mais simples", mode=mode)
            assert follow.grounded_followup_result.source_correlation_id == original.correlation_id
            assert follow.grounded_followup_result.content == original.answer
            assert follow.grounded_followup_result.guard_status == "FALLBACK_TO_SOURCE"
            math = await request(web, "2+2", mode=mode)
            assert math.calculator_result.content == "4"
            repeated = await request(web, "Repita", mode=mode)
            assert (
                repeated.grounded_followup_result.source_correlation_id == original.correlation_id
            )
            shifted = await request(web, "E na pós?", mode=mode)
            assert shifted.normative_result.domain == "pos_graduacao"
            assert shifted.normative_result.correlation_id != original.correlation_id
            assert provider.routes == []  # Both resolved queries have explicit levels.
            assert len(provider.scope_calls) == 2
            assert all(call["model"] == entry.runtime.router.model for call in provider.scope_calls)
            assert entry.runtime.service.llm_model == "qwen/qwen3-30b-a3b-instruct-2507"


@pytest.mark.asyncio
async def test_registered_clarification_isolation_and_concurrent_identities(registered):
    service_module, provider, _ = registered
    async with service_module.app.router.lifespan_context(service_module.app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=service_module.app), base_url="http://test"
        ) as web:
            first = await request(web, "Posso cancelar uma disciplina?")
            assert first.normative_result.status == "CLARIFICATION"
            other, math = await asyncio.gather(
                request(web, "Repita", user="B"), request(web, "2+2", user="C")
            )
            assert other.normative_result is other.grounded_followup_result is None
            assert math.calculator_result.content == "4"
            second = await request(web, "graduação")
            assert second.normative_result.status == "ANSWER"
            assert second.normative_result.correlation_id == first.normative_result.correlation_id
            assert provider.routes[-1]["question"] == "Posso cancelar uma disciplina?"
            assert provider.routes[-1]["clarification"] == "graduação"


@pytest.mark.parametrize(
    "failure,code",
    [
        ("index", "index_unavailable"),
        ("provider", "provider_not_configured"),
        ("registry", "registry_invalid"),
    ],
)
@pytest.mark.asyncio
async def test_registered_unavailable_is_explicit_and_legacy_default_survives(
    registered, tmp_path, failure, code
):
    service_module, _, _ = registered
    values = service_module.app.state.agent_runtime_options[AGENT]
    if failure == "index":
        values["settings"] = values["settings"].model_copy(
            update={"CHROMA_PERSIST_DIR": tmp_path / "missing"}
        )
    elif failure == "provider":
        values["settings"] = values["settings"].model_copy(update={"OPENROUTER_API_KEY": None})
    else:
        values["registry_path"] = tmp_path / "missing-registry.json"
    async with service_module.app.router.lifespan_context(service_module.app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=service_module.app), base_url="http://test"
        ) as web:
            info = (await web.get("/info")).json()
            assert info["default_agent"] == "chatbot_ufpi_v2"
            item = next(i for i in info["agents"] if i["key"] == AGENT)
            assert not item["available"] and item["unavailable_reason"] == code
            for mode in ["invoke", "stream"]:
                response = await web.post(f"/{AGENT}/{mode}", json={"message": "2+2"})
                assert response.status_code == 503 and code in response.text
                unknown = await web.post(f"/unknown-agent/{mode}", json={"message": "Oi"})
                assert unknown.status_code == 404
            assert (await web.get("/health")).json()["status"] == "ok"
            assert not (await web.get(f"/agents/{AGENT}/readiness")).json()["ready"]


@pytest.mark.asyncio
async def test_registered_memory_reopens_and_application_closes_saver(registered):
    service_module, _, entry = registered
    providers = []

    def factory(settings):
        provider = Provider()
        providers.append(provider)
        return provider

    service_module.app.state.agent_runtime_options[AGENT]["provider_factory"] = factory
    async with service_module.app.router.lifespan_context(service_module.app):
        saver = entry.graph.checkpointer
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=service_module.app), base_url="http://test"
        ) as web:
            first = await request(web, "Resolução 177/2012, art. 68")
    assert providers[0].closed
    with pytest.raises(ValueError):
        await saver.conn.execute("SELECT 1")
    async with service_module.app.router.lifespan_context(service_module.app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=service_module.app), base_url="http://test"
        ) as web:
            repeated = await request(web, "Repita")
            derived = repeated.grounded_followup_result
            assert derived.content == first.normative_result.answer
            assert derived.source_correlation_id == first.normative_result.correlation_id
            assert derived.references == first.normative_result.references
            assert not providers[1].routes
    assert len(providers) == 2 and all(p.closed for p in providers)


@pytest.mark.asyncio
async def test_partial_build_failure_closes_acquired_provider(
    assembly, runtime, tmp_path, monkeypatch
):
    import rag_baseline.conversation_contracts as contracts

    provider = Provider()

    def broken(*args):
        raise RuntimeError("controlled build failure")

    monkeypatch.setattr(contracts, "build_memory_stamp", broken)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "partial.sqlite")) as saver:
        with pytest.raises(RuntimeError, match="controlled build failure"):
            async with assembly.build_integrated_agent_runtime(
                saver, settings=options(runtime, tmp_path), provider_factory=lambda _: provider
            ):
                pytest.fail("Broken runtime started")
        assert provider.closed


@pytest.mark.asyncio
async def test_overlapping_runtime_leases_do_not_stop_active_chroma(assembly, runtime, tmp_path):
    import shutil

    target = tmp_path / "shared-owned"
    shutil.copytree(runtime[0].vector_store.persist_dir, target)
    settings = options(runtime, tmp_path, CHROMA_PERSIST_DIR=target)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "shared.sqlite")) as saver:
        first = assembly.build_integrated_agent_runtime(
            saver, settings=settings, provider_factory=lambda _: Provider()
        )
        second = assembly.build_integrated_agent_runtime(
            saver, settings=settings, provider_factory=lambda _: Provider()
        )
        a = await first.__aenter__()
        b = await second.__aenter__()
        try:
            await first.__aexit__(None, None, None)
            assert a.closed and b.index.store.count() == 10
        finally:
            await second.__aexit__(None, None, None)
        assert b.closed and b.index.closed


@pytest.mark.asyncio
async def test_health_and_startup_never_call_external_http_or_supabase(registered, monkeypatch):
    import socket

    import supabase

    service_module, provider, _ = registered
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append(True)
        pytest.fail("External IO or Supabase initialization during startup/health")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(supabase, "create_client", forbidden)
    # Invoke endpoint functions directly here so all HTTP sends can be forbidden.
    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)
    monkeypatch.setattr(service_module.settings, "LANGFUSE_TRACING", True)
    async with service_module.app.router.lifespan_context(service_module.app):
        health = await service_module.health_check()
        readiness = await service_module.agent_readiness(AGENT)
        assert health["status"] == "ok" and readiness["ready"]
        assert provider.routes == provider.prompts == provider.embeddings == []
    assert not attempts


@pytest.mark.asyncio
async def test_corrupt_index_startup_leaves_no_partial_chroma_system(assembly, runtime, tmp_path):
    from chromadb.api.shared_system_client import SharedSystemClient

    path = tmp_path / "corrupt-index"
    path.mkdir()
    (path / "chroma.sqlite3").write_bytes(b"controlled corrupt database")
    key = str(path.resolve())
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "corrupt.sqlite")) as saver:
        try:
            with pytest.raises(assembly.RuntimeBuildError) as error:
                async with assembly.build_integrated_agent_runtime(
                    saver, settings=options(runtime, tmp_path, CHROMA_PERSIST_DIR=path)
                ):
                    pytest.fail("Corrupt index became ready")
            assert error.value.code == "index_unavailable"
            assert key not in SharedSystemClient._identifier_to_system
        finally:
            partial = SharedSystemClient._identifier_to_system.pop(key, None)
            if partial is not None:
                from contextlib import suppress

                with suppress(AttributeError):
                    partial.stop()
