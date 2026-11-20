"""Single-query API for the terminal; no Jev interpreter or conversation memory.

The web prototype uses service.service through deploy/backend/prototype_launcher.py.
"""

from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from rag_baseline.config import BaselineSettings
from rag_baseline.models import QueryResult
from rag_baseline.openrouter import OpenRouterClient, OpenRouterError
from rag_baseline.profiles import apply_profile
from rag_baseline.prompts import V2_SYSTEM_PROMPT
from rag_baseline.service import CorpusNotIndexedError, RagService
from rag_baseline.vector_store import ChromaVectorStore


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    sector: Literal["graduacao", "pos_graduacao", "ambos", "automatico"] = "ambos"
    clarification: str | None = Field(default=None, min_length=1, max_length=1000)
    version_filter: bool = True

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
        self._agentic = None

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
                system_prompt=V2_SYSTEM_PROMPT,
                generation_mode=self.settings.GENERATION_MODE,
            )
        return self._service

    def agentic(self):
        if self._agentic is None:
            from rag_baseline.agentic import AgenticRagService
            from rag_baseline.router import NormativeRouter
            from rag_baseline.versioning import NormativeRegistry, VersionFilter

            service = self.service()
            self._agentic = AgenticRagService(
                service,
                NormativeRouter(service.openrouter, model=self.settings.ROUTER_MODEL),
                VersionFilter(NormativeRegistry.load()),
                routing_mode=self.settings.ROUTING_MODE,
                probe_top_k=self.settings.ROUTER_PROBE_TOP_K,
                distribution_threshold=self.settings.ROUTER_DISTRIBUTION_THRESHOLD,
            )
        return self._agentic


def resolve_settings(settings: BaselineSettings) -> BaselineSettings:
    """Apply the configured corpus profile; the default is the evaluated corpus."""
    return apply_profile(settings, settings.CORPUS_PROFILE)


def _openrouter_status(error: OpenRouterError) -> int:
    message = str(error)
    temporary_markers = ("OPENROUTER_API_KEY", "429", "tempo limite", "conectar")
    return 503 if any(marker in message for marker in temporary_markers) else 502


def create_app(
    settings: BaselineSettings | None = None,
    *,
    service: Any | None = None,
    vector_store: Any | None = None,
    agentic_service: Any | None = None,
) -> FastAPI:
    current_settings = settings or resolve_settings(BaselineSettings())
    runtime = _Runtime(current_settings)
    app = FastAPI(title="Baseline RAG — Graduação e Pós-graduação UFPI")

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
        try:
            if payload.sector == "automatico":
                agentic = agentic_service or runtime.agentic()
                return await agentic.query(
                    payload.question,
                    clarification=payload.clarification,
                    use_version_filter=payload.version_filter,
                )
            if agentic_service is not None or service is None or isinstance(service, RagService):
                if agentic_service is not None:
                    agentic = agentic_service
                elif service is not None:
                    from rag_baseline.agentic import AgenticRagService
                    from rag_baseline.router import NormativeRouter
                    from rag_baseline.versioning import NormativeRegistry, VersionFilter

                    agentic = AgenticRagService(
                        service,
                        NormativeRouter(service.openrouter),
                        VersionFilter(NormativeRegistry.load()),
                    )
                else:
                    agentic = runtime.agentic()
                return await agentic.query(
                    payload.question,
                    scope="ambas" if payload.sector == "ambos" else payload.sector,
                    clarification=payload.clarification,
                    use_version_filter=payload.version_filter,
                )
            rag_service = service or runtime.service()
            if payload.sector == "ambos":
                return await rag_service.query(payload.question)
            return await rag_service.query(payload.question, sector=payload.sector)
        except CorpusNotIndexedError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except OpenRouterError as exc:
            raise HTTPException(status_code=_openrouter_status(exc), detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return app


app = create_app()
