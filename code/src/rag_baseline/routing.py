"""Conservative scope hints from user text, independent of datasets and retrieval."""

import re
import unicodedata

from rag_baseline.scope import validate_sector


def question_sector(
    question: str, explicit: str | None = None, *, explicit_only: bool = False
) -> str | None:
    validate_sector(explicit)
    if is_level_comparison(question):
        return None
    text = "".join(
        c
        for c in unicodedata.normalize("NFKD", question.casefold())
        if not unicodedata.combining(c)
    )
    post = bool(
        re.search(
            r"\b(mestrado|doutorado|mestrand[oa]|doutorand[oa]|dissertacao|tese|stricto\s+sensu|pos[-\s]+graduacao)\b",
            text,
        )
    )
    # A strict bypass must not mistake an unresolved shorthand/composite for
    # standalone graduação ("graduação e pós", or a Unicode pós compound).
    # Defer these forms to RouterV1 instead of extending academic inference.
    if explicit_only and not post and re.search(r"\bpos\b", text):
        return None
    # Remove the postgraduate compound before detecting the standalone level.
    without_post = re.sub(r"\bpos[-\s]+graduacao\b", "", text)
    # Preserve accents for the acronym: the verb 'irá' is not the index IRA.
    has_ira = bool(re.search(r"\bira\b", question, flags=re.I))
    grad = bool(re.search(r"\bgraduacao\b", without_post))
    if not explicit_only:
        grad = (
            grad
            or has_ira
            or bool(re.search(r"\b(exame\s+final|laurea\s+universitaria)\b", without_post))
        )
    inferred = ("pos_graduacao" if post else "graduacao") if post != grad else None
    if explicit and inferred and explicit != inferred:
        raise ValueError("O setor informado conflita com o nível explícito na pergunta.")
    return explicit or inferred


def needs_scope_clarification(question: str) -> bool:
    """Scope gate for this pair of UFPI norms; not a general normative classifier.

    The common attendance topic is a documented exception for these two snapshots.
    No threshold or gold answer is encoded here: generation still needs evidence.
    """
    text = "".join(
        c
        for c in unicodedata.normalize("NFKD", question.casefold())
        if not unicodedata.combining(c)
    )
    grad = bool(re.search(r"\bgraduacao\b", re.sub(r"pos[-\s]+graduacao", "", text)))
    post = bool(re.search(r"\b(mestrado|doutorado|pos[-\s]+graduacao)\b", text))
    if grad and post:
        return False
    attendance = bool(re.search(r"frequencia|presenca|faltas?", text))
    limit = bool(re.search(r"minim|maxim|quant[ao]s?|percentual|porcentagem", text))
    grades = bool(re.search(r"\b(nota|media|exame|prova)\b", text))
    return not (attendance and limit and not grades)


def is_level_comparison(question: str) -> bool:
    text = "".join(
        c
        for c in unicodedata.normalize("NFKD", question.casefold())
        if not unicodedata.combining(c)
    )
    without_post = re.sub(r"pos[-\s]+graduacao", "", text)
    return bool(re.search(r"\bgraduacao\b", without_post)) and bool(
        re.search(r"\b(mestrado|doutorado|pos[-\s]+graduacao)\b", text)
    )
