from pydantic import BaseModel, ConfigDict


class CorpusChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    content: str
    source: str
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
    content: str
    distance: float


class QueryResult(BaseModel):
    answer: str
    references: list[Reference]
    llm_model: str
    embedding_model: str
