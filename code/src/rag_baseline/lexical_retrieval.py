"""Query-time lexical ranking over the indexed documents. No index or embedding changes."""

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

_STOPWORDS = """a o as os um uma uns umas de do da dos das em no na nos nas por pelo pela pelos pelas
para com sem que se e ou ao aos como qual quais quando onde quem quanto quantos quantas ser sao era
foi ter tem tinha ha meu minha meus minhas eu voce seu sua seus suas isso esse essa esses essas este
esta estes estas aquele aquela mais menos muito nao sim posso pode podem preciso precisa devo deve
ufpi resolucao resolucoes norma normas regulamento artigo artigos art graduacao pos mestrado doutorado
stricto sensu segundo conforme explique explicar detalhadamente detalhe resumidamente favor sobre
caso depois antes agora hoje atual atualmente vigente regra regras faco fazer funciona continuidade
pergunta entre cada dessa desse nessa nesse dele dela quero gostaria saber""".split()
_STOP = frozenset(_STOPWORDS)
_PREFIX = 6
_K1, _B = 1.2, 0.75
MIN_DISTINCTIVE_TERMS = 2
# Share of the question's weight a document must cover; independent of corpus size.
MIN_COVERAGE = 0.2
# A further article only joins the best one when it is about as strong.
MIN_RELATIVE_SCORE = 0.8


def fold(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c)
    )


def terms(text: str) -> list[str]:
    """Prefix terms absorb the inflection of Portuguese words (transferir, transferência)."""
    return [word[:_PREFIX] for word in re.findall(r"[a-z]{3,}", fold(text)) if word not in _STOP]


@dataclass(frozen=True)
class LexicalCandidate:
    id: str
    document: str
    metadata: dict
    score: float
    matched_terms: tuple[str, ...]


def lexical_candidates(
    collection,
    question: str,
    *,
    sector=None,
    excluded_sources=None,
    exclude_ids=(),
    eligible=None,
    limit=2,
) -> list[LexicalCandidate]:
    """Rank by BM25; statistics come from the documents of the same sector and sources."""
    wanted = set(terms(question))
    if len(wanted) < MIN_DISTINCTIVE_TERMS:
        return []
    rows = collection.get(include=["documents", "metadatas"])
    population = []
    for chunk_id, document, metadata in zip(
        rows["ids"], rows["documents"], rows["metadatas"], strict=True
    ):
        if sector is not None and metadata.get("sector") != sector:
            continue
        if metadata.get("source") in (excluded_sources or ()):
            continue
        population.append((chunk_id, document, metadata, Counter(terms(document))))
    if not population:
        return []
    average = sum(sum(c.values()) for *_, c in population) / len(population)
    frequency = Counter(term for *_, counts in population for term in counts if term in wanted)

    def idf(term):
        return math.log(1 + (len(population) - frequency[term] + 0.5) / (frequency[term] + 0.5))

    total_weight = sum(idf(term) for term in wanted)
    ranked = []
    for chunk_id, document, metadata, counts in population:
        if chunk_id in exclude_ids or (eligible is not None and not eligible(chunk_id, metadata)):
            continue
        matched = tuple(sorted(term for term in wanted if counts.get(term)))
        if len(matched) < MIN_DISTINCTIVE_TERMS:
            continue
        if sum(idf(term) for term in matched) < MIN_COVERAGE * total_weight:
            continue
        size = sum(counts.values())
        score = 0.0
        for term in matched:
            count = counts[term]
            score += idf(term) * count * (_K1 + 1) / (count + _K1 * (1 - _B + _B * size / average))
        ranked.append(LexicalCandidate(chunk_id, document, metadata, score, matched))
    ranked.sort(key=lambda c: (-c.score, c.id))
    return [c for c in ranked[:limit] if c.score >= MIN_RELATIVE_SCORE * ranked[0].score]
