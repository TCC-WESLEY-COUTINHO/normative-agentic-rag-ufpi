from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from rag_baseline.config import BaselineSettings
from rag_baseline.models import QueryResult
from rag_baseline.openrouter import OpenRouterClient, OpenRouterError
from rag_baseline.service import CorpusNotIndexedError, RagService
from rag_baseline.vector_store import ChromaVectorStore


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A pergunta não pode estar vazia.")
        return value


class HealthResponse(BaseModel):
    status: str
    indexed_chunks: int
    collection: str
    embedding_model: str
    llm_model: str
    openrouter_configured: bool


class _Runtime:
    def __init__(self, settings: BaselineSettings) -> None:
        self.settings = settings
        self._store: ChromaVectorStore | None = None
        self._service: RagService | None = None

    def store(self) -> ChromaVectorStore:
        if self._store is None:
            self._store = ChromaVectorStore(
                self.settings.CHROMA_PERSIST_DIR,
                self.settings.CHROMA_COLLECTION,
            )
        return self._store

    def service(self) -> RagService:
        if self._service is None:
            openrouter = OpenRouterClient(
                api_key=self.settings.api_key_value(),
                base_url=self.settings.OPENROUTER_BASE_URL,
                embedding_model=self.settings.EMBEDDING_MODEL,
                embedding_batch_size=self.settings.EMBEDDING_BATCH_SIZE,
                llm_model=self.settings.LLM_MODEL,
                llm_temperature=self.settings.LLM_TEMPERATURE,
                llm_max_tokens=self.settings.LLM_MAX_TOKENS,
                timeout_seconds=self.settings.OPENROUTER_TIMEOUT_SECONDS,
                app_name=self.settings.OPENROUTER_APP_NAME,
                http_referer=self.settings.OPENROUTER_HTTP_REFERER,
            )
            self._service = RagService(
                openrouter=openrouter,
                vector_store=self.store(),
                top_k=self.settings.RETRIEVAL_TOP_K,
                embedding_model=self.settings.EMBEDDING_MODEL,
                llm_model=self.settings.LLM_MODEL,
            )
        return self._service


def _openrouter_status(error: OpenRouterError) -> int:
    message = str(error)
    temporary_markers = ("OPENROUTER_API_KEY", "429", "tempo limite", "conectar")
    return 503 if any(marker in message for marker in temporary_markers) else 502


def create_app(
    settings: BaselineSettings | None = None,
    *,
    service: Any | None = None,
    vector_store: Any | None = None,
) -> FastAPI:
    current_settings = settings or BaselineSettings()
    runtime = _Runtime(current_settings)
    app = FastAPI(title="Baseline RAG — Graduação UFPI")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        store = vector_store or runtime.store()
        indexed_chunks = store.count()
        if indexed_chunks == 0:
            status = "indexing_required"
        elif not current_settings.OPENROUTER_API_KEY:
            status = "configuration_required"
        else:
            status = "ok"
        return HealthResponse(
            status=status,
            indexed_chunks=indexed_chunks,
            collection=current_settings.CHROMA_COLLECTION,
            embedding_model=current_settings.EMBEDDING_MODEL,
            llm_model=current_settings.LLM_MODEL,
            openrouter_configured=bool(current_settings.OPENROUTER_API_KEY),
        )

    @app.post("/query", response_model=QueryResult)
    async def query(payload: QueryRequest) -> QueryResult:
        rag_service = service or runtime.service()
        try:
            return await rag_service.query(payload.question)
        except CorpusNotIndexedError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except OpenRouterError as exc:
            raise HTTPException(status_code=_openrouter_status(exc), detail=str(exc)) from exc

    return app


app = create_app()
