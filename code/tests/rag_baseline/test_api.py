from fastapi.testclient import TestClient

from rag_baseline.api import create_app
from rag_baseline.config import BaselineSettings
from rag_baseline.models import QueryResult, Reference
from rag_baseline.openrouter import OpenRouterError
from rag_baseline.service import CorpusNotIndexedError


class FakeStore:
    def __init__(self, count: int) -> None:
        self.indexed_count = count

    def count(self) -> int:
        return self.indexed_count


class FakeService:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.questions: list[str] = []

    async def query(self, question: str):
        self.questions.append(question)
        if self.error:
            raise self.error
        return self.result


def settings(api_key: str | None = "configured-secret") -> BaselineSettings:
    return BaselineSettings(OPENROUTER_API_KEY=api_key, _env_file=None)


def query_result() -> QueryResult:
    return QueryResult(
        answer="Resposta.",
        references=[
            Reference(
                rank=1,
                article_number="42",
                source="Regulamento Geral da Graduação da UFPI",
                content="Conteúdo.",
                distance=0.1,
            )
        ],
        llm_model="qwen/test",
        embedding_model="embedding/test",
    )


def test_settings_load_without_api_key_and_keep_baseline_defaults() -> None:
    loaded = settings(api_key=None)

    assert loaded.OPENROUTER_API_KEY is None
    assert loaded.EMBEDDING_MODEL == "openai/text-embedding-3-small"
    assert loaded.LLM_MODEL == "qwen/qwen3-30b-a3b-instruct-2507"
    assert loaded.RETRIEVAL_TOP_K == 5
    assert str(loaded.CORPUS_PATH).replace("\\", "/") == "scripts/chunks_v2.json"


def test_empty_question_returns_422() -> None:
    app = create_app(settings(), service=FakeService(query_result()), vector_store=FakeStore(1))
    client = TestClient(app)

    response = client.post("/query", json={"question": "   "})

    assert response.status_code == 422


def test_query_returns_answer_and_deterministic_references() -> None:
    service = FakeService(query_result())
    app = create_app(settings(), service=service, vector_store=FakeStore(1))
    client = TestClient(app)

    response = client.post("/query", json={"question": "  Minha pergunta?  "})

    assert response.status_code == 200
    assert service.questions == ["Minha pergunta?"]
    assert response.json() == {
        "answer": "Resposta.",
        "references": [
            {
                "rank": 1,
                "article_number": "42",
                "chapter_number": None,
                "chapter_title": None,
                "section_number": None,
                "section_title": None,
                "subsection_number": None,
                "subsection_title": None,
                "source": "Regulamento Geral da Graduação da UFPI",
                "content": "Conteúdo.",
                "distance": 0.1,
            }
        ],
        "llm_model": "qwen/test",
        "embedding_model": "embedding/test",
    }


def test_query_without_index_returns_controlled_503() -> None:
    service = FakeService(error=CorpusNotIndexedError("Corpus ainda não indexado."))
    app = create_app(settings(), service=service, vector_store=FakeStore(0))
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/query", json={"question": "Pergunta"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Corpus ainda não indexado."}


def test_query_without_api_key_returns_controlled_503() -> None:
    service = FakeService(error=OpenRouterError("OPENROUTER_API_KEY não está configurada."))
    app = create_app(settings(api_key=None), service=service, vector_store=FakeStore(1))
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/query", json={"question": "Pergunta"})

    assert response.status_code == 503
    assert response.json() == {"detail": "OPENROUTER_API_KEY não está configurada."}


def test_upstream_failure_returns_controlled_502() -> None:
    service = FakeService(error=OpenRouterError("OpenRouter retornou HTTP 500."))
    app = create_app(settings(), service=service, vector_store=FakeStore(1))
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/query", json={"question": "Pergunta"})

    assert response.status_code == 502
    assert response.json() == {"detail": "OpenRouter retornou HTTP 500."}


def test_health_reports_index_and_never_exposes_secret() -> None:
    secret = "must-not-leak"
    app = create_app(
        settings(secret),
        service=FakeService(query_result()),
        vector_store=FakeStore(376),
    )
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "indexed_chunks": 376,
        "collection": "ufpi_graduacao_177_2012",
        "embedding_model": "openai/text-embedding-3-small",
        "llm_model": "qwen/qwen3-30b-a3b-instruct-2507",
        "openrouter_configured": True,
    }
    assert secret not in response.text


def test_health_indicates_when_indexing_is_required() -> None:
    app = create_app(settings(), service=FakeService(), vector_store=FakeStore(0))
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "indexing_required"
