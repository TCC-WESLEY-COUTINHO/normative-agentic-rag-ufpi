"""Small serializable presentation and audit contracts, independent of retrieval."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NormativeReference(OutputModel):
    """Final eligible context reference; not per-claim support attribution.

    evidence_text is the exact selected chunk text, projected without model authorship.
    Optional for compatibility with earlier persisted/public reference records.
    """

    chunk_id: str
    norm_id: str
    source: str
    article: str | None
    validated_subdivision: str | None = None
    display_text: str
    temporal_role: Literal["historical", "posterior", "eligible"]
    evidence_text: StrictStr | None = None


class TemporalFact(OutputModel):
    kind: Literal[
        "HISTORICAL_CONTEXT",
        "REVOKED_BY",
        "AMENDED_BY",
        "STATUS_UNKNOWN",
        "CURRENT_CONTEXT",
        "COMPARISON_ROLE",
    ]
    norm_id: str | None = None
    target_norm: str | None = None
    role: Literal["historical", "posterior", "eligible"] | None = None


class AllowedTemporalFacts(OutputModel):
    items: list[TemporalFact]


class GuardViolation(OutputModel):
    code: str
    start: int
    end: int
    excerpt: str


class AllowedContentLocator(OutputModel):
    norm_id: str
    article: str
    subdivision_type: Literal["paragraph", "inciso", "alinea", "caput"] | None = None
    subdivision_value: str | None = None
    source: Literal[
        "query_explicit", "amendment_target", "normative_relation", "validated_evidence"
    ]
    authorization_reason: str


class GenerationAudit(OutputModel):
    raw_answer: str
    guard_violations: list[GuardViolation]
    regenerated_answer: str | None = None
    regeneration_error: str | None = None
    second_guard_violations: list[GuardViolation] = []
    final_answer: str
    guard_action: Literal["accepted", "regenerated", "fallback"]
    allowed_content_locators: list[AllowedContentLocator] = []
    guard_version: str = "5"


class NormativeOutput(OutputModel):
    references: list[NormativeReference]
    allowed_temporal_facts: AllowedTemporalFacts
    temporal_status_text: str
    temporal_provenance: dict
    status: Literal["accepted", "regenerated", "fallback"]
