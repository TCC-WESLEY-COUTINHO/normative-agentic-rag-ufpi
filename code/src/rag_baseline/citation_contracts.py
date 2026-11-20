"""Strict claims and audit records preserve the link to literal evidence."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SIDE_PATTERN = r"^(?:graduacao|pos_graduacao|ufpi-\d+-\d{4})$"


class CitationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Support(CitationModel):
    span_id: str
    quote: str


class Claim(CitationModel):
    text: str
    role: Literal["conclusion", "condition", "exception", "deadline", "procedure", "context"]
    group: int
    side: str | None
    support: list[Support]


class CitedAnswer(CitationModel):
    # Field order is generation order under constrained decoding: claims are written from
    # the evidence before the answer is classified, not justified after a classification.
    claims: list[Claim]
    answer_type: Literal["answer", "insufficient", "needs_user_fact"]
    missing_user_fact: str | None


def cited_answer_schema(
    span_ids: list[str] | None = None, answer_types: list[str] | None = None
) -> dict:
    """Strict schema; optional enums let constrained decoding exclude invalid addresses."""
    schema = CitedAnswer.model_json_schema()
    for variant in schema["$defs"]["Claim"]["properties"]["side"]["anyOf"]:
        if variant.get("type") == "string":
            variant["pattern"] = SIDE_PATTERN
    if span_ids:
        schema["$defs"]["Support"]["properties"]["span_id"]["enum"] = sorted(set(span_ids))
    if answer_types:
        schema["properties"]["answer_type"]["enum"] = list(answer_types)
    return schema


class ClaimVerdict(CitationModel):
    index: int
    status: Literal["supported", "rejected"]
    codes: list[str]
    span_ids: list[str]


class CitationAudit(CitationModel):
    raw_answer: dict | None = None
    raw_response: str | None = None
    first_verdicts: list[ClaimVerdict] = Field(default_factory=list)
    repair: dict | None = None
    omitted_claims: list[dict] = Field(default_factory=list)
    snapped_quotes: list[dict] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    guard_violations: list[dict] = Field(default_factory=list)
    approved_claims: list[dict] = Field(default_factory=list)
    disposition_codes: list[str] = Field(default_factory=list)
    action: Literal[
        "accepted", "repaired", "partial", "fallback", "insufficient", "needs_user_fact"
    ] = "fallback"
    llm_calls: int = 0
    structured_output_error: str | None = None
