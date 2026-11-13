"""Provider-independent contracts for conversational turn interpretation.

An interpretation is a probabilistic reading of one user message. It never becomes a
fact about the student by itself: the deterministic transition policy decides what, if
anything, is resumed, persisted or executed.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

Intent = Literal["clarification", "level_declaration", "new_question", "mixed", "uncertain"]
Level = Literal["undergraduate", "postgraduate", "both", "none"]
LevelEvidence = Literal["explicit", "indirect", "hedged", "none"]
LevelSubject = Literal["self", "third_party", "generic", "unknown"]
InterpretationStatus = Literal[
    "ok",
    "provider_error",
    "timeout",
    "invalid_response",
    "inconsistent",
    "ungrounded",
]

MEMORY_LEVEL = {"undergraduate": "graduacao", "postgraduate": "pos_graduacao"}
CONTEXT_LEVEL = {"graduacao": "undergraduate", "pos_graduacao": "postgraduate"}
# Exactly the replies the closed R1 grammar already hands to the normative core.
CANONICAL_CLARIFICATION = {
    "undergraduate": "graduação",
    "postgraduate": "pós-graduação",
    "both": "ambas",
}


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ContextMessage(_Contract):
    role: Literal["user", "assistant"]
    content: StrictStr = Field(max_length=600)


class TurnContext(_Contract):
    """The same input for every interpreter: this thread only, never another one."""

    message: StrictStr = Field(min_length=1, max_length=2000)
    pending_question: StrictStr | None = None
    pending_clarification_question: StrictStr | None = None
    declared_level: Literal["undergraduate", "postgraduate"] | None = None
    last_normative_question: StrictStr | None = None
    conversation_context: tuple[ContextMessage, ...] = Field(default=(), max_length=6)
    has_pending_operation: bool = False

    @model_validator(mode="after")
    def coherent_pending(self):
        if self.has_pending_operation != (self.pending_question is not None):
            raise ValueError("has_pending_operation must match pending_question.")
        if self.pending_clarification_question is not None and self.pending_question is None:
            raise ValueError("A clarification request requires its pending question.")
        return self


class TurnInterpretation(_Contract):
    """Structured reading of one message. Fields describe the message, not the student."""

    intent: Intent
    declared_level: Level
    level_evidence: LevelEvidence
    level_subject: LevelSubject
    references_pending: bool
    has_new_question: bool
    cancels_pending: bool
    extracted_question: StrictStr | None = Field(default=None, max_length=1000)
    evidence_spans: tuple[StrictStr, ...] = Field(default=(), max_length=6)

    @model_validator(mode="after")
    def internally_consistent(self):
        problems = interpretation_contradictions(self)
        if problems:
            raise ValueError("Inconsistent interpretation: " + ", ".join(problems))
        return self


def interpretation_contradictions(value) -> list[str]:
    """Contradictions between fields; works on any object with the interpretation fields."""
    problems = []
    if (value.declared_level == "none") != (value.level_evidence == "none"):
        problems.append("level_without_evidence_kind")
    if value.intent in {"clarification", "level_declaration"}:
        if value.declared_level == "none":
            problems.append(f"{value.intent}_without_level")
        if value.has_new_question:
            problems.append(f"{value.intent}_with_new_question")
    if value.intent == "new_question" and not value.has_new_question:
        problems.append("new_question_without_question")
    if value.intent == "mixed" and not (
        value.has_new_question
        and (value.declared_level != "none" or value.cancels_pending or value.references_pending)
    ):
        problems.append("mixed_without_two_intents")
    if value.extracted_question is not None and not value.has_new_question:
        problems.append("extracted_question_without_question")
    return problems


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", (text or "").casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(plain.split())


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def grounding_violations(interpretation: TurnInterpretation, message: str) -> list[str]:
    """Extracted text must come from the message: nothing may be added to it."""
    violations = []
    folded = fold(message)
    for span in interpretation.evidence_spans:
        if not fold(span).strip() or fold(span).strip(" .,!?;:") not in folded:
            violations.append("evidence_span_not_in_message")
            break
    if interpretation.extracted_question is not None:
        words = set(_tokens(message))
        extracted = _tokens(interpretation.extracted_question)
        if not extracted or any(word not in words for word in extracted):
            violations.append("extracted_question_adds_words")
    return violations


# Level vocabulary used only to locate evidence for a level an interpreter proposed. It
# never decides intent and is not the closed R1 reply grammar.
_LEVEL_TERMS = (
    (
        r"pos[- ]?graduac\w*|pos\b|stricto sensu|lato sensu|mestrad\w*|mestrand\w*"
        r"|doutorad\w*|doutorand\w*|especializac\w*",
        "postgraduate",
    ),
    (r"graduac\w*|graduand\w*|bacharelad\w*|licenciatur\w*", "undergraduate"),
    (r"ambos|ambas|os dois|as duas", "both"),
)


def lexical_level_spans(message: str, level: str) -> tuple[str, ...]:
    """Spans of the message that name `level` (or both levels when level is 'both')."""
    folded = fold(message)
    found: list[tuple[int, int, str]] = []
    taken: list[tuple[int, int]] = []
    for pattern, kind in _LEVEL_TERMS:
        for match in re.finditer(r"\b(?:" + pattern + r")", folded):
            start, end = match.span()
            if any(start < b and a < end for a, b in taken):
                continue
            taken.append((start, end))
            found.append((start, end, kind))
    kinds = {kind for _, _, kind in found}
    if level == "both":
        wanted = (
            {"both"}
            if "both" in kinds
            else (
                {"undergraduate", "postgraduate"}
                if {"undergraduate", "postgraduate"} <= kinds
                else set()
            )
        )
    else:
        wanted = {level}
    return tuple(folded[a:b] for a, b, kind in sorted(found) if kind in wanted)


@dataclass(frozen=True)
class InterpretationOutcome:
    """Interpretation plus technical telemetry. Never contains model reasoning."""

    interpreter: str
    status: InterpretationStatus
    interpretation: TurnInterpretation | None = None
    error_type: str | None = None
    detail: str | None = None
    latency_ms: float = 0.0
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    model: str | None = None
    method: str | None = None
    probabilities: dict = field(default_factory=dict)
    adjustments: tuple[str, ...] = ()
    stages: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == "ok" and self.interpretation is not None
