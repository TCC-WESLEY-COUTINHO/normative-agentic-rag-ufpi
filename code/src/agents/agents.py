from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import Pregel

from schema import AgentInfo

DEFAULT_AGENT = "chatbot_ufpi_v2"

# Type alias to handle LangGraph's different agent patterns
# - @entrypoint functions return Pregel
# - StateGraph().compile() returns CompiledStateGraph
AgentGraph = CompiledStateGraph | Pregel


@dataclass
class Agent:
    description: str
    graph: AgentGraph | None = None
    import_path: str | None = None
    runtime_factory: str | None = None
    experimental: bool = False
    runtime: Any = None
    runtime_error: dict | None = None


agents: dict[str, Agent] = {
    "chatbot_ufpi_agentic": Agent(
        description="Consulta UFPI com roteamento de nível e filtro explícito de vigência.",
        import_path="agents.chatbot_ufpi_agentic:chatbot_ufpi_agentic",
    ),
    "chatbot_ufpi": Agent(
        description="Assistente acadêmico especializado no RGG da UFPI.",
        import_path="agents.chatbot_ufpi:chatbot_ufpi",
    ),
    "chatbot_ufpi_v2": Agent(
        description="Assistente acadêmico especializado no RGG da UFPI (v2) com busca semântica e por metadados.",
        import_path="agents.chatbot_ufpi_v2:chatbot_ufpi_v2",
    ),
    "chatbot_generic": Agent(
        description="Chatbot genérico simples para responder dúvidas gerais com suporte a cálculos.",
        import_path="agents.chatbot_generic:chatbot_generic",
    ),
    "chatbot_ufpi_integrated_v1": Agent(
        description="Protótipo v3.4: consulta normativa com geração citada, verificação, memória e calculadora determinística.",
        runtime_factory="rag_baseline.integrated_runtime:build_integrated_agent_runtime",
        experimental=True,
    ),
}


class AgentUnavailableError(RuntimeError):
    pass


def _load(path):
    module, name = path.split(":")
    return getattr(import_module(module), name)


def get_agent(agent_id: str) -> AgentGraph:
    entry = agents[agent_id]
    if entry.graph is None and entry.import_path:
        entry.graph = _load(entry.import_path)
    if entry.graph is None:
        raise AgentUnavailableError(
            (entry.runtime_error or {}).get("reason_code", "runtime_not_started")
        )
    return entry.graph


def get_all_agent_info() -> list[AgentInfo]:
    return [
        AgentInfo(
            key=agent_id,
            description=agent.description,
            experimental=agent.experimental,
            available=agent.graph is not None or agent.import_path is not None,
            unavailable_reason=(agent.runtime_error or {}).get("reason_code", "runtime_not_started")
            if agent.runtime_factory and agent.graph is None
            else None,
        )
        for agent_id, agent in agents.items()
    ]


def get_agent_readiness(agent_id):
    entry = agents[agent_id]
    if entry.runtime:
        result = entry.runtime.readiness()
    else:
        result = {
            "ready": bool(entry.graph is not None or entry.import_path),
            "reason_code": "runtime_not_started" if entry.runtime_factory else None,
            **(entry.runtime_error or {}),
        }
    return {**result, "registered": True, "experimental": entry.experimental}


@asynccontextmanager
async def initialize_agents(saver, store, *, runtime_options=None):
    from rag_baseline.integrated_runtime import RuntimeBuildError

    acquired = []
    async with AsyncExitStack() as stack:
        try:
            for key, entry in agents.items():
                if entry.runtime_factory:
                    acquired.append(entry)
                    entry.runtime_error = None
                    try:
                        entry.runtime = await stack.enter_async_context(
                            _load(entry.runtime_factory)(
                                saver, **(runtime_options or {}).get(key, {})
                            )
                        )
                        entry.graph = entry.runtime.graph
                    except RuntimeBuildError as exc:
                        entry.runtime_error = exc.checks
                    continue
                graph = get_agent(key)
                graph.checkpointer, graph.store = saver, store
            yield
        finally:
            for entry in acquired:
                entry.graph, entry.runtime = None, None
                entry.runtime_error = {"ready": False, "reason_code": "runtime_stopped"}
