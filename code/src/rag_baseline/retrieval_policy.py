"""Bounded structural parsing and strategy selection; no temporal decisions."""

import re
import unicodedata
from dataclasses import dataclass

from rag_baseline.tool_contracts import RetrievalStrategy
from rag_baseline.versioning import NormativeRegistry

_NORM = re.compile(r"(?<![\w.])(\d+(?:\.\d{3})*)\s*/\s*(\d{4})(?!\d)")
_ARTICLE = re.compile(
    r"\bart(?:igo)?s?\.?\s*(\d+[a-z]?[º°]?(?:\s*(?:,|e|ou|/|&|a|até|ate|[-–—])\s*\d+[a-z]?[º°]?)*)\b",
    re.I,
)


@dataclass(frozen=True)
class ResolvedIdentity:
    norm_id: str | None
    sector: str | None
    source: str
    article: str | None
    method: str


class NormativeIdentityResolver:
    def __init__(self, registry: NormativeRegistry):
        self.records = {n.norm_id: n for n in registry.norms}
        self.sources = {source: n.norm_id for n in registry.norms for source in n.sources}

    def resolve(self, chunk_id: str, metadata: dict) -> ResolvedIdentity:
        source = metadata.get("source", "")
        article = metadata.get("article_number")
        article = str(article) if article is not None else None
        identities = [
            ("metadata", metadata.get("norm_id")),
            ("chunk_id", chunk_id.split("-art-", 1)[0]),
            ("source", self.sources.get(source)),
        ]
        valid = [(method, value) for method, value in identities if value in self.records]
        sector = metadata.get("sector")
        if len({value for _, value in valid}) > 1:
            return ResolvedIdentity(None, sector, source, article, "conflict")
        if not valid or article is None or not re.fullmatch(r"\d+[a-z]?", article, re.I):
            return ResolvedIdentity(None, sector, source, article, "unknown")
        method, norm_id = valid[0]
        expected_sector = self.records[norm_id].sector
        if sector is not None and sector != expected_sector:
            return ResolvedIdentity(None, sector, source, article, "conflict")
        return ResolvedIdentity(norm_id, expected_sector, source, article, method)


@dataclass(frozen=True)
class ParsedReference:
    norm_ids: tuple[str, ...]
    articles: tuple[str, ...]
    raw_norm_references: tuple[str, ...]
    raw_article_references: tuple[str, ...]
    unknown_norm: bool
    ambiguous: bool
    semantic_query_remains: bool

    @property
    def norm_id(self):
        return self.norm_ids[0] if len(self.norm_ids) == 1 and not self.unknown_norm else None

    @property
    def article(self):
        return self.articles[0] if len(self.articles) == 1 else None


class NormativeQueryReferenceParser:
    def __init__(self, registry: NormativeRegistry):
        # Number/year normalization uses only identifiers actually registered.
        self.names = {}
        for norm in registry.norms:
            match = re.fullmatch(r"ufpi-(\d+)-(\d{4})", norm.norm_id)
            if match:
                self.names[(match[1], match[2])] = norm.norm_id

    def parse(self, query: str) -> ParsedReference:
        norms, articles = list(_NORM.finditer(query)), list(_ARTICLE.finditer(query))
        names = [(m[1].replace(".", ""), m[2]) for m in norms]
        norm_ids = tuple(dict.fromkeys(self.names[n] for n in names if n in self.names))
        numbers = []
        for match in articles:
            for number in re.finditer(r"(\d+)([a-z]?)[º°]?", match[1], re.I):
                numbers.append(str(int(number[1])) + number[2].lower())
        numbers = tuple(dict.fromkeys(numbers))
        ambiguous = len(set(names)) > 1 or len(numbers) > 1
        # A plural article expression must never be interpreted as one prefix.
        ambiguous |= any(re.match(r"art(?:igo)?s", m[0], re.I) for m in articles)
        ambiguous |= any(
            re.match(
                r"\s*(?:[-–—]\s*[a-z]|\.\s*\d|e\s+(?:seguintes|seg\b))", query[m.end() :], re.I
            )
            for m in articles
        )
        if len(norms) == len(articles) == 1:
            norm, article = norms[0], articles[0]
            gap = query[min(norm.end(), article.end()) : max(norm.start(), article.start())]
            ambiguous |= len(gap) > 140 or bool(re.search(r"[;!?\n]|\.(?!\d)", gap))
        remainder = query
        for match in sorted(norms + articles, key=lambda m: m.start(), reverse=True):
            remainder = remainder[: match.start()] + " " + remainder[match.end() :]
        remainder = "".join(
            c
            for c in unicodedata.normalize("NFD", remainder.lower())
            if not unicodedata.combining(c)
        )
        remainder = re.sub(r"§+\s*\d+[º°]?", " ", remainder)
        stop = set(
            "resolucao resolucoes artigo artigos art arts numero norma normas que qual quais onde fala diz dizer sobre para pela pelo uma como nos nas das dos da do de em na no ao os as por seu sua segundo conforme caput paragrafo inciso alinea".split()
        )
        semantic = any(token not in stop for token in re.findall(r"[a-z]{3,}", remainder))
        return ParsedReference(
            norm_ids,
            numbers,
            tuple(m[0] for m in norms),
            tuple(m[0] for m in articles),
            any(n not in self.names for n in names),
            ambiguous,
            semantic,
        )


@dataclass(frozen=True)
class RetrievalPlan:
    strategy: RetrievalStrategy
    reference: ParsedReference
    consistency: str


class RetrievalStrategySelector:
    def __init__(self, registry: NormativeRegistry):
        self.parser = NormativeQueryReferenceParser(registry)
        self.sectors = {n.norm_id: n.sector for n in registry.norms}

    def select(self, query: str, *, scope: str | None) -> RetrievalPlan:
        parsed = self.parser.parse(query)
        consistency = (
            "router_clarification"
            if scope is None
            else "scope_conflict"
            if scope != "ambas" and any(self.sectors[n] != scope for n in parsed.norm_ids)
            else "unknown_norm"
            if parsed.unknown_norm
            else "consistent"
        )
        strategy = RetrievalStrategy.DENSE_VECTOR
        if parsed.norm_id and not parsed.ambiguous:
            if parsed.article:
                strategy = RetrievalStrategy.METADATA_EXACT
            elif parsed.semantic_query_remains:
                strategy = RetrievalStrategy.VECTOR_FILTERED
        return RetrievalPlan(strategy, parsed, consistency)
