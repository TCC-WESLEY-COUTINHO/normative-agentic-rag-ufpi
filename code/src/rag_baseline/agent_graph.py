"""Internal, stateless integration graph; intentionally absent from service registry.

Build with a trusted facade dependency. Do not project this graph through the
legacy message-only service: typed transport and memory belong to later work.
"""

from dataclasses import dataclass, replace
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph

from rag_baseline.agent_emission import AuthoritativeEmissionGate
from rag_baseline.agent_policy import ActionDecision, AgentAction, AgentActionPolicy
from rag_baseline.agent_tool import (
    NormativeFacade,
    build_normative_tool,
    safe_tool_error,
    validated_result,
)
from rag_baseline.tool_contracts import NormativeToolResult, ToolStatus


@dataclass(frozen=True)
class AgentTurnAudit:
    action: AgentAction
    action_reason_code: str
    correlation_id: str
    nodes_visited: tuple[str, ...] = ("action_policy",)
    normative_tool_called: bool = False
    facade_calls: int = 0
    normative_status: str | None = None
    retrieval_strategy: str | None = None
    authoritative_emission: bool = False
    final_source: str | None = None
    tool_exception_type: str | None = None


@dataclass
class _InvocationFacade:
    """Per-invocation receipt survives framework callback errors; never shared."""

    delegate: NormativeFacade
    calls: int = 0
    result: NormativeToolResult | None = None

    async def query(self, question, clarification=None, correlation_id=None):
        self.calls += 1
        self.result = await self.delegate.query(
            question=question,
            clarification=clarification,
            correlation_id=correlation_id,
        )
        return self.result


def _question_content(human: HumanMessage | None) -> str:
    if human is None:
        return ""
    if isinstance(human.content, str):
        return human.content
    parts = []
    for block in human.content:
        if isinstance(block, str):
            parts.append(block)
        elif (
            isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ):
            parts.append(block["text"])
        else:
            # Unsupported modalities cannot be reduced to a safe social prefix.
            return ""
    return "\n".join(parts)


class IntegratedAgentState(MessagesState, total=False):
    action: AgentAction
    action_decision: ActionDecision
    current_question: str
    normative_result: NormativeToolResult | None
    normative_correlation_id: str
    turn_audit: AgentTurnAudit


def build_integrated_graph(
    facade: NormativeFacade,
    *,
    checkpointer=None,
    memory_stamp=None,
    transformer=None,
    scope_gate=None,
    interpreter=None,
    transition_policy=None,
) -> CompiledStateGraph:
    if memory_stamp is not None:
        from rag_baseline.conversation_graph import build_conversation_graph

        return build_conversation_graph(
            facade,
            checkpointer=checkpointer,
            memory_stamp=memory_stamp,
            transformer=transformer,
            scope_gate=scope_gate,
            interpreter=interpreter,
            transition_policy=transition_policy,
        )
    if interpreter is not None:
        raise ValueError("A conversation interpreter requires persistent conversation state.")
    if checkpointer is not None:
        raise ValueError("A compatibility stamp is required for persistent conversation.")
    policy = AgentActionPolicy()
    gate = AuthoritativeEmissionGate()

    def action_policy(state: IntegratedAgentState):
        human = next((m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), None)
        question = _question_content(human)
        decision = policy.decide(question)
        correlation = str(uuid4())
        # Never trust caller-supplied previous action, result, correlation or audit.
        return {
            "action": decision.action,
            "action_decision": decision,
            "current_question": question,
            "normative_result": None,
            "normative_correlation_id": correlation,
            "turn_audit": AgentTurnAudit(decision.action, decision.reason_code, correlation),
        }

    def direct_response(state: IntegratedAgentState):
        decision = state["action_decision"]
        assert decision.action == AgentAction.DIRECT and decision.direct_response is not None
        audit = state["turn_audit"]
        return {
            "messages": [AIMessage(content=decision.direct_response)],
            "turn_audit": replace(
                audit,
                nodes_visited=(*audit.nodes_visited, "direct_response"),
                final_source="direct_response",
            ),
        }

    async def normative_tool(state: IntegratedAgentState, config: RunnableConfig):
        correlation = state["normative_correlation_id"]
        receipt = _InvocationFacade(facade)
        tool = build_normative_tool(receipt)
        tool_exception_type = None
        call = {
            "type": "tool_call",
            "id": str(uuid4()),
            "name": tool.name,
            "args": {"question": state["current_question"], "correlation_id": correlation},
        }
        try:
            message = await tool.ainvoke(call, config)
            if not isinstance(message, ToolMessage) or not isinstance(
                message.artifact, NormativeToolResult
            ):
                raise TypeError("Typed normative artifact missing.")
            result = message.artifact
        except Exception as exc:
            tool_exception_type = type(exc).__name__
            try:
                # A completion callback can fail after the facade returned.
                # Reuse that typed receipt without calling the facade again.
                result = validated_result(receipt.result)
                if str(result.correlation_id) != correlation:
                    raise ValueError("Normative result correlation mismatch.")
            except (TypeError, ValueError):
                result = safe_tool_error(UUID(correlation), tool_exception_type)
            message = ToolMessage(
                content=f"normative_rag: {result.status.value}",
                artifact=result,
                tool_call_id=call["id"],
                name=tool.name,
            )
        audit = state["turn_audit"]
        return {
            "messages": [message],
            "normative_result": result,
            "turn_audit": replace(
                audit,
                nodes_visited=(*audit.nodes_visited, "normative_tool"),
                normative_tool_called=True,
                facade_calls=receipt.calls,
                tool_exception_type=tool_exception_type,
                normative_status=result.status.value,
                retrieval_strategy=result.retrieval_strategy.value,
            ),
        }

    def authoritative_emission(state: IntegratedAgentState):
        result = state["normative_result"]
        assert result is not None
        message = gate.emit(result)
        field = {
            ToolStatus.ANSWER: "answer",
            ToolStatus.CLARIFICATION: "clarification_question",
            ToolStatus.ERROR: "safe_message",
        }[result.status]
        audit = state["turn_audit"]
        return {
            "messages": [message],
            "turn_audit": replace(
                audit,
                nodes_visited=(*audit.nodes_visited, "authoritative_emission"),
                authoritative_emission=True,
                final_source=f"normative_result.{field}",
            ),
        }

    graph = StateGraph(IntegratedAgentState)
    graph.add_node("action_policy", action_policy)
    graph.add_node("direct_response", direct_response)
    graph.add_node("normative_tool", normative_tool)
    graph.add_node("authoritative_emission", authoritative_emission)
    graph.add_edge(START, "action_policy")
    graph.add_conditional_edges(
        "action_policy",
        lambda state: state["action"],
        {
            AgentAction.DIRECT: "direct_response",
            AgentAction.NORMATIVE_RAG: "normative_tool",
        },
    )
    graph.add_edge("direct_response", END)
    graph.add_edge("normative_tool", "authoritative_emission")
    graph.add_edge("authoritative_emission", END)
    return graph.compile(name="chatbot_ufpi_integrated_v1")
