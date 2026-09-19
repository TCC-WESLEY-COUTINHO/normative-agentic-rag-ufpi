from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import (
    RunnableConfig,
    RunnableLambda,
    RunnableSerializable,
)
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.managed import RemainingSteps
from langgraph.prebuilt import ToolNode

from agents.tools import calculator, get_current_datetime
from core import get_model, settings


class AgentState(MessagesState, total=False):
    """Estado do agente genérico."""

    remaining_steps: RemainingSteps


tools = [calculator, get_current_datetime]


instructions = """
Você é um assistente útil e amigável. Sua função é ajudar os usuários respondendo suas perguntas de forma clara e precisa.

Quando necessário, use as ferramentas disponíveis:
- Para cálculos matemáticos, use a calculadora.
- Para informações sobre data e hora atual, use a ferramenta de data/hora.

Seja direto, objetivo e prestativo em todas as suas respostas."""


def wrap_model(model: BaseChatModel) -> RunnableSerializable[AgentState, AIMessage]:
    """Envolve o modelo com ferramentas e prompt do sistema."""
    bound_model = model.bind_tools(tools)
    preprocessor = RunnableLambda(
        lambda state: [SystemMessage(content=instructions)] + state["messages"],
        name="StateModifier",
    )
    return preprocessor | bound_model  # type: ignore[return-value]


async def acall_model(state: AgentState, config: RunnableConfig) -> AgentState:
    """Chama o modelo com o estado atual."""
    m = get_model(config["configurable"].get("model", settings.DEFAULT_MODEL))
    model_runnable = wrap_model(m)
    response = await model_runnable.ainvoke(state, config)

    if state["remaining_steps"] < 2 and response.tool_calls:
        return {
            "messages": [
                AIMessage(
                    id=response.id,
                    content="Desculpe, preciso de mais passos para processar esta solicitação.",
                )
            ]
        }
    return {"messages": [response]}


# Define o grafo
agent = StateGraph(AgentState)
agent.add_node("model", acall_model)
agent.add_node("tools", ToolNode(tools))
agent.set_entry_point("model")

# Sempre executa "model" depois de "tools"
agent.add_edge("tools", "model")


# Depois de "model", se houver tool calls, executa "tools". Caso contrário, END.
def pending_tool_calls(state: AgentState) -> Literal["tools", "done"]:
    """Verifica se há tool calls pendentes."""
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage):
        raise TypeError(f"Esperado AIMessage, recebido {type(last_message)}")
    if last_message.tool_calls:
        return "tools"
    return "done"


agent.add_conditional_edges("model", pending_tool_calls, {"tools": "tools", "done": END})

chatbot_generic = agent.compile()

