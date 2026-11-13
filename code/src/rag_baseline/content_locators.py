"""Scoped body permissions from structured provenance, independent of display policy.

The bounded parser handles the enumerated Portuguese forms; it is not a legal
parser. Subdivision existence is read from the line structure of the final evidence;
this does not validate what a body claims a subdivision says.
"""

import re
import unicodedata
from dataclasses import dataclass

from rag_baseline.grounding import TemporalGroundingContext
from rag_baseline.output_contracts import AllowedContentLocator, NormativeReference

POLICY_VERSION = "3"
NORM = re.compile(r"\b(\d+(?:\.\d{3})*)\s*/\s*(\d{4})\b")
ARTICLE = re.compile(r"\bart(?:igo)?s?\.?\s*(\d+[º°o]?(?:\s*(?:,|e)\s*\d+[º°o]?)*)\b")
SUBDIVISION = re.compile(
    r"(?P<paragraph>§+\s*\d+[º°o]?|\bparagrafo\s+(?:unico|\d+[º°o]?))|"
    r"\bincisos?\s+(?P<inciso>[ivxlcdm\d]+)\b|"
    r"\balineas?\s+[\"'‘’“”]?(?P<alinea>[a-z])\b|"
    r"\b(?P<caput>caput)\b|"
    r"\bart(?:igo)?\.?\s*\d+[º°o]?\s*,\s*(?P<roman>[ivxlcdm]+)\b"
)


def fold(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c)
    )


def norm_id(match) -> str:
    return f"ufpi-{match[1].replace('.', '')}-{match[2]}"


def _distance(a, b):
    return max(a.start() - b.end(), b.start() - a.end(), 0)


def nearest(text, match, candidates, window=120):
    """Only an unambiguous nearest candidate in a short punctuation-bounded clause."""
    nearby = [
        c
        for c in candidates
        if _distance(match, c) < window
        and not re.search(
            r"[;!?\n]|\.(?!\d)", text[min(match.end(), c.end()) : max(match.start(), c.start())]
        )
    ]
    if not nearby:
        return None
    best = min(_distance(match, c) for c in nearby)
    winners = [c for c in nearby if _distance(match, c) == best]
    return winners[0] if len(winners) == 1 else None


def associated_norm(text, article_match, norms):
    """Prefer a document attached after the provision, not a nearby amending act.

    An intervening temporal/predicate phrase is not an article/document binding.
    This is deliberately bounded; unrecognized attribution remains implicit.
    """
    candidates = []
    for candidate in norms:
        if _distance(article_match, candidate) >= 120:
            continue
        gap = text[
            min(article_match.end(), candidate.end()) : max(
                article_match.start(), candidate.start()
            )
        ]
        if re.search(
            r"[;!?\n]|\.(?!\d)|\b(?:alteracao|alterou|alterad[ao]|promovida|apos|antes|vigente|estabelece|estabelecia|previa)\b",
            gap,
        ):
            continue
        candidates.append(candidate)
    following = [candidate for candidate in candidates if candidate.start() >= article_match.end()]
    return nearest(text, article_match, following or candidates)


@dataclass(frozen=True)
class LocatorMention:
    start: int
    end: int
    norm_id: str | None
    article: str | None
    subdivision_type: str
    subdivision_value: str


def locator_mentions(raw: str) -> list[LocatorMention]:
    text = fold(raw)
    articles, norms = list(ARTICLE.finditer(text)), list(NORM.finditer(text))
    result = []
    for match in SUBDIVISION.finditer(text):
        kind = match.lastgroup
        value = match[kind]
        if kind == "paragraph":
            value = "unico" if "unico" in value else re.search(r"\d+", value)[0]
        elif kind in {"roman", "inciso"}:
            kind, value = "inciso", value.upper()
        article_match = nearest(text, match, articles)
        numbers = re.findall(r"\d+", article_match[1]) if article_match else []
        article = numbers[0] if len(numbers) == 1 else "__ambiguous__" if numbers else None
        norm_match = (
            associated_norm(text, article_match, norms)
            if article_match
            else nearest(text, match, norms)
        )
        result.append(
            LocatorMention(
                match.start(),
                match.end(),
                norm_id(norm_match) if norm_match else None,
                article,
                kind,
                value,
            )
        )
    return result


def matching_permissions(mention, locators):
    candidates = [
        locator
        for locator in locators
        if (locator.subdivision_type, locator.subdivision_value)
        == (mention.subdivision_type, mention.subdivision_value)
        and (mention.article is None or locator.article == mention.article)
        and (mention.norm_id is None or locator.norm_id == mention.norm_id)
    ]
    # An implicit article/norm is only safe when the remaining provision is unique.
    return (
        candidates
        if len({(locator.norm_id, locator.article) for locator in candidates}) == 1
        else []
    )


_LINE_PREFIX = r"^[\s>*\-]*(?:\d+\.\s*)?"
# OCR forms observed in the indexed documents; only a line start declares a provision.
_PARAGRAPH_LINE = re.compile(_LINE_PREFIX + r"(?:§+|\$+|S\$|8(?=\s+\d+\s*[º°o]))\s*(\d+)", re.M)
_SINGLE_PARAGRAPH_LINE = re.compile(_LINE_PREFIX + r"par[áa]grafo\s+[úu]nico\b", re.I | re.M)
_INCISO_LINE = re.compile(_LINE_PREFIX + r"([IVXLC|l]+)\s*[-–—]", re.M)
_ALINEA_LINE = re.compile(_LINE_PREFIX + r"([a-z])\)", re.M)
_ROMAN = re.compile(r"M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})")


def evidence_subdivisions(content: str) -> set[tuple[str, str]]:
    """Provisions this article text declares, excluding cross-references inside sentences."""
    found = {("caput", "caput")}
    found |= {("paragraph", match[1]) for match in _PARAGRAPH_LINE.finditer(content)}
    if _SINGLE_PARAGRAPH_LINE.search(content):
        found.add(("paragraph", "unico"))
    for match in _INCISO_LINE.finditer(content):
        roman = match[1].replace("|", "I").replace("l", "I")
        if roman and _ROMAN.fullmatch(roman):
            found.add(("inciso", roman))
    found |= {("alinea", match[1]) for match in _ALINEA_LINE.finditer(content)}
    return found


class ContentLocatorPolicy:
    @staticmethod
    def from_evidence(evidence: dict) -> list[AllowedContentLocator]:
        """Permissions for subdivisions that really exist in each final (norm, article) text."""
        return [
            AllowedContentLocator(
                norm_id=norm,
                article=article,
                subdivision_type=kind,
                subdivision_value=value,
                source="validated_evidence",
                authorization_reason="Subdivision declared by the final evidence text.",
            )
            for (norm, article), content in sorted(evidence.items())
            for kind, value in sorted(evidence_subdivisions(content))
        ]

    @classmethod
    def for_generation(cls, query, grounding, references, chunks):
        """Permissions for one generation: structural evidence, query and known relations."""
        provenance = {e.chunk_id: e for e in grounding.evidence_states}
        evidence = {
            (provenance[c.id].source_norm, provenance[c.id].source_article): c.content
            for c in chunks
            if c.id in provenance
        }
        # An amending article transcribes the target's wording: its markers belong to the target.
        amending = {
            (relation.target_norm, re.match(r"\s*(\d*)", relation.evidence_article or "")[1])
            for relation in grounding.known_relations
            if relation.relation == "AMENDED_BY"
        }
        locators = cls().build(
            query,
            grounding,
            references,
            validated_evidence=cls.from_evidence(
                {key: text for key, text in evidence.items() if key not in amending}
            ),
            # An article cannot declare what it only transcribes, even when the user asks.
            declared_evidence={
                key: "" if key in amending else text for key, text in evidence.items()
            },
        )
        return evidence, locators

    def build(
        self,
        query: str,
        grounding: TemporalGroundingContext,
        official_references: list[NormativeReference],
        *,
        validated_evidence: list[AllowedContentLocator] = (),
        declared_evidence: dict | None = None,
    ) -> list[AllowedContentLocator]:
        pairs = {(e.source_norm, e.source_article) for e in grounding.evidence_states}
        if any((r.norm_id, r.article) not in pairs for r in official_references if r.article):
            raise ValueError("Display reference outside final structural evidence")
        result = []

        def add(
            norm,
            article,
            kind=None,
            value=None,
            source="validated_evidence",
            reason="Final grounding validates this norm/article, independently of display ceiling.",
        ):
            result.append(
                AllowedContentLocator(
                    norm_id=norm,
                    article=article,
                    subdivision_type=kind,
                    subdivision_value=value,
                    source=source,
                    authorization_reason=reason,
                )
            )

        for norm, article in sorted(pairs):
            add(norm, article)
        for mention in locator_mentions(query):
            candidates = {
                (n, a)
                for n, a in pairs
                if a == mention.article and (mention.norm_id is None or n == mention.norm_id)
            }
            if len(candidates) == 1:
                norm, article = next(iter(candidates))
                # Asking about a subdivision does not make it exist in the evidence.
                if (
                    declared_evidence is not None
                    and (norm, article) in declared_evidence
                    and (mention.subdivision_type, mention.subdivision_value)
                    not in evidence_subdivisions(declared_evidence[(norm, article)])
                ):
                    continue
                add(
                    norm,
                    article,
                    mention.subdivision_type,
                    mention.subdivision_value,
                    "query_explicit",
                    "Explicit query subdivision bound to an unambiguous final norm/article.",
                )
        for relation in grounding.known_relations:
            if relation.target_article and relation.target_paragraph:
                add(
                    relation.source_norm,
                    relation.target_article,
                    "paragraph",
                    relation.target_paragraph,
                    "amendment_target",
                    "Explicit amendment target in the final grounding.",
                )
            # Resolve the proof document from its structured source, never from raw chunk text.
            proof = NORM.search(fold(relation.evidence_source))
            if proof and norm_id(proof) in {relation.source_norm, relation.target_norm}:
                proof_norm = norm_id(proof)
                article = re.fullmatch(
                    r"\s*(\d+)\s*(?:,\s*([IVXLCDM]+))?\s*", relation.evidence_article, re.I
                )
                if article:
                    add(
                        proof_norm,
                        article[1],
                        source="normative_relation",
                        reason="Proof article of a known relation already selected in grounding; body-only permission.",
                    )
                    if article[2]:
                        add(
                            proof_norm,
                            article[1],
                            "inciso",
                            article[2].upper(),
                            "normative_relation",
                            "Explicit inciso in the structured proof of the known relation.",
                        )
        for locator in validated_evidence:
            if (
                locator.source != "validated_evidence"
                or (locator.norm_id, locator.article) not in pairs
            ):
                raise ValueError("Validated subdivision must bind to final evidence")
            result.append(locator)
        return list(dict.fromkeys(result))
