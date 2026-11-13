"""High precision routing-only expansion of an explicit academic abbreviation."""

import re

_POSTGRADUATE_CUE = re.compile(
    r"\b(na|da|pela|para\s+a)\s+pós(?=$|[ \t\r\n?!.,;:)\]])", re.IGNORECASE
)
_TERMINAL_POSTGRADUATE_CUE = re.compile(r"\ba\s+pós(?=\s*[?!.,;:)\]]*\s*$)", re.IGNORECASE)


def routing_question(question: str) -> str:
    """Keep original storage/retrieval text; expand only standalone domain phrases."""
    question = _POSTGRADUATE_CUE.sub(lambda match: match.group(1) + " pós-graduação", question)
    return _TERMINAL_POSTGRADUATE_CUE.sub("a pós-graduação", question)


_OVERRIDE_SENTENCE = re.compile(
    r"^\s*(?:ignore|ignorar|desconsidere|esque[cç]a|finja|aja\s+como|responda\s+como)\b",
    re.IGNORECASE,
)


def without_override_instructions(question: str) -> str:
    """Drop imperative override sentences for level resolution; they never define the level."""
    sentences = re.findall(r"[^.?!]+[.?!]*", question)
    kept = [s for s in sentences if not _OVERRIDE_SENTENCE.match(s)]
    if not kept or len(kept) == len(sentences):
        return question
    return "".join(kept).strip()
