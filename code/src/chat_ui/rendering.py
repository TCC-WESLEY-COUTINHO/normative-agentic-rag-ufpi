"""Markup for text and typed evidence. Everything received from the service is escaped."""

import re
from collections import defaultdict, deque
from html import escape

from rag_baseline.output_contracts import NormativeReference
from rag_baseline.ui_presentation import group_references

_QUOTE_PREFIX = re.compile(r" {0,3}(?:> ? {0,3})*")
_FENCE = re.compile(r" {0,3}(?:> ? {0,3})*(`{3,}|~{3,})(.*)")
_BACKTICKS = re.compile(r"`+")
_BLANK_LINE = re.compile(r"(\n[ \t]*\n)")
_LINES = re.compile(r"[^\n]*\n|[^\n]+")
_UNESCAPED_SPECIAL = re.compile(r"(?<!\\)((?:\\\\)*)(\$|:(?=[\w/+-]+(?::|\[)))")
_INDENTED = re.compile(r"(?: {0,3}> ?)*(?: {4}| {0,3}\t)\s*\S")
_LIST_ITEM = re.compile(r" {0,3}(?:[-*+]|\d{1,9}[.)])\s")
ROLE_LABELS = {"historical": "Contexto histórico", "posterior": "Contexto posterior"}
SCOPE_LABELS = {
    "graduacao": "normas de graduação",
    "pos_graduacao": "normas de pós-graduação",
    "ambas": "normas de graduação e pós-graduação",
}


def _protect(text: str) -> str:
    """Add a backslash only where none is already acting on the character."""
    return _UNESCAPED_SPECIAL.sub(r"\1\\\2", text)


def _protect_outside_inline_code(paragraph: str) -> str:
    """An inline span closes on a backtick run of exactly the same length (CommonMark)."""
    runs = list(_BACKTICKS.finditer(paragraph))
    by_length = defaultdict(deque)
    for index, run in enumerate(runs):
        by_length[len(run.group())].append(index)
    parts, position, index = [], 0, 0
    while index < len(runs):
        candidates = by_length[len(runs[index].group())]
        while candidates and candidates[0] <= index:
            candidates.popleft()
        if candidates:
            closing = candidates[0]
            parts += [
                _protect(paragraph[position : runs[index].start()]),
                paragraph[runs[index].start() : runs[closing].end()],
            ]
            position = runs[closing].end()
            index = closing
        index += 1
    return "".join([*parts, _protect(paragraph[position:])])


def _protect_prose(lines: list[str]) -> str:
    pieces = _BLANK_LINE.split("".join(lines))
    return "".join(
        piece if index % 2 else _protect_outside_inline_code(piece)
        for index, piece in enumerate(pieces)
    )


def literal_markdown(text: str) -> str:
    """Keep Markdown structure but show `$` and `:word:` as written, not as math or emoji.

    Only backslashes are added, and never inside fenced, indented or inline code. Inside a list,
    indentation continues the item, so it is treated as prose.
    """
    output, prose, fence, fence_depth = [], [], None, 0
    after_blank, in_list = True, False
    for line in _LINES.findall(text):
        blank = not line.strip(" \t\r\n>")
        indented = _INDENTED.match(line) is not None
        if _LIST_ITEM.match(line):
            in_list = True
        elif after_blank and not blank and not indented:
            in_list = False
        starts_code = indented and after_blank and not in_list and fence is None
        after_blank = blank or (starts_code and after_blank)
        match = _FENCE.fullmatch(line.rstrip("\n"))
        depth = _QUOTE_PREFIX.match(line).group().count(">")
        if fence is not None and depth < fence_depth:
            fence = None  # The block quote holding the fence ended, and the fence with it.
        if fence is not None:
            output.append(line)
            delimiter = match.group(1) if match else ""
            closes = delimiter[:1] == fence[0] and len(delimiter) >= len(fence)
            if closes and depth == fence_depth and not match.group(2).strip():
                fence = None
        elif match and not (match.group(1)[0] == "`" and "`" in match.group(2)):
            output.append(_protect_prose(prose))
            prose = []
            output.append(line)
            fence, fence_depth = match.group(1), depth
        elif starts_code:
            output.append(_protect_prose(prose))
            prose = []
            output.append(line)
        else:
            prose.append(line)
    output.append(_protect_prose(prose))
    return "".join(output)


def _text(value: str) -> str:
    """Escape for a one-line raw block: a blank line would end it and reopen Markdown parsing."""
    return escape(value).replace("\r", "&#13;").replace("\n", "&#10;")


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def reference_title(reference: NormativeReference) -> str:
    title = f"Art. {reference.article}" if reference.article else "Trecho normativo"
    if reference.validated_subdivision:
        title += f", {reference.validated_subdivision}"
    return title


_DOCUMENT_ICON = (
    '<svg class="ufpi-icon" viewBox="0 0 16 16" aria-hidden="true">'
    '<path d="M4 1.5h5.5L12.5 4.5v10h-8.5z"/><path d="M9.5 1.5v3h3M6 8h4.5M6 10.5h4.5"/></svg>'
)
_COPY_ICON = (
    '<svg class="ufpi-icon" viewBox="0 0 16 16" aria-hidden="true">'
    '<rect x="5.5" y="5.5" width="8" height="8" rx="1.5"/>'
    '<path d="M10.5 5.5v-2a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2"/></svg>'
)


def copy_markup(content: str) -> str:
    """The stored text travels whole in the button, so copying never reads the rendered page."""
    return (
        '<div class="ufpi-actions"><button type="button" class="ufpi-copy" '
        f'data-copy="{_text(content)}">{_COPY_ICON}'
        '<span class="ufpi-copy-label" role="status">Copiar resposta</span></button></div>'
    )


def _reference(reference: NormativeReference, uncertified: bool) -> str:
    tags = []
    if role := ROLE_LABELS.get(reference.temporal_role):
        tags.append(role)
    if uncertified:
        tags.append("Vigência não certificada")
    tag_markup = "".join(f'<span class="ufpi-ref-tag">{escape(tag)}</span>' for tag in tags)
    if reference.evidence_text is None:
        body = '<p class="ufpi-ref-missing">Texto integral indisponível nesta resposta.</p>'
    else:
        body = (
            '<p class="ufpi-ref-label">Trecho recuperado da norma</p>'
            f'<div class="ufpi-ref-text" tabindex="0">{_text(reference.evidence_text)}</div>'
        )
    return (
        '<details class="ufpi-ref"><summary>'
        f'<span class="ufpi-ref-title">{_text(reference_title(reference))}</span>{tag_markup}'
        f"</summary>{body}</details>"
    )


def sources_markup(
    references: list[NormativeReference],
    *,
    domain: str | None = None,
    uncertified_chunks: frozenset[str] = frozenset(),
    conclusive: bool = True,
) -> str:
    """Typed references by norm. The contract has no per-claim link, so none is suggested.

    Text that did not support a conclusion is listed closed and is not called a source.
    """
    groups = group_references(references)
    counts = (
        f"{_plural(len(groups), 'norma', 'normas')} · "
        f"{_plural(len(references), 'trecho', 'trechos')}"
    )
    scope = f" em {SCOPE_LABELS[domain]}" if domain in SCOPE_LABELS else ""
    hint = (
        f"Trechos recuperados{scope} para esta consulta. "
        "A lista não indica qual trecho fundamenta cada afirmação da resposta."
    )
    norms = "".join(
        f'<div class="ufpi-norm"><div class="ufpi-norm-head">{_DOCUMENT_ICON}'
        f'<p class="ufpi-norm-title">{_text(group.label)}</p></div>'
        + "".join(
            _reference(reference, reference.chunk_id in uncertified_chunks)
            for reference in group.references
        )
        + "</div>"
        for group in groups
    )
    title = "Fontes normativas" if conclusive else "Trechos consultados"
    # The list always starts collapsed, so it does not take the reader's screen; the heading
    # shows how many norms and excerpts it holds, and a click opens it.
    return (
        f'<details class="ufpi-sources"><summary>'
        f'<span class="ufpi-sources-title">{title}</span>'
        f'<span class="ufpi-sources-count">{counts}</span></summary>'
        f'<p class="ufpi-sources-hint">{escape(hint)}</p>{norms}</details>'
    )


def note_markup(label: str, text: str = "", kind: str = "neutral") -> str:
    """A state is stated in words first; color only reinforces it."""
    sentence = f" {escape(text)}" if text else ""
    return f'<span class="ufpi-note ufpi-note-{kind}"><strong>{escape(label)}.</strong>{sentence}</span>'
