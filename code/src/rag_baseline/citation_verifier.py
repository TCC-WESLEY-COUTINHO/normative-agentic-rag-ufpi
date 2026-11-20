"""Deterministic checks establish literal attribution, not semantic entailment."""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from math import ceil

from rag_baseline.citation_contracts import SIDE_PATTERN, CitedAnswer, Claim, ClaimVerdict
from rag_baseline.content_locators import (
    _PARAGRAPH_LINE,
    ARTICLE,
    NORM,
    associated_norm,
    locator_mentions,
    norm_id,
)
from rag_baseline.evidence_spans import EvidenceSpan
from rag_baseline.evidence_support import _TENS, _UNITS, _digits
from rag_baseline.normative_output import FALLBACK_BODY, norm_name

PARTIAL_NOTICE = "Parte da explicação foi omitida por não ter correspondência literal nos trechos normativos recuperados."
INSUFFICIENT_BODY = "Os trechos normativos recuperados não permitem responder com segurança."
LOAD_BEARING_ROLES = frozenset({"conclusion", "condition", "exception", "deadline"})
SNAP_THRESHOLD = 0.90
DELIVERY_THRESHOLD = 0.5
LEVELS = frozenset({"graduacao", "pos_graduacao"})
NEGATION_MARKERS = frozenset(
    {
        "nao",
        "nunca",
        "nenhum",
        "nenhuma",
        "nem",
        "vedado",
        "vedada",
        "vedados",
        "vedadas",
        "vedacao",
        "proibido",
        "proibida",
        "proibidos",
        "proibidas",
        "impedido",
        "impedida",
    }
)
_NEGATION = re.compile(r"\b(?:" + "|".join(sorted(NEGATION_MARKERS)) + r")\b")
_LEVEL = re.compile(r"\b(?:pos[- ]graduacao|stricto sensu|mestrado|doutorado|graduacao)\b")


def normalize(text: str) -> str:
    lines = []
    for line in text.splitlines():
        marker = _PARAGRAPH_LINE.match(line)
        lines.append(f"§ {marker[1]}{line[marker.end() :]}" if marker else line)
    text = "\n".join(lines)
    text = "".join(
        c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c)
    )
    text = text.translate(
        str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "—": "-", "–": "-"})
    )
    text = re.sub(r"§\s*(\d+)[º°o]?", r"§ \1", text)
    return " ".join(text.split())


def has_negation(text: str) -> bool:
    return bool(_NEGATION.search(normalize(text)))


def mentioned_levels(text: str, *, quotes: list[str] | None = None) -> set[str]:
    text = normalize(text)
    quoted_expressions = {
        match[0] for quote in quotes or [] for match in _LEVEL.finditer(normalize(quote))
    }
    # Like copied locators, level expressions in the claim's own quotes are not scope.
    return {
        "graduacao" if match[0] == "graduacao" else "pos_graduacao"
        for match in _LEVEL.finditer(text)
        if match[0] not in quoted_expressions
    }


def valid_side(side: str | None) -> bool:
    return side is None or bool(re.fullmatch(SIDE_PATTERN, side))


def snap_quote(
    quote: str, span_text: str, threshold: float = SNAP_THRESHOLD
) -> tuple[str | None, float]:
    """Search nearby word-window sizes; ties keep the earliest, shortest window."""
    target = normalize(quote)
    if target in normalize(span_text):
        return quote, 1.0
    words = list(re.finditer(r"\S+", span_text))
    length = len(target.split())
    margin = max(2, ceil(length * 0.2))
    best, similarity = None, 0.0
    for start in range(len(words)):
        for size in range(max(1, length - margin), length + margin + 1):
            if start + size > len(words):
                break
            candidate = span_text[words[start].start() : words[start + size - 1].end()]
            matcher = SequenceMatcher(None, target, normalize(candidate), autojunk=False)
            if matcher.quick_ratio() <= similarity:
                continue
            ratio = matcher.ratio()
            if ratio > similarity:
                best, similarity = candidate, ratio
    return (best if similarity >= threshold else None), similarity


def side_name(side: str) -> str:
    if not valid_side(side):
        return ""
    return {"graduacao": "Graduação", "pos_graduacao": "Pós-graduação"}.get(
        side, norm_name(side) if re.fullmatch(r"ufpi-\d+-\d{4}", side) else side
    )


def compose_claims(claims: list[Claim], indices) -> tuple[str, dict[int, tuple[int, int]]]:
    """Section order follows first appearance, including when earlier claims are omitted."""
    indices = list(indices)
    sides = list(dict.fromkeys(c.side for c in claims))
    ordered = (
        [i for side in sides for i in indices if claims[i].side == side]
        if any(side is not None for side in sides)
        else indices
    )
    body, offsets = "", {}
    previous = None
    for i in ordered:
        if body:
            body += "\n\n"
        side = claims[i].side if valid_side(claims[i].side) else None
        if side is not None and side != previous:
            body += side_name(side) + ":\n\n"
        start = len(body)
        body += claims[i].text
        offsets[i] = (start, len(body))
        previous = side
    return body, offsets


_NUMERALS = {
    **_UNITS,
    **_TENS,
    "zero": 0,
    "cento": 100,
    "duzentos": 200,
    "duzentas": 200,
    "trezentos": 300,
    "trezentas": 300,
    "quatrocentos": 400,
    "quatrocentas": 400,
    "quinhentos": 500,
    "quinhentas": 500,
    "seiscentos": 600,
    "seiscentas": 600,
    "setecentos": 700,
    "setecentas": 700,
    "oitocentos": 800,
    "oitocentas": 800,
    "novecentos": 900,
    "novecentas": 900,
    "mil": 1000,
    "milhao": 1000000,
    "milhoes": 1000000,
    "bilhao": 1000000000,
    "bilhoes": 1000000000,
}
_NUMERAL_WORD = "|".join(sorted(_NUMERALS, key=len, reverse=True))
_NUMBER = rf"(?:\d+(?:\.\d{{3}})*(?:,\d+)?|(?:{_NUMERAL_WORD})(?:\s+(?:e\s+)?(?:{_NUMERAL_WORD}))*)"
_NUMBER_PATTERN = re.compile(rf"\b{_NUMBER}\b")


def _number_value(text: str) -> str:
    if text[0].isdigit():
        return _digits(text.replace(".", ""))
    total, group = 0, 0
    for token in text.split():
        if token == "e":
            continue
        value = _NUMERALS[token]
        if value >= 1000000:
            total += (group or 1) * value
            group = 0
        elif value == 1000:
            group = (group or 1) * value
        else:
            group += value
    return str(total + group)


def _values(text: str) -> set[str]:
    return {_number_value(m[0]) for m in _NUMBER_PATTERN.finditer(text)}


def _following_word(text, match):
    word = re.match(r"\s+(\w+)\b", text[match.end() :])
    return word[1] if word else None


def _number_units(text):
    return {
        (_number_value(match[0]), unit)
        for match in _NUMBER_PATTERN.finditer(text)
        if (unit := _following_word(text, match)) is not None
    }


def _ancestors(cited, spans):
    result = {}
    for span in cited:
        while span is not None:
            result[span.span_id] = span
            span = spans.get(span.parent_id)
    return list(result.values())


def _matches(mention, span):
    if span.kind == "fact":
        return (
            mention.subdivision_type == "paragraph"
            and mention.subdivision_value == span.paragraph
            and (mention.article is None or mention.article == span.article)
            and (mention.norm_id is None or mention.norm_id == span.norm_id)
        )
    # An ambiguous label cannot certify which subdivision the claim names.
    return (
        not span.ambiguous
        and mention.subdivision_type == span.kind
        and mention.subdivision_value == span.label
        and (mention.article is None or mention.article == span.article)
        and (mention.norm_id is None or mention.norm_id == span.norm_id)
    )


_DEADLINE = re.compile(
    rf"\b({_NUMBER})\s+(?:\(\s*{_NUMBER}\s*\)\s*)?dias?\b"
    r"(?:\s+(util|uteis|corridos?|letivos?))?\b"
)
_QUALIFIER = re.compile(r"\bdias?\s+(util|uteis|corridos?|letivos?)\b")


def _qualifier(value):
    return {"util": "uteis", "corrido": "corridos", "letivo": "letivos"}.get(value, value or "")


def _qualifiers(text):
    return {_qualifier(m[1]) for m in _QUALIFIER.finditer(text)}


def _deadlines(text):
    result = {}
    for match in _DEADLINE.finditer(text):
        value = _number_value(match[1])
        result.setdefault(value, set()).add(_qualifier(match[2]))
    return result


def verify_claim(
    claim: Claim, spans: dict[str, EvidenceSpan], index: int = 0, question: str = ""
) -> ClaimVerdict:
    codes = []
    if not valid_side(claim.side):
        codes.append("invalid_side")
    if not claim.text.strip():
        codes.append("empty_claim")
    if not claim.support:
        codes.append("no_support")
    cited = []
    quotes = []
    for support in claim.support:
        span = spans.get(support.span_id)
        quote = normalize(support.quote)
        quotes.append(quote)
        if span is None:
            codes.append("unknown_span")
        else:
            cited.append(span)
        if len(re.findall(r"\b\w+\b", quote)) < 4:
            codes.append("quote_too_short")
        if span is not None and quote not in normalize(span.text):
            codes.append("quote_not_found")
    text = normalize(claim.text)
    leveled = [s for s in cited if s.kind != "fact" and s.sector in LEVELS]
    if claim.side in LEVELS and any(s.sector != claim.side for s in leveled):
        codes.append("side_mismatch")
    if (
        claim.side
        and re.fullmatch(r"ufpi-\d+-\d{4}", claim.side)
        and any(s.kind != "fact" and s.norm_id != claim.side for s in cited)
    ):
        codes.append("side_mismatch")
    levels = mentioned_levels(text, quotes=quotes)
    if leveled and levels - {s.sector for s in leveled}:
        codes.append("level_mismatch")
    if has_negation(text) and not any(has_negation(q) for q in quotes):
        codes.append("negation_added")
    ancestors = _ancestors(cited, spans)
    erase = []

    def quoted(start, end):
        # A cross-reference copied inside the claim's own quotation restates the cited
        # text; it is not an attribution. The output guard still decides if it may appear.
        segment = text[start:end].strip()
        return bool(segment) and any(segment in quote for quote in quotes)

    norms = list(NORM.finditer(text))
    for match in norms:
        if quoted(match.start(), match.end()) or any(
            s.norm_id == norm_id(match)
            or (s.kind == "fact" and norm_id(match) in s.related_norm_ids)
            for s in cited
        ):
            erase.append((match.start(), match.end()))
        else:
            codes.append("locator_mismatch")
    for match in ARTICLE.finditer(text):
        bound = associated_norm(text, match, norms)
        if quoted(match.start(), match.end()) or all(
            any(
                s.article == number and (bound is None or s.norm_id == norm_id(bound))
                for s in cited
            )
            for number in re.findall(r"\d+", match[1])
        ):
            erase.append((match.start(), match.end()))
        else:
            codes.append("locator_mismatch")
    for mention in locator_mentions(text):
        if quoted(mention.start, mention.end) or any(_matches(mention, s) for s in ancestors):
            erase.append((mention.start, mention.end))
        else:
            codes.append("locator_mismatch")
    numeric_text = text
    for start, end in sorted(erase, reverse=True):
        numeric_text = numeric_text[:start] + " " * (end - start) + numeric_text[end:]
    numeric_levels = mentioned_levels(text) | ({claim.side} if claim.side in LEVELS else set())
    explicit_norms = {norm_id(match) for match in norms}
    numeric_quotes = []
    for support in claim.support:
        span = spans.get(support.span_id)
        if span is None:
            continue
        if span.kind != "fact":
            if numeric_levels and span.sector is not None and span.sector not in numeric_levels:
                continue
            if explicit_norms and span.norm_id not in explicit_norms:
                continue
        numeric_quotes.append(normalize(support.quote))
    user_text = normalize(question)
    user_deadlines = _deadlines(user_text)
    user_units = _number_units(user_text)
    numeric_deadlines = list(_DEADLINE.finditer(numeric_text))
    quoted_values = _values(" ".join(numeric_quotes))

    def supplied_by_user(match):
        value = _number_value(match[0])
        if any(d.start() <= match.start() < d.end() for d in numeric_deadlines):
            return value in user_deadlines
        unit = _following_word(numeric_text, match)
        return unit is not None and (value, unit) in user_units

    if any(
        _number_value(match[0]) not in quoted_values and not supplied_by_user(match)
        for match in _NUMBER_PATTERN.finditer(numeric_text)
    ):
        codes.append("number_not_in_quotes")
    deadlines = _deadlines(text)
    # Only a numbered deadline supplied by the user bypasses qualifier matching.
    qualified_text = _DEADLINE.sub(
        lambda m: " " * len(m[0]) if _number_value(m[1]) in user_deadlines else m[0], text
    )
    if _qualifiers(qualified_text) - set().union(*(_qualifiers(q) for q in numeric_quotes)):
        codes.append("deadline_qualifier_mismatch")
    quoted_deadlines = {}
    for quote in numeric_quotes:
        for value, qualifiers in _deadlines(quote).items():
            quoted_deadlines.setdefault(value, set()).update(qualifiers)
    for value, qualifiers in deadlines.items():
        if value in user_deadlines:
            continue
        quoted = quoted_deadlines.get(value, set())
        if qualifiers - quoted or ("" in qualifiers and quoted - {""}):
            codes.append("deadline_qualifier_mismatch")
    codes = list(dict.fromkeys(codes))
    return ClaimVerdict(
        index=index,
        status="rejected" if codes else "supported",
        codes=codes,
        span_ids=list(dict.fromkeys(s.span_id for s in cited)),
    )


@dataclass(frozen=True)
class Disposition:
    body: str
    action: str
    approved_indices: list[int]
    omitted_indices: list[int]
    codes: list[str]
    caveats: list[str]


def _claim_caveats(claim, spans, role=None):
    label = {"condition": "condição", "exception": "exceção", "deadline": "prazo"}.get(
        role or claim.role, "regra"
    )
    locations = []
    for support in claim.support:
        span = spans.get(support.span_id)
        if span is None:
            locations.append("nos trechos recuperados")
            continue
        location = f"em {norm_name(span.norm_id)}"
        if span.article:
            location += f", art. {span.article}"
        ancestors = list(reversed(_ancestors([span], spans)))
        for ancestor in ancestors:
            if ancestor.ambiguous:
                continue
            if ancestor.kind == "paragraph":
                location += (
                    ", parágrafo único" if ancestor.label == "unico" else f", § {ancestor.label}"
                )
            elif ancestor.kind in {"inciso", "alinea"}:
                kind = "alínea" if ancestor.kind == "alinea" else "inciso"
                location += f", {kind} {ancestor.label}"
        if span.kind == "fact" and span.paragraph:
            location += f", § {span.paragraph}"
        locations.append(location)
    return [
        f"Ressalva: há {label} {location} que não pôde ser verificada literalmente "
        "nos trechos recuperados; consulte o dispositivo."
        for location in dict.fromkeys(locations or ["nos trechos recuperados"])
    ]


def _missing_user_fact(text: str | None) -> str:
    missing = (text or "").strip()
    normalized = normalize(missing)
    if (
        re.search(r"[\r\n;:]", text or "")
        or not re.fullmatch(r"[^.!?]+[.!?]?", missing)
        or len(re.findall(r"\b\w+\b", normalized)) > 25
        or re.search(r"\d", normalized)
        or _values(normalized)
        or has_negation(missing)
        or re.search(
            r"\b(?:pois|porque|ja que|uma vez que)\b|"
            r"\b(?:permitid|proibid|vedad|obrigatori|sempre)",
            normalized,
        )
        or re.search(
            r"\b(?:normas?|artigos?|art|dispositivos?|resolucoes|resolucao|"
            r"paragrafos?|incisos?|alineas?|caput|leis?|decretos?|portarias?)\b|§",
            normalized,
        )
        or not (
            missing.endswith("?")
            or re.match(
                r"^(?:informe|indique|diga|especifique|esclareca|confirme|selecione|escolha)\b",
                normalized,
            )
        )
    ):
        return ""
    return missing


def disposition(
    answer: CitedAnswer,
    verdicts: list[ClaimVerdict],
    *,
    repaired: bool = False,
    spans: dict[str, EvidenceSpan] | None = None,
) -> Disposition:
    spans = spans or {}
    notes = []
    all_indices = list(range(len(answer.claims)))
    supported = {v.index for v in verdicts if v.status == "supported"}
    supported -= {v.index for v in verdicts if v.status == "rejected"}
    supported -= {i for i, c in enumerate(answer.claims) if not valid_side(c.side)}
    missing = _missing_user_fact(answer.missing_user_fact)
    if answer.answer_type == "insufficient":
        if not supported:
            return Disposition(INSUFFICIENT_BODY, "insufficient", [], all_indices, [], [])
        answer = answer.model_copy(update={"answer_type": "answer"})
        notes.append("insufficient_label_overridden_by_verified_claims")
    if answer.answer_type == "needs_user_fact" and not missing:
        return Disposition(FALLBACK_BODY, "fallback", [], all_indices, ["missing_user_fact"], [])
    if answer.answer_type == "needs_user_fact" and not answer.claims:
        return Disposition(f"Dado necessário: {missing}", "needs_user_fact", [], [], [], [])

    # A request for user facts can consist solely of verified conditional guidance.
    conditional = (
        answer.answer_type == "needs_user_fact"
        and not any(c.role == "conclusion" for c in answer.claims)
        and all(c.side is None for c in answer.claims)
    )
    if not conditional and not any(c.role == "conclusion" for c in answer.claims):
        return Disposition(
            FALLBACK_BODY, "fallback", [], all_indices, notes + ["missing_conclusion"], []
        )

    approved, caveats = [], []
    sides = list(dict.fromkeys(c.side for c in answer.claims))
    comparison = any(side is not None for side in sides)
    for side in sides:
        indices = [i for i in all_indices if answer.claims[i].side == side]
        essential = [i for i in indices if answer.claims[i].role in LOAD_BEARING_ROLES]
        conclusions = [i for i in indices if answer.claims[i].role == "conclusion"]
        has_conclusion = bool(supported.intersection(conclusions))
        fraction = (
            len(supported.intersection(essential)) / len(essential)
            if essential
            else float(conditional and bool(supported.intersection(indices)))
        )
        if (not has_conclusion and not conditional) or fraction < DELIVERY_THRESHOLD:
            notes.append("load_bearing_claim_rejected")
            if fraction < DELIVERY_THRESHOLD:
                notes.append("delivery_threshold_not_met")
            if comparison and side is not None and valid_side(side):
                caveats.append(
                    f"Não foi possível verificar a regra para {side_name(side)} "
                    "nos trechos recuperados."
                )
            continue
        groups = list(dict.fromkeys(answer.claims[i].group for i in indices))
        for group in groups:
            members = [i for i in indices if answer.claims[i].group == group]
            conclusions = [i for i in members if answer.claims[i].role == "conclusion"]
            if not conditional and (
                not conclusions or not all(i in supported for i in conclusions)
            ):
                representative = next((i for i in conclusions if i not in supported), members[0])
                caveats.extend(_claim_caveats(answer.claims[representative], spans, "conclusion"))
                notes.append("group_without_verified_conclusion")
                for i in members:
                    if i not in supported and answer.claims[i].role in LOAD_BEARING_ROLES:
                        caveats.extend(_claim_caveats(answer.claims[i], spans))
                continue
            for i in members:
                if i in supported:
                    approved.append(i)
                elif answer.claims[i].role in LOAD_BEARING_ROLES:
                    caveats.extend(_claim_caveats(answer.claims[i], spans))
                    notes.append("load_bearing_claim_rejected")
        if (
            comparison
            and side is not None
            and valid_side(side)
            and not set(indices).intersection(approved)
        ):
            caveats.append(
                f"Não foi possível verificar a regra para {side_name(side)} "
                "nos trechos recuperados."
            )
    if not approved or (
        not conditional and not any(answer.claims[i].role == "conclusion" for i in approved)
    ):
        return Disposition(
            FALLBACK_BODY,
            "fallback",
            [],
            all_indices,
            list(dict.fromkeys(notes)),
            list(dict.fromkeys(caveats)),
        )
    approved.sort()
    omitted = sorted(set(all_indices) - set(approved))
    body, _ = compose_claims(answer.claims, approved)
    action = "partial" if omitted else "repaired" if repaired else "accepted"
    if any(answer.claims[i].role not in LOAD_BEARING_ROLES for i in omitted):
        body += "\n\n" + PARTIAL_NOTICE
    if answer.answer_type == "needs_user_fact":
        body += ("\n\n" if body else "") + f"Dado necessário: {missing}"
        if not omitted:
            action = "needs_user_fact"
    return Disposition(
        body, action, approved, omitted, list(dict.fromkeys(notes)), list(dict.fromkeys(caveats))
    )
