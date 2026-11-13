"""The closed A' grammar (R1/R2) expressed through the common interpreter contract."""

from rag_baseline.conversation_interpretation.base import ConversationInterpreter, finalize
from rag_baseline.conversation_interpretation.contracts import TurnContext
from rag_baseline.conversation_policy import clarification_level

_LEVEL = {"graduacao": "undergraduate", "pos_graduacao": "postgraduate", "ambas": "both"}


class RuleBasedInterpreter(ConversationInterpreter):
    """No provider call. Mirrors `clarification_level`, which stays unchanged."""

    name = "rules"

    def _read(self, context: TurnContext) -> dict:
        level = _LEVEL.get(clarification_level(context.message) or "")
        span = (context.message.strip(),)
        if context.has_pending_operation and level:
            return dict(
                intent="clarification",
                declared_level=level,
                level_evidence="explicit",
                level_subject="unknown",
                references_pending=True,
                has_new_question=False,
                cancels_pending=False,
                evidence_spans=span,
            )
        if (
            not context.has_pending_operation
            and level in {"undergraduate", "postgraduate"}
            and "?" not in context.message
        ):
            return dict(
                intent="level_declaration",
                declared_level=level,
                level_evidence="explicit",
                level_subject="self",
                references_pending=False,
                has_new_question=False,
                cancels_pending=False,
                evidence_spans=span,
            )
        return dict(
            intent="new_question",
            declared_level="none",
            level_evidence="none",
            level_subject="unknown",
            references_pending=False,
            has_new_question=True,
            cancels_pending=False,
        )

    def interpret(self, context, config=None):
        return finalize(self.name, self._read(context), context, method="closed_grammar")

    async def ainterpret(self, context, config=None):
        return self.interpret(context, config)

    def describe(self):
        return {"interpreter": self.name, "method": "closed_grammar_r1_r2", "provider": None}
