from rag_baseline.corpus import normalize_chunk
from rag_baseline.vector_store import ChromaVectorStore


def raw_chunk(article: str, content: str) -> dict:
    return {
        "conteudo": content,
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
            "artigo_numero": article,
            "artigo": f"Art. {article}",
        },
    }


def test_upsert_is_idempotent_and_persistent(tmp_path) -> None:
    chunk = normalize_chunk(raw_chunk("1", "Primeiro artigo."), index=0)
    persist_dir = tmp_path / "chroma"
    store = ChromaVectorStore(persist_dir, "baseline_test")

    store.upsert([chunk], [[1.0, 0.0]])
    store.upsert([chunk], [[1.0, 0.0]])

    assert store.count() == 1
    reopened = ChromaVectorStore(persist_dir, "baseline_test")
    assert reopened.count() == 1


def test_query_respects_top_k_and_orders_by_cosine_distance(tmp_path) -> None:
    chunks = [
        normalize_chunk(raw_chunk("1", "Mais próximo."), index=0),
        normalize_chunk(raw_chunk("2", "Segundo resultado."), index=1),
        normalize_chunk(raw_chunk("3", "Mais distante."), index=2),
    ]
    store = ChromaVectorStore(tmp_path / "chroma", "baseline_test")
    store.upsert(chunks, [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]])

    results = store.query([1.0, 0.0], top_k=2)

    assert len(results) == 2
    assert [result.article_number for result in results] == ["1", "2"]
    assert [result.rank for result in results] == [1, 2]
    assert results[0].distance < results[1].distance


def test_query_returns_content_and_hierarchical_metadata(tmp_path) -> None:
    chunk = normalize_chunk(raw_chunk("7", "Conteúdo recuperado."), index=4)
    store = ChromaVectorStore(tmp_path / "chroma", "baseline_test")
    store.upsert([chunk], [[1.0, 0.0]])

    result = store.query([1.0, 0.0], top_k=1)[0]

    assert result.content == "Conteúdo recuperado."
    assert result.source == "Regulamento Geral da Graduação da UFPI"
    assert result.title_number == "I"
    assert result.title_name == "DISPOSIÇÕES"
    assert result.chapter_number is None
    assert result.article_number == "7"
    assert result.original_index == 4


def test_reset_removes_only_baseline_collection(tmp_path) -> None:
    persist_dir = tmp_path / "chroma"
    baseline = ChromaVectorStore(persist_dir, "baseline_test")
    other = ChromaVectorStore(persist_dir, "other_collection")
    baseline_chunk = normalize_chunk(raw_chunk("1", "Baseline."), index=0)
    other_chunk = normalize_chunk(raw_chunk("2", "Outra coleção."), index=0)
    baseline.upsert([baseline_chunk], [[1.0, 0.0]])
    other.upsert([other_chunk], [[0.0, 1.0]])

    baseline.reset()

    assert baseline.count() == 0
    assert other.count() == 1
