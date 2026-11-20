"""Checkpointed conversation graph with interpretation and optional assistant identity.

The normative facade supplies retrieval, cited generation and verification in v3.4.
"""

from dataclasses import dataclass, replace
from uuid import uuid4

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from rag_baseline.agent_emission import AuthoritativeEmissionGate
from rag_baseline.agent_graph import (
    AgentTurnAudit,
    IntegratedAgentState,
    _InvocationFacade,
    _question_content,
)
from rag_baseline.agent_policy import AgentAction, AgentActionPolicy
from rag_baseline.agent_tool import build_normative_tool, safe_tool_error, validated_result
from rag_baseline.assistant_identity import ROUTE as IDENTITY_ROUTE
from rag_baseline.assistant_identity import assistant_identity_reply
from rag_baseline.calculator import build_calculator_tool
from rag_baseline.calculator_contracts import CalculatorRequest, CalculatorToolResult
from rag_baseline.conversation_contracts import (
    ConversationIdentity,
    ConversationNormativeMemory,
    GroundedFollowUpResult,
    NormativeMemoryCompatibilityStamp,
    PendingClarification,
    build_memory_stamp,
    load_conversation_memory,
)
from rag_baseline.conversation_interpretation.contracts import (
    CONTEXT_LEVEL,
    InterpretationOutcome,
    TurnContext,
)
from rag_baseline.conversation_interpretation.transition import (
    INTERPRETABLE,
    ConversationTransitionPolicy,
    TransitionDecision,
)
from rag_baseline.conversation_policy import (
    ABOUT_ASSISTANT_RESPONSE,
    OUT_OF_SCOPE_RESPONSE,
    ContextualNormativeQueryResolver,
    ConversationFollowUpPolicy,
    FollowUpAction,
    clarification_level,
    declared_level_clarification,
)
from rag_baseline.conversation_transform import GroundedFollowUpTransformer
from rag_baseline.scope_gate import NormativeScopeGate

__all__ = [
    "ConversationIdentity",
    "ConversationNormativeMemory",
    "GroundedFollowUpResult",
    "NormativeMemoryCompatibilityStamp",
    "PendingClarification",
    "build_memory_stamp",
    "ConversationFollowUpPolicy",
    "ContextualNormativeQueryResolver",
    "GroundedFollowUpTransformer",
    "build_conversation_graph",
]


@dataclass(frozen=True)
class ConversationTurnAudit(AgentTurnAudit):
    conversation_action: str = ""
    memory_status: str = "ABSENT"
    stale_reason: str | None = None
    transform_calls: int = 0
    transform_reason: str | None = None
    transform_violations: tuple[str, ...] = ()
    replaced_incompatible_memory: bool = False
    calculator_called: bool = False
    calculator_calls: int = 0
    calculator_operation: str | None = None
    calculator_status: str | None = None
    facade_called: bool = False
    memory_preserved: bool = False
    pending_preserved: bool = False
    scope_gate_decision: str | None = None
    scope_gate_status: str | None = None
    scope_gate_provider_calls: int = 0
    scope_gate_latency_ms: float = 0.0
    declared_level_used: bool = False
    # Experimental interpretation (A''). Empty when no interpreter is configured.
    interpreter: str | None = None
    interpreter_status: str | None = None
    interpretation: dict | None = None
    base_conversation_action: str | None = None
    transition_reason: str | None = None
    interpreter_calls: int = 0
    interpreter_latency_ms: float = 0.0
    interpreter_input_tokens: int = 0
    interpreter_output_tokens: int = 0
    interpreter_cost_usd: float | None = None
    interpreter_model: str | None = None
    interpreter_method: str | None = None
    interpreter_error_type: str | None = None
    interpreter_detail: str | None = None
    interpreter_adjustments: tuple[str, ...] = ()
    interpreter_stages: tuple[str, ...] = ()
    interpreter_probabilities: dict | None = None
    question_override: str | None = None
    deferred_question: str | None = None
    interpreted_level_persisted: str | None = None
    # Transition policy v2 (Stage 7); defaults keep v1 audits unchanged.
    transition_policy_version: str | None = None
    superseded_pending: bool = False
    declared_level_suppressed: bool = False
    third_party_query_level: str | None = None


class ConversationState(IntegratedAgentState, total=False):
    action: AgentAction | FollowUpAction
    conversation_identity: ConversationIdentity
    conversation_memory: ConversationNormativeMemory | None
    grounded_followup_result: GroundedFollowUpResult | None
    followup_action: FollowUpAction
    transform_kind: str | None
    calculator_result: CalculatorToolResult | None
    calculator_request: CalculatorRequest | None
    interpretation_decision: TransitionDecision | None


REPEAT_CONTEXT = "O contexto normativo anterior não pode ser reutilizado nesta versão. Repita a pergunta original."
UNRESOLVED = "Repita a pergunta completa e especifique o nível acadêmico desejado."


def _active_subject(memory) -> str | None:
    """Subject of this conversation only. An answer mentions many words the user never asked."""
    return memory.last_normative_question


def build_conversation_graph(
    facade,
    *,
    checkpointer,
    memory_stamp,
    transformer=None,
    scope_gate=None,
    interpreter=None,
    transition_policy=None,
    assistant_identity=False,
):
    """`interpreter` (A'' only) is a ConversationInterpreter; None keeps A' unchanged."""
    if checkpointer is None:
        raise ValueError("Conversation memory requires an injected checkpointer.")
    current = NormativeMemoryCompatibilityStamp.model_validate(memory_stamp.model_dump())
    policy, resolver = ConversationFollowUpPolicy(), ContextualNormativeQueryResolver()
    transformer = transformer or GroundedFollowUpTransformer()
    scope_gate = scope_gate if scope_gate is not None else NormativeScopeGate()
    gate = AuthoritativeEmissionGate()
    calculator = build_calculator_tool()
    interpret_runnable = interpreter.as_runnable() if interpreter is not None else None
    transition = transition_policy or ConversationTransitionPolicy()

    def entry(state: ConversationState, config: RunnableConfig):
        raw_identity = state["conversation_identity"]
        identity = ConversationIdentity.model_validate(
            raw_identity.model_dump()
            if isinstance(raw_identity, ConversationIdentity)
            else raw_identity
        )
        if config.get("configurable", {}).get("thread_id") != identity.storage_key():
            raise ValueError("Conversation namespace does not match declared identity.")
        memory, status, reason = load_conversation_memory(
            state.get("conversation_memory"), identity, current
        )
        from langchain_core.messages import HumanMessage

        human = next((m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), None)
        text = _question_content(human)
        identity_reply = assistant_identity_reply(text) if assistant_identity else None
        decision = policy.decide(
            text,
            pending=status == "VALID" and memory.pending_clarification is not None,
            active_subject=_active_subject(memory) if status == "VALID" else None,
        )
        audit = ConversationTurnAudit(
            action=AgentAction.DIRECT,
            action_reason_code=decision.reason_code
            if decision.action == FollowUpAction.CALCULATOR
            else decision.action.value,
            correlation_id="",
            nodes_visited=("conversation_entry",),
            conversation_action=decision.action.value,
            memory_status=status,
            stale_reason=reason,
        )
        return {
            "current_question": text,
            "normative_result": None,
            "grounded_followup_result": None,
            "calculator_result": None,
            "calculator_request": decision.calculator_request,
            "normative_correlation_id": "",
            "conversation_identity": identity,
            "conversation_memory": memory,
            "turn_audit": audit,
            "followup_action": decision.action,
            "transform_kind": decision.transform_kind,
            "action": AgentAction.DIRECT,
            "action_decision": None,
            "interpretation_decision": None,
            # Optional prototype layer, ahead of every other decision; when disabled
            # (or the message is not a whole identity question) the turn is unchanged.
            **({
                "followup_action": FollowUpAction.ASSISTANT_IDENTITY,
                "turn_audit": replace(
                    audit,
                    conversation_action=FollowUpAction.ASSISTANT_IDENTITY.value,
                    action_reason_code=f"{IDENTITY_ROUTE}_{identity_reply.intent}",
                ),
            } if identity_reply is not None else {}),
        }

    async def interpret(state: ConversationState, config: RunnableConfig):
        """Probabilistic reading of this thread's message; the policy applies it."""
        base = state["followup_action"]
        audit = replace(
            state["turn_audit"],
            nodes_visited=(*state["turn_audit"].nodes_visited, "conversation_interpretation"),
            interpreter=interpreter.name,
            base_conversation_action=base.value,
        )
        if base not in INTERPRETABLE:
            return {"turn_audit": replace(audit, interpreter_status="not_invoked")}
        memory = state["conversation_memory"]
        valid = audit.memory_status == "VALID" and memory is not None
        pending = memory.pending_clarification if valid else None
        try:
            context = TurnContext(
                message=state["current_question"],
                pending_question=pending.original_question if pending else None,
                pending_clarification_question=pending.clarification_question if pending else None,
                declared_level=CONTEXT_LEVEL.get(memory.declared_level) if valid else None,
                last_normative_question=memory.last_normative_question if valid else None,
                has_pending_operation=pending is not None,
            )
        except ValueError:
            return {"turn_audit": replace(audit, interpreter_status="input_rejected")}
        try:
            outcome = await interpret_runnable.ainvoke(context, config)
        except Exception as exc:  # any untyped failure leaves A' fully in charge
            outcome = InterpretationOutcome(
                interpreter.name,
                "provider_error",
                error_type=type(exc).__name__,
                detail=str(exc)[:200],
                calls=1,
            )
        decision = transition.decide(base, outcome, context)
        audit = replace(
            audit,
            conversation_action=decision.action.value,
            action_reason_code=decision.action.value,
            interpreter_status=outcome.status,
            interpretation=outcome.interpretation.model_dump(mode="json")
            if outcome.interpretation is not None
            else None,
            transition_reason=decision.reason,
            interpreter_calls=outcome.calls,
            interpreter_latency_ms=outcome.latency_ms,
            interpreter_input_tokens=outcome.input_tokens,
            interpreter_output_tokens=outcome.output_tokens,
            interpreter_cost_usd=outcome.cost_usd,
            interpreter_model=outcome.model,
            interpreter_method=outcome.method,
            interpreter_error_type=outcome.error_type,
            interpreter_detail=outcome.detail,
            interpreter_adjustments=tuple(outcome.adjustments),
            interpreter_stages=tuple(outcome.stages),
            interpreter_probabilities=dict(outcome.probabilities) or None,
            question_override=decision.question_override,
            deferred_question=decision.deferred_question,
            transition_policy_version=getattr(decision, "policy_version", "transition-v1"),
            superseded_pending=getattr(decision, "superseded_pending", False),
        )
        # A technical failure leaves A' fully in charge: the decision is audited, but the
        # turn executes exactly as without an interpreter.
        failed = not outcome.ok or getattr(decision, "defer_to_base", False)
        return {
            "followup_action": decision.action,
            "interpretation_decision": None if failed else decision,
            "turn_audit": audit,
        }

    def direct(state, text, memory):
        audit = state["turn_audit"]
        return dict(
            messages=[AIMessage(content=text)],
            action=AgentAction.DIRECT,
            normative_result=None,
            grounded_followup_result=None,
            conversation_memory=memory,
            turn_audit=replace(
                audit,
                nodes_visited=(*audit.nodes_visited, "direct_response"),
                final_source="direct_response",
            ),
        )

    def update_memory(state, result, question, keep_current=False):
        memory = state["conversation_memory"]
        if result.status == "ERROR":
            if memory is None:
                return None
            return ConversationNormativeMemory.model_validate(
                {**memory.model_dump(), "pending_clarification": None}
            )
        base = (
            memory.model_dump()
            if state["turn_audit"].memory_status == "VALID" or keep_current
            else dict(
                memory_version=current.memory_version,
                conversation_identity=state["conversation_identity"],
                compatibility_stamp=current,
            )
        )
        if result.status == "ANSWER":
            base.update(
                last_normative_question=question,
                last_normative_result_persistence=result.to_persistence(),
                last_normative_correlation_id=result.correlation_id,
                pending_clarification=None,
            )
        else:
            base["pending_clarification"] = PendingClarification(
                original_question=question,
                clarification_question=result.clarification_question,
                correlation_id=result.correlation_id,
                compatibility_stamp=current,
            )
        return ConversationNormativeMemory.model_validate(base)

    def declare_level(state, level, source):
        base = (
            state["conversation_memory"].model_dump()
            if state["turn_audit"].memory_status == "VALID"
            else dict(
                memory_version=current.memory_version,
                conversation_identity=state["conversation_identity"],
                compatibility_stamp=current,
            )
        )
        return ConversationNormativeMemory.model_validate(
            {**base, "declared_level": level, "declared_level_source": source}
        )

    async def execute(state: ConversationState, config: RunnableConfig):
        action = state["followup_action"]
        memory, audit, text = (
            state["conversation_memory"],
            state["turn_audit"],
            state["current_question"],
        )
        valid = audit.memory_status == "VALID"
        interpreted = state.get("interpretation_decision")
        level_written = False
        if action == FollowUpAction.ASSISTANT_IDENTITY:
            output = direct(state, assistant_identity_reply(text).content, memory)
            output["turn_audit"] = replace(
                output["turn_audit"], memory_preserved=True, pending_preserved=True
            )
            return output
        if action == FollowUpAction.CLARIFY_INTENT:
            output = direct(state, interpreted.direct_message, memory)
            output["turn_audit"] = replace(
                output["turn_audit"], memory_preserved=True, pending_preserved=True
            )
            return output
        if interpreted is not None and interpreted.clear_pending and valid:
            memory = ConversationNormativeMemory.model_validate(
                {**memory.model_dump(), "pending_clarification": None}
            )
            state = {**state, "conversation_memory": memory}
        if action == FollowUpAction.SAFE_DIRECT:
            return direct(state, AgentActionPolicy().decide(text).direct_response, memory)
        if action == FollowUpAction.ABOUT_ASSISTANT:
            return direct(state, ABOUT_ASSISTANT_RESPONSE, memory)
        if action == FollowUpAction.CLEAR_PENDING:
            updated = ConversationNormativeMemory.model_validate(
                {**memory.model_dump(), "pending_clarification": None}
            )
            return direct(state, "Pendência de esclarecimento cancelada.", updated)
        if action == FollowUpAction.DECLARE_LEVEL:
            if interpreted is not None:
                level = interpreted.persist_level
                audit = replace(audit, interpreted_level_persisted=level)
                state = {**state, "turn_audit": audit}
            else:
                level = clarification_level(text)
            updated = declare_level(state, level, "explicit_declaration")
            label = "graduação" if level == "graduacao" else "pós-graduação"
            return direct(state, f"Certo, vou considerar {label} nas próximas perguntas.", updated)
        if action == FollowUpAction.CALCULATOR:
            result = await calculator.ainvoke({"request": state["calculator_request"]}, config)
            result = CalculatorToolResult.model_validate(result.model_dump())
            return dict(
                messages=[AIMessage(content=result.content)],
                action=FollowUpAction.CALCULATOR,
                calculator_result=result,
                calculator_request=None,
                normative_result=None,
                grounded_followup_result=None,
                normative_correlation_id="",
                conversation_memory=memory,
                turn_audit=replace(
                    audit,
                    action=FollowUpAction.CALCULATOR,
                    nodes_visited=(*audit.nodes_visited, "calculator", "calculator_emission"),
                    final_source="calculator_result.content",
                    calculator_called=True,
                    calculator_calls=1,
                    calculator_operation=result.operation_kind,
                    calculator_status=result.status,
                    memory_preserved=True,
                    pending_preserved=True,
                ),
            )
        if action == FollowUpAction.GROUNDED_TRANSFORM:
            source = memory.restore_result() if valid else None
            if source is None:
                return direct(state, REPEAT_CONTEXT, memory)
            if source.core_status == "abstained":
                return direct(state, source.answer, memory)
            derived, violations, reason = await transformer.transform(
                text, state["transform_kind"], source
            )
            calls = int(
                state["transform_kind"] != "REPEAT"
                and source.core_status != "fallback"
                and transformer.provider is not None
            )
            return dict(
                messages=[AIMessage(content=derived.content)],
                action=AgentAction.NORMATIVE_RAG,
                normative_result=None,
                grounded_followup_result=derived,
                normative_correlation_id=str(source.correlation_id),
                conversation_memory=memory,
                turn_audit=replace(
                    audit,
                    action=AgentAction.NORMATIVE_RAG,
                    nodes_visited=(
                        *audit.nodes_visited,
                        "grounded_transform",
                        "authoritative_emission",
                    ),
                    correlation_id=str(source.correlation_id),
                    authoritative_emission=True,
                    final_source="grounded_followup_result.content",
                    transform_calls=calls,
                    transform_reason=reason,
                    transform_violations=tuple(violations),
                ),
            )
        question, clarification, correlation = text, None, uuid4()
        if interpreted is not None and interpreted.question_override:
            question = interpreted.question_override
        if action == FollowUpAction.CONTEXTUAL_NORMATIVE_RAG:
            question = (
                resolver.resolve(
                    text, memory.last_normative_question, memory.restore_result().domain
                )
                if valid and memory.restore_result()
                else None
            )
            if question is None:
                return direct(state, UNRESOLVED, memory)
        triage_question = question
        if action == FollowUpAction.CONTINUATION_NORMATIVE_RAG:
            source = memory.restore_result() if valid else None
            resolved = (
                resolver.resolve_continuation(text, memory.last_normative_question, source.domain)
                if source is not None
                else None
            )
            if resolved is None:
                # No usable state in this conversation: the message stands on its own.
                audit = replace(audit, conversation_action=FollowUpAction.NORMATIVE_RAG.value)
                state = {**state, "turn_audit": audit}
            else:
                # The policy only reaches this point when the message has no subject of its
                # own, so an elliptical message is judged with the subject it completes. A
                # message naming anything else was left as an independent question above.
                question = resolved
                triage_question = resolved
        if action == FollowUpAction.CONTINUE_CLARIFICATION:
            pending = memory.pending_clarification
            question, clarification, correlation = (
                pending.original_question,
                # The canonical level, never the free text around it.
                interpreted.clarification_text if interpreted is not None else text,
                pending.correlation_id,
            )
            triage_question = question

        # Triage the complete operation question, including a resumed pending
        # operation. This also protects pending created before gate installation.
        scope = await scope_gate.classify(triage_question)
        audit = replace(
            audit,
            nodes_visited=(*audit.nodes_visited, "scope_gate"),
            scope_gate_decision=scope.decision,
            scope_gate_status=scope.status,
            scope_gate_provider_calls=scope.provider_calls,
            scope_gate_latency_ms=scope.latency_ms,
        )
        state = {**state, "turn_audit": audit}
        if scope.decision == "OUT_OF_SCOPE":
            output = direct(state, OUT_OF_SCOPE_RESPONSE, memory)
            output["followup_action"] = FollowUpAction.OUT_OF_SCOPE
            output["turn_audit"] = replace(
                output["turn_audit"],
                conversation_action=FollowUpAction.OUT_OF_SCOPE.value,
                action_reason_code="scope_gate_out_of_scope",
                memory_preserved=True,
                pending_preserved=True,
            )
            return output

        if interpreted is not None and interpreted.persist_level:
            # Only the policy decides persistence: explicit, grounded, about the user.
            state = {
                **state,
                "conversation_memory": declare_level(
                    state, interpreted.persist_level, interpreted.persist_source
                ),
            }
            audit = replace(audit, interpreted_level_persisted=interpreted.persist_level)
            level_written = True
        if action == FollowUpAction.CONTINUE_CLARIFICATION:
            level = clarification_level(text) if interpreted is None else None
            if level in {"graduacao", "pos_graduacao"}:
                state = {
                    **state,
                    "conversation_memory": declare_level(state, level, "confirmed_clarification"),
                }
        elif action == FollowUpAction.NORMATIVE_RAG and getattr(interpreted, "query_level", None):
            # A question about a third party: their explicit level, for this query only.
            clarification = interpreted.query_level
            audit = replace(
                audit, third_party_query_level=clarification, declared_level_suppressed=True
            )
        elif action == FollowUpAction.NORMATIVE_RAG and getattr(
            interpreted, "suppress_declared_level", False
        ):
            audit = replace(audit, declared_level_suppressed=True)
        elif action == FollowUpAction.NORMATIVE_RAG and (valid or level_written):
            stored = state["conversation_memory"].declared_level
            clarification = declared_level_clarification(question, stored)
            audit = replace(audit, declared_level_used=clarification is not None)

        class OperationFacade:
            async def query(self, **kwargs):
                if kwargs["question"] != question or kwargs["correlation_id"] != correlation:
                    raise ValueError("Parent normative operation mismatch.")
                return await facade.query(
                    question=question, clarification=clarification, correlation_id=correlation
                )

        receipt = _InvocationFacade(OperationFacade())
        tool = build_normative_tool(receipt)
        error_type = None
        try:
            message = await tool.ainvoke(
                {
                    "type": "tool_call",
                    "id": str(uuid4()),
                    "name": tool.name,
                    "args": {"question": question, "correlation_id": correlation},
                },
                config,
            )
            if not isinstance(message, ToolMessage):
                raise TypeError("Expected normative tool message.")
            result = validated_result(message.artifact)
        except Exception as exc:
            error_type = type(exc).__name__
            try:
                result = validated_result(receipt.result)
                if result.correlation_id != correlation:
                    raise ValueError("Normative correlation mismatch.")
            except (TypeError, ValueError):
                result = safe_tool_error(correlation, error_type)
        if result.correlation_id != correlation:
            result = safe_tool_error(correlation, "CorrelationMismatch")
        final = gate.emit(result)
        # Result, memory and final message form one terminal node update. No raw
        # generation or ToolMessage is written as an intermediate conversation step.
        updated = update_memory(state, result, question, keep_current=level_written)
        field = {
            "ANSWER": "answer",
            "CLARIFICATION": "clarification_question",
            "ERROR": "safe_message",
        }[result.status]
        return dict(
            messages=[final],
            action=AgentAction.NORMATIVE_RAG,
            normative_result=result,
            grounded_followup_result=None,
            normative_correlation_id=str(result.correlation_id),
            conversation_memory=updated,
            turn_audit=replace(
                audit,
                action=AgentAction.NORMATIVE_RAG,
                nodes_visited=(*audit.nodes_visited, "normative_tool", "authoritative_emission"),
                correlation_id=str(result.correlation_id),
                normative_tool_called=True,
                facade_calls=receipt.calls,
                facade_called=bool(receipt.calls),
                normative_status=result.status.value,
                retrieval_strategy=result.retrieval_strategy.value,
                authoritative_emission=True,
                final_source=f"normative_result.{field}",
                tool_exception_type=error_type,
                replaced_incompatible_memory=audit.memory_status in {"STALE", "INVALID"}
                and result.status != "ERROR",
            ),
        )

    graph = StateGraph(ConversationState)
    graph.add_node("conversation_entry", entry)
    graph.add_node("conversation_turn", execute)
    graph.add_edge(START, "conversation_entry")
    if interpreter is None:
        graph.add_edge("conversation_entry", "conversation_turn")
    else:
        graph.add_node("conversation_interpretation", interpret)
        graph.add_edge("conversation_entry", "conversation_interpretation")
        graph.add_edge("conversation_interpretation", "conversation_turn")
    graph.add_edge("conversation_turn", END)
    return graph.compile(checkpointer=checkpointer, name="chatbot_ufpi_integrated_v1")
