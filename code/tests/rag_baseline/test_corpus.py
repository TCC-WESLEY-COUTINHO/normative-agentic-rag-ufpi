import json

import pytest

from rag_baseline.corpus import CorpusError, build_embedding_text, load_corpus, normalize_chunk


def sample_chunk() -> dict:
    return {
        "conteudo": "Art. 42. Conteudo normativo.",
        "metadados": {
            "fonte": "Regulamento Geral da Graduacao da UFPI",
            "titulo_numero": "III",
            "titulo_nome": "DO ENSINO",
            "capitulo_numero": "II",
            "capitulo_nome": "DA MATRICULA",
            "secao_numero": "I",
            "secao_nome": "DISPOSICOES GERAIS",
            "subsecao_numero": "",
            "subsecao_nome": "",
            "artigo_numero": "42",
            "artigo": "Art. 42",
        },
    }


def test_loader_normalizes_chunk_and_preserves_hierarchy(tmp_path) -> None:
    corpus_path = tmp_path / "chunks.json"
    corpus_path.write_text(json.dumps([sample_chunk()]), encoding="utf-8")

    chunks = load_corpus(corpus_path)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.content == "Art. 42. Conteudo normativo."
    assert chunk.source == "Regulamento Geral da Graduacao da UFPI"
    assert chunk.title_number == "III"
    assert chunk.title_name == "DO ENSINO"
    assert chunk.chapter_number == "II"
    assert chunk.chapter_name == "DA MATRICULA"
    assert chunk.section_number == "I"
    assert chunk.section_name == "DISPOSICOES GERAIS"
    assert chunk.subsection_number is None
    assert chunk.article_number == "42"
    assert chunk.original_index == 0


def test_chunk_id_is_deterministic() -> None:
    first = normalize_chunk(sample_chunk(), index=7)
    second = normalize_chunk(sample_chunk(), index=7)

    assert first.id == "ufpi-177-2012-art-42-idx-000007"
    assert second.id == first.id


def test_loader_preserves_original_order(tmp_path) -> None:
    second = sample_chunk()
    second["metadados"] = {**second["metadados"], "artigo_numero": "43", "artigo": "Art. 43"}
    corpus_path = tmp_path / "chunks.json"
    corpus_path.write_text(json.dumps([sample_chunk(), second]), encoding="utf-8")

    chunks = load_corpus(corpus_path)

    assert [chunk.article_number for chunk in chunks] == ["42", "43"]
    assert [chunk.original_index for chunk in chunks] == [0, 1]


def test_embedding_text_includes_available_structural_context() -> None:
    chunk = normalize_chunk(sample_chunk(), index=0)

    text = build_embedding_text(chunk)

    assert "Norma: Resolução nº 177/2012 CEPEX/UFPI" in text
    assert "Título III: DO ENSINO" in text
    assert "Capítulo II: DA MATRICULA" in text
    assert "Seção I: DISPOSICOES GERAIS" in text
    assert "Artigo: Art. 42" in text
    assert "Conteúdo:\nArt. 42. Conteudo normativo." in text


def test_embedding_text_omits_missing_fields_without_rendering_none() -> None:
    raw = sample_chunk()
    raw["metadados"] = {
        **raw["metadados"],
        "capitulo_numero": "",
        "capitulo_nome": "",
        "secao_numero": "",
        "secao_nome": "",
    }
    chunk = normalize_chunk(raw, index=0)

    text = build_embedding_text(chunk)

    assert "Capítulo" not in text
    assert "Seção" not in text
    assert "None" not in text


def test_loader_fails_clearly_when_file_is_missing(tmp_path) -> None:
    with pytest.raises(CorpusError, match="não encontrado"):
        load_corpus(tmp_path / "missing.json")


def test_loader_fails_clearly_when_corpus_is_empty(tmp_path) -> None:
    corpus_path = tmp_path / "chunks.json"
    corpus_path.write_text("[]", encoding="utf-8")

    with pytest.raises(CorpusError, match="vazio"):
        load_corpus(corpus_path)


def test_loader_rejects_invalid_root_format(tmp_path) -> None:
    corpus_path = tmp_path / "chunks.json"
    corpus_path.write_text('{"conteudo": "nao e uma lista"}', encoding="utf-8")

    with pytest.raises(CorpusError, match="lista"):
        load_corpus(corpus_path)
