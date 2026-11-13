"""Jev first; the structured LLM only for mixed or genuinely undetermined readings.

A technical failure of Jev is NOT forwarded to the LLM: that would be a silent fallback
between models. It is returned as the Jev failure it is.
"""

from dataclasses import replace

from rag_baseline.conversation_interpretation.base import ConversationInterpreter
from rag_baseline.conversation_interpretation.contracts import InterpretationOutcome

ESCALATE_INTENTS = frozenset({"mixed", "uncertain"})


class HybridInterpreter(ConversationInterpreter):
    name = "hybrid"

    def __init__(self, first: ConversationInterpreter, second: ConversationInterpreter):
        self.first, self.second = first, second

    def describe(self):
        return {
            "interpreter": self.name,
            "first": self.first.describe(),
            "second": self.second.describe(),
            "escalate_when_intent_in": sorted(ESCALATE_INTENTS),
            "escalate_on_first_failure": False,
        }

    @staticmethod
    def escalates(outcome: InterpretationOutcome) -> bool:
        return outcome.ok and outcome.interpretation.intent in ESCALATE_INTENTS

    def _combine(self, first, second=None) -> InterpretationOutcome:
        if second is None:
            return replace(first, interpreter=self.name, stages=("jev",))
        total = [first.cost_usd, second.cost_usd]
        return replace(
            second,
            interpreter=self.name,
            latency_ms=first.latency_ms + second.latency_ms,
            calls=first.calls + second.calls,
            input_tokens=first.input_tokens + second.input_tokens,
            output_tokens=first.output_tokens + second.output_tokens,
            cost_usd=None if all(c is None for c in total) else sum(c or 0.0 for c in total),
            probabilities={"jev": first.probabilities},
            adjustments=first.adjustments + second.adjustments,
            stages=("jev", f"structured_llm:{first.interpretation.intent}"),
        )

    def interpret(self, context, config=None):
        first = self.first.interpret(context, config)
        if not self.escalates(first):
            return self._combine(first)
        return self._combine(first, self.second.interpret(context, config))

    async def ainterpret(self, context, config=None):
        first = await self.first.ainterpret(context, config)
        if not self.escalates(first):
            return self._combine(first)
        return self._combine(first, await self.second.ainterpret(context, config))
