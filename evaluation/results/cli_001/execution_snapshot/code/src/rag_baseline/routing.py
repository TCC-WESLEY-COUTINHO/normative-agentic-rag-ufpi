"""Conservative scope hints from user text, independent of datasets and retrieval."""

import re
import unicodedata

from rag_baseline.scope import validate_sector


def question_sector(question: str, explicit: str | None = None) -> str | None:
    validate_sector(explicit)
    text = "".join(
        c
        for c in unicodedata.normalize("NFKD", question.casefold())
        if not unicodedata.combining(c)
    )
    post = bool(
        re.search(
            r"\b(mestrado|doutorado|mestrand[oa]|doutorand[oa]|stricto\s+sensu|pos[-\s]+graduacao)\b",
            text,
        )
    )
    # Remove the postgraduate compound before detecting the standalone level.
    without_post = re.sub(r"\bpos[-\s]+graduacao\b", "", text)
    grad = bool(
        re.search(r"\b(graduacao|ira|exame\s+final|laurea\s+universitaria)\b", without_post)
    )
    inferred = ("pos_graduacao" if post else "graduacao") if post != grad else None
    if explicit and inferred and explicit != inferred:
        raise ValueError("O setor informado conflita com o nível explícito na pergunta.")
    return explicit or inferred
