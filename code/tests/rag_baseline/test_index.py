import json

import pytest

from rag_baseline.config import BaselineSettings
from rag_baseline.index import IndexingError, index_corpus, main


def write_fixture(path) -> None:
    chunks = [
        {
            "conteudo": "Conteúdo do artigo 1.",
            "metadados": {
                "fonte": "Regulamento Geral da Graduação da UFPI",
                "titulo_numero": "I",
                "titulo_nome": "DISPOSIÇÕES",
                "capitulo_numero": "",
                "capitulo_nome": "",
                "secao_numero": "",
                "secao_nome": "",
                "subsecao_numero": "",
                "subsecao_nome": "",
                "artigo_numero": "1",
                "artigo": "Art. 1",
            },
        },
        {
            "conteudo": "Conteúdo do artigo 2.",
            "metadados": {
                "fonte": "Regulamento Geral da Graduação da UFPI",
                "titulo_numero": "I",
                "titulo_nome": "DISPOSIÇÕES",
                "capitulo_numero": "",
                "capitulo_nome": "",
                "secao_numero": "",
                "secao_nome": "",
                "subsecao_numero": "",
                "subsecao_nome": "",
                "artigo_numero": "2",
                "artigo": "Art. 2",
            },
        },
    ]
    path.write_text(json.dumps(chunks), encoding="utf-8")


class FakeOpenRouter:
    def __init__(self, events: list[str] | None = None) -> None:
        self.texts: list[str] = []
        self.events = events

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts = texts
        if self.events is not None:
            self.events.append("embed")
        return [[float(index), 1.0] for index, _ in enumerate(texts)]


class FakeStore:
    def __init__(self, events: list[str] | None = None, count_offset: int = 0) -> None:
        self.events = events
        self.count_offset = count_offset
        self.chunks = []
        self.embeddings = []

    def reset(self) -> None:
        if self.events is not None:
            self.events.append("reset")
        self.chunks = []

    def upsert(self, chunks, embeddings) -> None:
        if self.events is not None:
            self.events.append("upsert")
        self.chunks = chunks
        self.embeddings = embeddings

    def count(self) -> int:
        return len(self.chunks) + self.count_offset


def make_settings(corpus_path, api_key: str | None = "test-key") -> BaselineSettings:
    return BaselineSettings(
        OPENROUTER_API_KEY=api_key,
        CORPUS_PATH=corpus_path,
        CHROMA_COLLECTION="baseline_test",
        CHROMA_PERSIST_DIR=corpus_path.parent / "chroma",
        _env_file=None,
    )


@pytest.mark.asyncio
async def test_index_corpus_embeds_structural_text_and_verifies_count(tmp_path) -> None:
    corpus_path = tmp_path / "chunks.json"
    write_fixture(corpus_path)
    openrouter = FakeOpenRouter()
    store = FakeStore()

    summary = await index_corpus(
        make_settings(corpus_path),
        openrouter=openrouter,
        vector_store=store,
        rebuild=False,
    )

    assert len(openrouter.texts) == 2
    assert "Norma: Resolução nº 177/2012 CEPEX/UFPI" in openrouter.texts[0]
    assert "Artigo: Art. 1" in openrouter.texts[0]
    assert len(store.embeddings) == 2
    assert summary.loaded_chunks == 2
    assert summary.indexed_chunks == 2
    assert summary.collection == "baseline_test"


@pytest.mark.asyncio
async def test_rebuild_generates_embeddings_before_resetting_collection(tmp_path) -> None:
    corpus_path = tmp_path / "chunks.json"
    write_fixture(corpus_path)
    events: list[str] = []

    await index_corpus(
        make_settings(corpus_path),
        openrouter=FakeOpenRouter(events),
        vector_store=FakeStore(events),
        rebuild=True,
    )

    assert events == ["embed", "reset", "upsert"]


@pytest.mark.asyncio
async def test_index_fails_when_collection_count_differs_from_corpus(tmp_path) -> None:
    corpus_path = tmp_path / "chunks.json"
    write_fixture(corpus_path)

    with pytest.raises(IndexingError, match="contagem"):
        await index_corpus(
            make_settings(corpus_path),
            openrouter=FakeOpenRouter(),
            vector_store=FakeStore(count_offset=-1),
            rebuild=False,
        )


def test_main_without_api_key_fails_cleanly(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    exit_code = main([])

    assert exit_code == 1
    assert "OPENROUTER_API_KEY" in capsys.readouterr().err
