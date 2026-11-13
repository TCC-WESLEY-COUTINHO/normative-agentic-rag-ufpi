"""Experimental conversational interpretation (A'' conditions); inactive by default."""

from rag_baseline.conversation_interpretation.base import ConversationInterpreter
from rag_baseline.conversation_interpretation.contracts import (
    InterpretationOutcome,
    TurnContext,
    TurnInterpretation,
)
from rag_baseline.conversation_interpretation.factory import (
    InterpreterConfig,
    build_conversation_interpreter,
)
from rag_baseline.conversation_interpretation.transition import (
    ConversationTransitionPolicy,
    TransitionDecision,
)

__all__ = [
    "ConversationInterpreter",
    "ConversationTransitionPolicy",
    "InterpretationOutcome",
    "InterpreterConfig",
    "TransitionDecision",
    "TurnContext",
    "TurnInterpretation",
    "build_conversation_interpreter",
]
