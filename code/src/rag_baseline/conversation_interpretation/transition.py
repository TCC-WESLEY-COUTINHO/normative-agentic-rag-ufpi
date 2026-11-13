"""Deterministic application of a probabilistic interpretation.

The interpreter proposes; this policy decides. Invariants enforced here, never in a
prompt:

1. no resumption without a pending operation in this thread;
2. no level stored without explicit, grounded evidence;
3. no level stored for a third party;
4. a new question is never consumed as a clarification;
5. the pending question is never silently replaced by a different one;
6. only this thread's state is read (the caller builds the context per thread);
7. an explicit new level replaces the previous one;
8. 'both' (comparison) is never stored as a personal level;
9. genuinely ambiguous replies to a pending request are asked back;
10. probabilities never certify anything: they only select or reject a reading.
"""

from dataclasses import dataclass

from rag_baseline.conversation_interpretation.contracts import (
    CANONICAL_CLARIFICATION,
    MEMORY_LEVEL,
    InterpretationOutcome,
    TurnContext,
)
from rag_baseline.conversation_policy import FollowUpAction, clarification_level

_GRAMMAR_LEVEL = {"graduacao": "undergraduate", "pos_graduacao": "postgraduate", "ambas": "both"}


def clarification_for(message: str, level: str) -> str:
    """The text handed to the core as the clarification.

    A reply the A' grammar already accepts with the same level is passed unchanged, so
    routing sees exactly what A' would. Any other reply is reduced to the canonical level:
    free text around it (course names, apologies, a second question) never reaches the
    router as if it were part of the answer.
    """
    if _GRAMMAR_LEVEL.get(clarification_level(message) or "") == level:
        return message
    return CANONICAL_CLARIFICATION[level]


# Decisions the interpreter may revise. Cancel words, greetings, assistant identity,
# calculator, grounded transforms and domain shortcuts stay structural and deterministic.
INTERPRETABLE = frozenset(
    {
        FollowUpAction.CONTINUE_CLARIFICATION,
        FollowUpAction.DECLARE_LEVEL,
        FollowUpAction.NORMATIVE_RAG,
        FollowUpAction.CONTINUATION_NORMATIVE_RAG,
    }
)
_GRAMMAR_ONLY = frozenset({FollowUpAction.CONTINUE_CLARIFICATION, FollowUpAction.DECLARE_LEVEL})

REASK_UNCLEAR_LEVEL = (
    "Não consegui identificar com segurança o nível acadêmico na sua resposta. {question} "
    "Se preferir fazer outra pergunta, envie-a completa."
)
REASK_GENERIC = "Para responder à pergunta anterior, preciso de uma informação: {question}"
ASK_QUESTION = (
    "Entendi. Qual é a sua dúvida sobre as normas acadêmicas da UFPI? Informe a pergunta completa."
)


@dataclass(frozen=True)
class TransitionDecision:
    action: FollowUpAction
    reason: str
    base_action: FollowUpAction
    clarification_text: str | None = None
    persist_level: str | None = None
    persist_source: str | None = None
    direct_message: str | None = None
    deferred_question: str | None = None
    # Grounded copy of the new question inside a mixed message (never a rewrite).
    question_override: str | None = None
    clear_pending: bool = False


class ConversationTransitionPolicy:
    def decide(
        self, base: FollowUpAction, outcome: InterpretationOutcome | None, context: TurnContext
    ) -> TransitionDecision:
        if base not in INTERPRETABLE or outcome is None:
            return TransitionDecision(base, "structural_or_not_interpreted", base)
        if not outcome.ok:
            # Safe behaviour on any technical failure: the unchanged A' decision, with
            # the failure recorded in the audit (never a second model).
            return TransitionDecision(base, f"interpreter_{outcome.status}", base)

        i = outcome.interpretation
        pending = context.has_pending_operation
        level, evidence, subject = i.declared_level, i.level_evidence, i.level_subject
        grounded_level = level != "none" and bool(i.evidence_spans)
        usable_for_resume = grounded_level and evidence in {"explicit", "indirect"}
        explicit = grounded_level and evidence == "explicit" and level in MEMORY_LEVEL

        def resume(reason, deferred=None):
            store = explicit and subject != "third_party"
            return TransitionDecision(
                FollowUpAction.CONTINUE_CLARIFICATION,
                reason,
                base,
                clarification_text=clarification_for(context.message, level),
                persist_level=MEMORY_LEVEL[level] if store else None,
                persist_source="confirmed_clarification" if store else None,
                deferred_question=deferred,
            )

        def reask(reason, unclear_level):
            template = REASK_UNCLEAR_LEVEL if unclear_level else REASK_GENERIC
            question = context.pending_clarification_question or "Qual é o nível acadêmico?"
            return TransitionDecision(
                FollowUpAction.CLARIFY_INTENT,
                reason,
                base,
                direct_message=template.format(question=question),
            )

        def as_question(reason, override=None):
            action = base if base not in _GRAMMAR_ONLY else FollowUpAction.NORMATIVE_RAG
            if override is not None:
                # The extracted question stands alone; it is not a continuation.
                action = FollowUpAction.NORMATIVE_RAG
            store = explicit and subject == "self"
            return TransitionDecision(
                action,
                reason,
                base,
                persist_level=MEMORY_LEVEL[level] if store else None,
                persist_source="explicit_declaration" if store else None,
                question_override=override,
                clear_pending=pending and i.cancels_pending,
            )

        if i.intent in {"clarification", "level_declaration"}:
            if pending:
                if usable_for_resume:
                    return resume(f"{i.intent}_resumes_pending")
                return reask(f"{i.intent}_level_not_usable", unclear_level=True)
            if explicit and subject == "self":
                return TransitionDecision(
                    FollowUpAction.DECLARE_LEVEL,
                    "self_declaration",
                    base,
                    persist_level=MEMORY_LEVEL[level],
                    persist_source="explicit_declaration",
                )
            # A level that cannot be stored, without any question to answer.
            return TransitionDecision(
                FollowUpAction.CLARIFY_INTENT,
                "declaration_not_storable",
                base,
                direct_message=ASK_QUESTION,
            )

        if i.intent == "mixed":
            if pending and i.references_pending and not i.cancels_pending:
                if usable_for_resume:
                    # The reply answers the pending request: that operation runs; the extra
                    # question is recorded, never substituted for the original.
                    return resume("mixed_resumes_pending", deferred=i.extracted_question)
                return reask("mixed_level_not_usable", unclear_level=True)
            return as_question("mixed_executes_new_question", override=i.extracted_question)

        if i.intent == "new_question":
            # A plain new question keeps the user's full text: nothing to separate.
            return as_question("new_question")

        # uncertain
        if pending and (level != "none" or base in _GRAMMAR_ONLY):
            return reask("uncertain_with_pending", unclear_level=evidence == "hedged")
        if base in _GRAMMAR_ONLY:
            return TransitionDecision(
                FollowUpAction.CLARIFY_INTENT,
                "uncertain_level_only",
                base,
                direct_message=ASK_QUESTION,
            )
        return TransitionDecision(base, "uncertain_keeps_base", base)
