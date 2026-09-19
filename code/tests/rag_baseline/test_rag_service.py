import pytest

from rag_baseline.models import RetrievedChunk
from rag_baseline.service import CorpusNotIndexedError, RagService


class FakeOpenRouter:
    def __init__(self, answer: str = "Resposta baseada no contexto.") -> None:
        self.answer = answer
        self.embedded_inputs: list[list[str]] = []
        self.system_prompt = ""
        self.user_prompt = ""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.embedded_inputs.append(texts)
        return [[0.1, 0.2] for _ in texts]

    async def chat(self, *, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return self.answer


class FakeStore:
    def __init__(self, chunks: list[RetrievedChunk], count: int = 1) -> None:
        self.chunks = chunks
        self.indexed_count = count
        self.received_top_k: int | None = None
        self.received_embedding: list[float] | None = None

    def count(self) -> int:
        return self.indexed_count

    def query(self, embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        self.received_embedding = embedding
        self.received_top_k = top_k
        return self.chunks[:top_k]


def retrieved_chunk(article: str = "42", rank: int = 1) -> RetrievedChunk:
    return RetrievedChunk(
        id=f"chunk-{article}",
        content=f"Conteúdo normativo do artigo {article}.",
        source="Regulamento Geral da Graduação da UFPI",
        title_number="III",
        title_name="DO ENSINO",
        chapter_number="II",
        chapter_name="DA MATRÍCULA",
        section_number=None,
        section_name=None,
        subsection_number=None,
        subsection_name=None,
        article_number=article,
        article_label=f"Art. {article}",
        original_index=rank - 1,
        distance=0.1 * rank,
        rank=rank,
    )


@pytest.mark.asyncio
async def test_service_uses_retrieved_chunks_as_llm_context_and_respects_top_k() -> None:
    chunks = [retrieved_chunk("42", 1), retrieved_chunk("43", 2)]
    openrouter = FakeOpenRouter()
    store = FakeStore(chunks)
    service = RagService(
        openrouter=openrouter,
        vector_store=store,
        top_k=2,
        embedding_model="openai/text-embedding-3-small",
        llm_model="qwen/test",
    )

    result = await service.query("Como funciona a matrícula?")

    assert openrouter.embedded_inputs == [["Como funciona a matrícula?"]]
    assert store.received_embedding == [0.1, 0.2]
    assert store.received_top_k == 2
    assert "Art. 42" in openrouter.user_prompt
    assert "Conteúdo normativo do artigo 42." in openrouter.user_prompt
    assert "Como funciona a matrícula?" in openrouter.user_prompt
    assert "somente" in openrouter.system_prompt.lower()
    assert result.answer == "Resposta baseada no contexto."


@pytest.mark.asyncio
async def test_references_come_from_retrieval_not_from_llm_text() -> None:
    openrouter = FakeOpenRouter(answer="A resposta cita incorretamente o Art. 999.")
    store = FakeStore([retrieved_chunk("42", 1)])
    service = RagService(
        openrouter=openrouter,
        vector_store=store,
        top_k=5,
        embedding_model="embedding-model",
        llm_model="llm-model",
    )

    result = await service.query("Pergunta")

    assert result.references[0].article_number == "42"
    assert result.references[0].content == "Conteúdo normativo do artigo 42."
    assert result.references[0].rank == 1
    assert result.embedding_model == "embedding-model"
    assert result.llm_model == "llm-model"


@pytest.mark.asyncio
async def test_service_fails_cleanly_when_corpus_is_not_indexed() -> None:
    openrouter = FakeOpenRouter()
    service = RagService(
        openrouter=openrouter,
        vector_store=FakeStore([], count=0),
        top_k=5,
        embedding_model="embedding-model",
        llm_model="llm-model",
    )

    with pytest.raises(CorpusNotIndexedError, match="Corpus ainda não indexado"):
        await service.query("Pergunta")

    assert openrouter.embedded_inputs == []
