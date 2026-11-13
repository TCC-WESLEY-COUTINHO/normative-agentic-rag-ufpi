"""Versioned normative delivery contract, independent of conversation transports.

ANSWER carries the final core output, including a possible conservative V2 fallback.
Consumers must deliver it intact rather than replace it with a free-form synthesis.
Default serialization is public. Only to_persistence() includes private generation
audit; that envelope must never be used as a prompt or public API response.
"""

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator

from rag_baseline.grounding import TemporalGroundingContext
from rag_baseline.output_contracts import (
    AllowedTemporalFacts,
    GenerationAudit,
    NormativeReference,
)
from rag_baseline.router import Scope
from rag_baseline.versioning import TemporalIntent


class ToolStatus(StrEnum):
    ANSWER = "ANSWER"
    CLARIFICATION = "CLARIFICATION"
    ERROR = "ERROR"


class RetrievalStrategy(StrEnum):
    DENSE_VECTOR = "dense_vector"
    METADATA_EXACT = "metadata_exact"
    VECTOR_FILTERED = "vector_filtered"


class ToolErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    PROVIDER_ERROR = "provider_error"
    INDEX_UNAVAILABLE = "index_unavailable"
    ROUTER_ERROR = "router_error"
    NO_ELIGIBLE_CONTEXT = "no_eligible_context"
    CLARIFICATION_UNRESOLVED = "clarification_unresolved"
    INVALID_CORE_RESULT = "invalid_core_result"
    INTERNAL_ERROR = "internal_error"


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NormativeToolAudit(_Contract):
    """Private diagnostics; preserves the three excluded QueryResult fields."""

    response_kind: Literal["generated", "clarification"] | None = None
    generation_attempts: int | None = Field(default=None, ge=0)
    output_audit: GenerationAudit | None = None
    exception_type: str | None = None
    retrieval_audit: dict | None = None
    abstention_reason: str | None = None


class NormativeToolResult(_Contract):
    contract_version: Literal["1"]
    core_version: Literal["structured_output_v2"]
    status: ToolStatus
    answer: StrictStr | None = None
    references: list[NormativeReference] = Field(default_factory=list)
    temporal_provenance: TemporalGroundingContext | None = None
    temporal_status_text: StrictStr | None = None
    allowed_temporal_facts: AllowedTemporalFacts | None = None
    core_status: Literal["accepted", "regenerated", "fallback", "abstained"] | None = None
    domain: Scope | None = None
    retrieval_strategy: RetrievalStrategy
    needs_clarification: bool = False
    clarification_question: StrictStr | None = None
    correlation_id: UUID
    error_code: ToolErrorCode | None = None
    safe_message: StrictStr | None = None
    internal_audit: NormativeToolAudit | None = Field(default=None, exclude=True, repr=False)

    @field_validator("temporal_provenance")
    @classmethod
    def public_provenance_fields(cls, value):
        if value is not None:
            # Grounding's legacy dictionaries are projected from these exact fields.
            # Reject extensions rather than silently carrying internal prompt data.
            allowed = set(TemporalIntent.model_fields) - {"mode"}
            if set(value.requested_time_context) - allowed:
                raise ValueError("Unknown requested temporal context fields.")
            TemporalIntent.model_validate(
                {"mode": value.temporal_intent, **value.requested_time_context}, strict=True
            )
            for state in value.evidence_states:
                if state.relation_source is not None and set(state.relation_source) - {
                    "source",
                    "article",
                }:
                    raise ValueError("Unknown temporal relation source fields.")
        return value

    @model_validator(mode="after")
    def consistent_status(self):
        if self.status == ToolStatus.ANSWER and self.core_status == "abstained":
            # A deliberate decision not to answer: there is no evidence to expose.
            if not (self.answer and self.answer.strip() and self.domain):
                raise ValueError("A deliberate abstention requires its message and domain.")
            if (
                self.references
                or self.temporal_provenance is not None
                or self.temporal_status_text is not None
                or self.allowed_temporal_facts is not None
            ):
                raise ValueError("A deliberate abstention carries no normative output.")
            if self.needs_clarification or self.clarification_question is not None:
                raise ValueError("ANSWER cannot request clarification.")
            if self.error_code is not None or self.safe_message is not None:
                raise ValueError("ANSWER cannot carry an error.")
        elif self.status == ToolStatus.ANSWER:
            if not (
                self.answer
                and self.answer.strip()
                and self.references
                and self.temporal_provenance
                and self.temporal_provenance.evidence_states
                and self.temporal_status_text
                and self.allowed_temporal_facts is not None
                and self.core_status
                and self.domain
            ):
                raise ValueError("ANSWER requires final structured normative output.")
            if self.needs_clarification or self.clarification_question is not None:
                raise ValueError("ANSWER cannot request clarification.")
            if self.error_code is not None or self.safe_message is not None:
                raise ValueError("ANSWER cannot carry an error.")
        else:
            if (
                self.answer is not None
                or self.references
                or self.temporal_provenance is not None
                or self.temporal_status_text is not None
                or self.allowed_temporal_facts is not None
                or self.core_status is not None
            ):
                raise ValueError("Only ANSWER carries normative output.")
            if self.status == ToolStatus.CLARIFICATION:
                if not (
                    self.needs_clarification
                    and self.clarification_question
                    and self.clarification_question.strip()
                    and self.domain is None
                ):
                    raise ValueError("CLARIFICATION requires an unresolved domain and question.")
                if self.error_code is not None or self.safe_message is not None:
                    raise ValueError("CLARIFICATION cannot carry an error.")
            elif (
                self.needs_clarification
                or self.clarification_question is not None
                or self.error_code is None
                or not self.safe_message
                or not self.safe_message.strip()
            ):
                raise ValueError("ERROR requires a code and safe message, without clarification.")
        return self

    def to_persistence(self) -> dict:
        """Explicit private envelope; public dump/json always omit internal_audit."""
        return _PersistenceRecord(
            persistence_version="1", result=self, internal_audit=self.internal_audit
        ).model_dump(mode="json")

    @classmethod
    def from_persistence(cls, payload: dict) -> "NormativeToolResult":
        record = _PersistenceRecord.model_validate(payload)
        return cls.model_validate(
            {**record.result.model_dump(), "internal_audit": record.internal_audit}
        )


class _PersistenceRecord(_Contract):
    persistence_version: Literal["1"]
    result: NormativeToolResult
    internal_audit: NormativeToolAudit | None
