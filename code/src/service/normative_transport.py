"""Current-turn transport adapter for the frozen internal integration graph."""

from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph.state import CompiledStateGraph

from rag_baseline.calculator_contracts import CalculatorToolResult
from rag_baseline.conversation_contracts import ConversationIdentity, GroundedFollowUpResult
from rag_baseline.tool_contracts import NormativeToolResult, ToolStatus
from schema import ChatMessage

INTEGRATED_AGENT_NAME = "chatbot_ufpi_integrated_v1"


def is_integrated_agent(agent: Any) -> bool:
    # Agent lookup is trusted application configuration, never request state/config.
    return isinstance(agent, CompiledStateGraph) and agent.name == INTEGRATED_AGENT_NAME


def is_conversation_agent(agent: Any) -> bool:
    return (
        is_integrated_agent(agent)
        and "conversation_identity" in agent.builder.input_schema.__annotations__
    )


def conversation_identity(user_id, agent_id, thread_id) -> ConversationIdentity:
    if agent_id is None:
        raise ValueError("The selected agent path is required for conversation identity.")
    return ConversationIdentity(user_id=user_id, agent_id=agent_id, thread_id=thread_id)


def project_integrated_state(state: dict) -> ChatMessage:
    """Read typed terminal state; never recover normative data from message text."""
    message = state["messages"][-1]
    if not isinstance(message, AIMessage) or not isinstance(message.content, str):
        raise ValueError("Expected a terminal AI message.")
    audit = state["turn_audit"]
    result = state.get("normative_result")
    derived = state.get("grounded_followup_result")
    calculated = state.get("calculator_result")
    if calculated is not None:
        if (
            state.get("action") != "CALCULATOR"
            or result is not None
            or derived is not None
            or not isinstance(calculated, CalculatorToolResult)
            or not getattr(audit, "calculator_called", False)
            or getattr(audit, "calculator_calls", 0) != 1
            or audit.facade_calls != 0
            or audit.normative_tool_called
            or audit.nodes_visited[-1] != "calculator_emission"
            or audit.final_source != "calculator_result.content"
            or state.get("normative_correlation_id") != ""
        ):
            raise ValueError("Unexpected calculator emission state.")
        public = CalculatorToolResult.model_validate(calculated.model_dump())
        return ChatMessage(type="ai", content=message.content, calculator_result=public)
    if state.get("action") == "DIRECT":
        if (
            result is not None
            or derived is not None
            or audit.nodes_visited[-1] != "direct_response"
        ):
            raise ValueError("Unexpected direct result state.")
        return ChatMessage(type="ai", content=message.content)
    if derived is not None:
        if result is not None or not isinstance(derived, GroundedFollowUpResult):
            raise ValueError("Invalid derived presentation state.")
        if not audit.authoritative_emission or audit.nodes_visited[-1] != "authoritative_emission":
            raise ValueError("Derived presentation has not completed.")
        if audit.final_source != "grounded_followup_result.content" or str(
            derived.source_correlation_id
        ) != state.get("normative_correlation_id"):
            raise ValueError("Derived presentation source mismatch.")
        public_derived = GroundedFollowUpResult.model_validate(derived.model_dump())
        return ChatMessage(
            type="ai", content=message.content, grounded_followup_result=public_derived
        )
    if state.get("action") != "NORMATIVE_RAG" or not isinstance(result, NormativeToolResult):
        raise ValueError("Expected a typed normative result.")
    if not audit.authoritative_emission or audit.nodes_visited[-1] != "authoritative_emission":
        raise ValueError("Normative emission has not completed.")
    if str(result.correlation_id) != state.get("normative_correlation_id"):
        raise ValueError("Normative operation correlation mismatch.")
    field = {
        ToolStatus.ANSWER: "answer",
        ToolStatus.CLARIFICATION: "clarification_question",
        ToolStatus.ERROR: "safe_message",
    }[result.status]
    if audit.final_source != f"normative_result.{field}":
        raise ValueError("Unexpected normative emission source.")
    # Public dump only: to_persistence() and ToolMessage.artifact are never serialized.
    public_result = NormativeToolResult.model_validate(result.model_dump())
    return ChatMessage(type="ai", content=message.content, normative_result=public_result)
