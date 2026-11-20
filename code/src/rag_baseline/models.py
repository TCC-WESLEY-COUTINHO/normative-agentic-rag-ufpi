from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from rag_baseline.output_contracts import GenerationAudit, NormativeOutput
from rag_baseline.scope import Sector


class CorpusChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    content: str
    source: str
    sector: Sector | None = None
    norm_id: str | None = None
    normative_status: str | None = None
    title_number: str | None = None
    title_name: str | None = None
    chapter_number: str | None = None
    chapter_name: str | None = None
    section_number: str | None = None
    section_name: str | None = None
    subsection_number: str | None = None
    subsection_name: str | None = None
    article_number: str
    article_label: str
    original_index: int


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    content: str
    source: str
    sector: Sector | None = None
    norm_id: str | None = None
    normative_status: str | None = None
    title_number: str | None = None
    title_name: str | None = None
    chapter_number: str | None = None
    chapter_name: str | None = None
    section_number: str | None = None
    section_name: str | None = None
    subsection_number: str | None = None
    subsection_name: str | None = None
    article_number: str
    article_label: str
    original_index: int
    distance: float | None
    rank: int


class Reference(BaseModel):
    rank: int
    article_number: str
    chapter_number: str | None = None
    chapter_title: str | None = None
    section_number: str | None = None
    section_title: str | None = None
    subsection_number: str | None = None
    subsection_title: str | None = None
    source: str
    sector: Sector | None = None
    content: str
    distance: float | None

    @model_serializer(mode="wrap")
    def serialize_reference(self, handler):
        result = handler(self)
        if self.sector is None:
            result.pop("sector", None)
        return result


class QueryResult(BaseModel):
    answer: str
    references: list[Reference]
    llm_model: str
    embedding_model: str
    route: dict | None = None
    needs_clarification: bool | None = None
    clarification_question: str | None = None
    selected_scope: str | None = None
    version_filter: dict | None = None
    routing: dict | None = None
    error: str | None = None
    response_kind: Literal["generated", "clarification"] = Field(default="generated", exclude=True)
    generation_attempts: int = Field(default=1, exclude=True)
    normative_output: NormativeOutput | None = None
    output_audit: GenerationAudit | None = Field(default=None, exclude=True)
    citation_audit: dict | None = None
    effective_generation_mode: Literal["free_text_v2", "cited_v3"] | None = None
    generation_fallback_reason: str | None = None

    @model_serializer(mode="wrap")
    def serialize_result(self, handler):
        result = handler(self)
        for key in ("effective_generation_mode", "generation_fallback_reason"):
            if getattr(self, key) is None:
                result.pop(key, None)
        if self.citation_audit is None:
            result.pop("citation_audit", None)
        if self.normative_output is None:
            result.pop("normative_output", None)
        if self.routing is None:
            result.pop("routing", None)
        if self.route is None:
            result.pop("route", None)
        if self.route is None and self.version_filter is None:
            for key in (
                "route",
                "needs_clarification",
                "clarification_question",
                "selected_scope",
                "version_filter",
                "error",
            ):
                if getattr(self, key) is None:
                    result.pop(key, None)
        return result
