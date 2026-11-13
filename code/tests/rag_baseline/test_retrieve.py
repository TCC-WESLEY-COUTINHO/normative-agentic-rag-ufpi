import pytest

from rag_baseline.retrieve import RetrievalError, retrieve_chunks


class FakeOpenRouter:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts = texts
        return [[1.0, 0.0]]


class FakeStore:
    def __init__(self, *, count: int = 1) -> None:
        self._count = count
        self.query_args = None

    def count(self) -> int:
        return self._count

    def query(self, embedding, top_k):
        self.query_args = (embedding, top_k)
        return ["resultado"]


@pytest.mark.asyncio
async def test_retrieve_chunks_embeds_only_the_question_and_queries_selected_store() -> None:
    openrouter = FakeOpenRouter()
    store = FakeStore()

    results = await retrieve_chunks(
        "Quais são os requisitos do mestrado?",
        openrouter=openrouter,
        vector_store=store,
        top_k=3,
    )

    assert openrouter.texts == ["Quais são os requisitos do mestrado?"]
    assert store.query_args == ([1.0, 0.0], 3)
    assert results == ["resultado"]


@pytest.mark.asyncio
async def test_retrieve_chunks_rejects_an_empty_collection_before_embedding() -> None:
    openrouter = FakeOpenRouter()

    with pytest.raises(RetrievalError, match="não indexado"):
        await retrieve_chunks(
            "Pergunta",
            openrouter=openrouter,
            vector_store=FakeStore(count=0),
            top_k=3,
        )

    assert openrouter.texts == []


@pytest.mark.asyncio
@pytest.mark.parametrize("question", ["", "   "])
async def test_retrieve_chunks_rejects_an_empty_question(question) -> None:
    with pytest.raises(RetrievalError, match="pergunta"):
        await retrieve_chunks(
            question,
            openrouter=FakeOpenRouter(),
            vector_store=FakeStore(),
            top_k=3,
        )


@pytest.mark.asyncio
async def test_retrieve_chunks_rejects_non_positive_top_k() -> None:
    with pytest.raises(RetrievalError, match="top_k"):
        await retrieve_chunks(
            "Pergunta",
            openrouter=FakeOpenRouter(),
            vector_store=FakeStore(),
            top_k=0,
        )
