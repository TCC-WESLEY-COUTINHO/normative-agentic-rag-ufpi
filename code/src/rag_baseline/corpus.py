import json
import re
from pathlib import Path
from typing import Any

from rag_baseline.models import CorpusChunk

NORM_NAME = "Resolução nº 177/2012 CEPEX/UFPI"


class CorpusError(ValueError):
    pass


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_chunk(raw: Any, index: int) -> CorpusChunk:
    if not isinstance(raw, dict):
        raise CorpusError(f"Chunk na posição {index} deve ser um objeto.")

    content = _optional_text(raw.get("conteudo"))
    metadata = raw.get("metadados")
    if not content:
        raise CorpusError(f"Chunk na posição {index} não possui conteúdo.")
    if not isinstance(metadata, dict):
        raise CorpusError(f"Chunk na posição {index} não possui metadados válidos.")

    article_number = _optional_text(metadata.get("artigo_numero"))
    source = _optional_text(metadata.get("fonte"))
    if not article_number or not source:
        raise CorpusError(f"Chunk na posição {index} não possui fonte ou número do artigo.")

    article_slug = re.sub(r"[^0-9A-Za-z]+", "-", article_number).strip("-")
    chunk_id = f"ufpi-177-2012-art-{article_slug}-idx-{index:06d}"

    return CorpusChunk(
        id=chunk_id,
        content=content,
        source=source,
        title_number=_optional_text(metadata.get("titulo_numero")),
        title_name=_optional_text(metadata.get("titulo_nome")),
        chapter_number=_optional_text(metadata.get("capitulo_numero")),
        chapter_name=_optional_text(metadata.get("capitulo_nome")),
        section_number=_optional_text(metadata.get("secao_numero")),
        section_name=_optional_text(metadata.get("secao_nome")),
        subsection_number=_optional_text(metadata.get("subsecao_numero")),
        subsection_name=_optional_text(metadata.get("subsecao_nome")),
        article_number=article_number,
        article_label=_optional_text(metadata.get("artigo")) or f"Art. {article_number}",
        original_index=index,
    )


def load_corpus(path: str | Path) -> list[CorpusChunk]:
    corpus_path = Path(path)
    if not corpus_path.is_file():
        raise CorpusError(f"Arquivo do corpus não encontrado: {corpus_path}")

    try:
        raw_corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusError(f"Não foi possível carregar o corpus: {exc}") from exc

    if not isinstance(raw_corpus, list):
        raise CorpusError("O corpus deve ser uma lista JSON.")
    if not raw_corpus:
        raise CorpusError("O corpus está vazio.")

    return [normalize_chunk(raw, index) for index, raw in enumerate(raw_corpus)]


def _hierarchy_line(label: str, number: str | None, name: str | None) -> str | None:
    if not number and not name:
        return None
    prefix = f"{label} {number}" if number else label
    return f"{prefix}: {name}" if name else prefix


def build_embedding_text(chunk: CorpusChunk) -> str:
    lines = [f"Norma: {NORM_NAME}"]
    for line in (
        _hierarchy_line("Título", chunk.title_number, chunk.title_name),
        _hierarchy_line("Capítulo", chunk.chapter_number, chunk.chapter_name),
        _hierarchy_line("Seção", chunk.section_number, chunk.section_name),
        _hierarchy_line("Subseção", chunk.subsection_number, chunk.subsection_name),
    ):
        if line:
            lines.append(line)
    lines.extend((f"Artigo: {chunk.article_label}", f"Conteúdo:\n{chunk.content}"))
    return "\n".join(lines)
