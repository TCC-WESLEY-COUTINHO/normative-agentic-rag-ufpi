from pydantic import BaseModel, ConfigDict, model_serializer

from rag_baseline.scope import Sector


class CorpusChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    content: str
    source: str
    sector: Sector | None = None
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
    distance: float
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
    distance: float

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
