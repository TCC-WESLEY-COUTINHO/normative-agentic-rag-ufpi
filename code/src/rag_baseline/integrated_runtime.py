"""Assembly of the registered v3.4 runtime; imports acquire no resources.

The demo selects Jev with transition v2. BaselineSettings selects cited generation
and corpus v4; ASSISTANT_IDENTITY controls fixed replies about the assistant.
"""

import inspect
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from rag_baseline.config import BaselineSettings

CODE_DIR = Path(__file__).resolve().parents[2]
AGENT_ID = "chatbot_ufpi_integrated_v1"


class IntegratedRuntimeSettings(BaselineSettings):
    # Prototype presentation layer (assistant_identity.py). "off" reproduces the frozen
    # v3.4 conversation graph; reproducible evaluations run with "off".
    ASSISTANT_IDENTITY: Literal["on", "off"] = "on"
    NORMATIVE_REGISTRY_PATH: Path = CODE_DIR.parent / "data/normative_registry.json"
    # Conversation layer: "none" selects A'; the demo sets Jev with transition v2.
    CONVERSATION_INTERPRETER: str = "none"
    CONVERSATION_INTERPRETER_CONFIG: str | None = None  # JSON InterpreterConfig overrides


def interpreter_config(settings):
    """Reproducible interpreter condition from settings (no secrets inside)."""
    import json

    from rag_baseline.conversation_interpretation.factory import InterpreterConfig

    mode = getattr(settings, "CONVERSATION_INTERPRETER", "none") or "none"
    raw = getattr(settings, "CONVERSATION_INTERPRETER_CONFIG", None)
    overrides = json.loads(raw) if raw else {}
    return InterpreterConfig(
        **{
            "base_url": settings.OPENROUTER_BASE_URL,
            "app_name": settings.OPENROUTER_APP_NAME,
            **overrides,
            "mode": mode,
        }
    )


class RuntimeBuildError(RuntimeError):
    def __init__(self, code, checks):
        self.code = code
        self.checks = {**checks, "ready": False, "reason_code": code}
        super().__init__(code)


# Chroma 1.0.x has System.stop but no public Client.close. Count our leases;
# a pre-existing external system remains borrowed and is never stopped here.
_INDEX_LEASES: dict[str, list] = {}


def _stop_partial_chroma(system):
    from chromadb.api.rust import RustBindingsAPI
    from chromadb.config import Component

    # A failed Rust start never assigns bindings; its stock stop deletes that
    # missing attribute and would prevent the remaining components from closing.
    Component.stop(system)
    for component in reversed(list(system.components())):
        if isinstance(component, RustBindingsAPI) and not hasattr(component, "bindings"):
            continue
        component.stop()


class _IndexLease:
    def __init__(self, directory, collection_name):
        import chromadb
        from chromadb.api.shared_system_client import SharedSystemClient
        from chromadb.config import Settings

        from rag_baseline.vector_store import ChromaVectorStore

        self.key, self.closed = str(directory.resolve()), False
        cached = SharedSystemClient._identifier_to_system.get(self.key)
        try:
            client = chromadb.PersistentClient(
                path=self.key, settings=Settings(anonymized_telemetry=False)
            )
        except BaseException:
            partial = SharedSystemClient._identifier_to_system.get(self.key)
            if cached is None and partial is not None:
                try:
                    _stop_partial_chroma(partial)
                finally:
                    if SharedSystemClient._identifier_to_system.get(self.key) is partial:
                        del SharedSystemClient._identifier_to_system[self.key]
            raise
        shared = _INDEX_LEASES.get(self.key)
        if shared is None:
            shared = [client._system, 0, cached is None]
            _INDEX_LEASES[self.key] = shared
        shared[1] += 1
        self.owned = shared[2]
        try:
            collection = client.get_collection(collection_name, embedding_function=None)

            class ExistingIndex(ChromaVectorStore):
                def __init__(self):
                    # Reuse all retrieval methods, bypass get_or_create_collection.
                    self.persist_dir, self.collection_name = directory, collection_name
                    self.client, self.collection = client, collection

            self.store = ExistingIndex()
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.closed:
            return
        from chromadb.api.shared_system_client import SharedSystemClient

        self.closed = True
        shared = _INDEX_LEASES[self.key]
        shared[1] -= 1
        if shared[1] == 0:
            del _INDEX_LEASES[self.key]
            if shared[2]:
                shared[0].stop()
                if SharedSystemClient._identifier_to_system.get(self.key) is shared[0]:
                    del SharedSystemClient._identifier_to_system[self.key]


@dataclass
class IntegratedAgentRuntime:
    graph: Any
    service: Any
    router: Any
    facade: Any
    registry: Any
    memory_stamp: Any
    index: _IndexLease
    checks: dict = field(repr=False)
    closed: bool = False

    def readiness(self):
        checks = dict(self.checks)
        if self.closed:
            return {
                **checks,
                "ready": False,
                "reason_code": "runtime_stopped",
                "memory_ready": False,
            }
        try:
            checks["index_records"] = self.index.store.count()
            checks["index_available"] = checks["index_records"] > 0
        except Exception:
            checks["index_available"] = False
        checks["ready"] = all(
            checks[k]
            for k in (
                "provider_configured",
                "registry_valid",
                "index_available",
                "memory_ready",
                "memory_stamp_created",
                "calculator_available",
                "facade_ready",
            )
        )
        if not checks["ready"]:
            checks["reason_code"] = "dependency_unavailable"
        return checks


def _provider(settings):
    from rag_baseline.openrouter import OpenRouterClient

    return OpenRouterClient(
        api_key=settings.api_key_value(),
        base_url=settings.OPENROUTER_BASE_URL,
        embedding_model=settings.EMBEDDING_MODEL,
        embedding_batch_size=settings.EMBEDDING_BATCH_SIZE,
        llm_model=settings.LLM_MODEL,
        llm_temperature=settings.LLM_TEMPERATURE,
        llm_max_tokens=settings.LLM_MAX_TOKENS,
        timeout_seconds=settings.OPENROUTER_TIMEOUT_SECONDS,
        app_name=settings.OPENROUTER_APP_NAME,
        http_referer=settings.OPENROUTER_HTTP_REFERER,
    )


@asynccontextmanager
async def build_integrated_agent_runtime(
    checkpointer, *, settings=None, registry_path=None, provider_factory=None, interpreter=None
):
    """Borrow the application saver; own acquired index leases and provider lifecycle."""
    from rag_baseline.agent_graph import build_integrated_graph
    from rag_baseline.conversation_contracts import build_memory_stamp
    from rag_baseline.conversation_transform import GroundedFollowUpTransformer
    from rag_baseline.profiles import apply_profile
    from rag_baseline.prompts import V2_SYSTEM_PROMPT
    from rag_baseline.router import NormativeRouter
    from rag_baseline.scope_gate import NormativeScopeGate
    from rag_baseline.service import RagService
    from rag_baseline.tool_facade import NormativeRagFacade
    from rag_baseline.versioning import NormativeRegistry, VersionFilter

    if settings is None:
        base = IntegratedRuntimeSettings(_env_file=CODE_DIR / ".env")
        settings = apply_profile(base, base.CORPUS_PROFILE)
    checks = dict(
        ready=False,
        reason_code=None,
        provider_configured=bool(settings.api_key_value() and settings.api_key_value().strip()),
        registry_valid=False,
        index_available=False,
        index_records=None,
        memory_ready=checkpointer is not None,
        memory_stamp_created=False,
        calculator_available=False,
        facade_ready=False,
    )
    if not checks["provider_configured"]:
        raise RuntimeBuildError("provider_not_configured", checks)
    if checkpointer is None:
        raise RuntimeBuildError("memory_unavailable", checks)
    registry_path = Path(
        registry_path
        or getattr(
            settings, "NORMATIVE_REGISTRY_PATH", CODE_DIR.parent / "data/normative_registry.json"
        )
    )
    if not registry_path.is_absolute():
        registry_path = CODE_DIR / registry_path
    try:
        registry = NormativeRegistry.load(registry_path)
    except (OSError, ValueError):
        raise RuntimeBuildError("registry_invalid", checks) from None
    checks["registry_valid"] = True
    directory = settings.CHROMA_PERSIST_DIR
    if not directory.is_absolute():
        directory = CODE_DIR / directory
    if not directory.is_dir() or not (directory / "chroma.sqlite3").is_file():
        raise RuntimeBuildError("index_unavailable", checks)
    async with AsyncExitStack() as stack:
        try:
            index = _IndexLease(directory, settings.CHROMA_COLLECTION)
        except Exception:
            raise RuntimeBuildError("index_unavailable", checks) from None
        stack.callback(index.close)
        try:
            checks["index_records"] = index.store.count()
        except Exception:
            raise RuntimeBuildError("index_unavailable", checks) from None
        if checks["index_records"] == 0:
            raise RuntimeBuildError("index_empty", checks)
        checks["index_available"] = True
        provider = (provider_factory or _provider)(settings)
        close = getattr(provider, "aclose", None)
        if close is not None:

            async def close_provider():
                result = close()
                if inspect.isawaitable(result):
                    await result

            stack.push_async_callback(close_provider)
        service = RagService(
            openrouter=provider,
            vector_store=index.store,
            top_k=settings.RETRIEVAL_TOP_K,
            embedding_model=settings.EMBEDDING_MODEL,
            llm_model=settings.LLM_MODEL,
            system_prompt=V2_SYSTEM_PROMPT,
            generation_mode=getattr(settings, "GENERATION_MODE", "cited_v3"),
        )
        router = NormativeRouter(provider, model=settings.ROUTER_MODEL)
        facade = NormativeRagFacade(service, router, VersionFilter(registry))
        stamp = build_memory_stamp(index.store, registry_path)
        from rag_baseline.conversation_interpretation.factory import (
            build_conversation_interpreter,
            build_transition_policy,
        )

        if interpreter is None:
            interpreter = build_conversation_interpreter(
                interpreter_config(settings), api_key=settings.api_key_value()
            )
        transition_policy = build_transition_policy(interpreter_config(settings))
        graph = build_integrated_graph(
            facade,
            checkpointer=checkpointer,
            memory_stamp=stamp,
            transformer=GroundedFollowUpTransformer(),
            scope_gate=NormativeScopeGate(provider, model=settings.ROUTER_MODEL),
            interpreter=interpreter,
            transition_policy=transition_policy,
            assistant_identity=getattr(settings, "ASSISTANT_IDENTITY", "on") == "on",
        )
        checks.update(
            memory_stamp_created=True, calculator_available=True, facade_ready=True, ready=True
        )
        runtime = IntegratedAgentRuntime(
            graph, service, router, facade, registry, stamp, index, checks
        )
        try:
            yield runtime
        finally:
            runtime.closed = True
