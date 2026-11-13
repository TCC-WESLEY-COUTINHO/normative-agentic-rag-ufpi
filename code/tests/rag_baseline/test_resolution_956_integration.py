import re
import unicodedata
from pathlib import Path

import pytest

from rag_baseline.config import BaselineSettings
from rag_baseline.corpus import normalize_chunk
from rag_baseline.index import index_corpus
from rag_baseline.profiles import apply_profile
from rag_baseline.retrieve import retrieve_chunks
from rag_baseline.vector_store import ChromaVectorStore

VOCABULARY = ("mestrado", "doutorado", "creditos", "qualificacao", "dissertacao", "tese")
CODE_ROOT = Path(__file__).resolve().parents[2]


def tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return re.findall(r"[a-z]+", ascii_text)


class LocalKeywordEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(tokens(text).count(term)) for term in VOCABULARY] for text in texts]


def graduation_sentinel():
    return normalize_chunk(
        {
            "conteudo": "Conteúdo exclusivo da graduação.",
            "metadados": {
                "fonte": "Regulamento Geral da Graduação da UFPI",
                "artigo_numero": "1",
                "artigo": "Art. 1",
            },
        },
        index=0,
    )


def stale_resolution_chunk():
    return normalize_chunk(
        {
            "conteudo": "Artigo obsoleto que não pertence ao corpus atual.",
            "metadados": {
                "fonte": "Resolução CEPEX/UFPI nº 956/2025",
                "artigo_numero": "999",
                "artigo": "Art. 999",
            },
        },
        index=999,
        id_prefix="ufpi-956-2025",
    )


@pytest.mark.asyncio
async def test_full_resolution_corpus_indexes_and_retrieves_without_touching_graduation(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(CODE_ROOT)
    settings = apply_profile(BaselineSettings(_env_file=None), "resolucao-956").model_copy(
        update={"CHROMA_PERSIST_DIR": tmp_path / "chroma"}
    )
    resolution_store = ChromaVectorStore(settings.CHROMA_PERSIST_DIR, settings.CHROMA_COLLECTION)
    graduation_store = ChromaVectorStore(settings.CHROMA_PERSIST_DIR, "ufpi_graduacao_177_2012")
    graduation_store.upsert([graduation_sentinel()], [[1.0, 0.0, 0.0, 0.0, 0.0, 0.0]])
    stale_chunk = stale_resolution_chunk()
    resolution_store.upsert([stale_chunk], [[1.0, 0.0, 0.0, 0.0, 0.0, 0.0]])

    summary = await index_corpus(
        settings,
        openrouter=LocalKeywordEmbedder(),
        vector_store=resolution_store,
        rebuild=False,
    )
    results = await retrieve_chunks(
        "requisitos mestrado créditos qualificação dissertação",
        openrouter=LocalKeywordEmbedder(),
        vector_store=resolution_store,
        top_k=3,
    )

    assert summary.indexed_chunks == 62
    assert stale_chunk.id not in resolution_store.collection.get()["ids"]
    assert all(result.id.startswith("ufpi-956-2025-") for result in results)
    assert all(result.source == "Resolução CEPEX/UFPI nº 956/2025" for result in results)
    assert graduation_store.count() == 1
