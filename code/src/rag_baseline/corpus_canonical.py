"""Canonical plain legal text for every corpus: conversion syntax removed, words kept.

The corpora come from PDF-to-markdown conversion (and OCR for the scanned norms). Their
words are right, but the text carries markdown syntax (bold, block quotes, bullets,
headings, auto-numbering before legal markers), LaTeX fractions and HTML entities that a
reader, and a model quoting the text, do not reproduce. This module removes only that
syntax: every word stays, in the same order, and every provision keeps its line and its
legal marker (Art., §, Parágrafo único, I -, a)).

Usage: ``python -m rag_baseline.corpus_canonical --write`` regenerates the canonical
corpora and the change log; ``--check`` verifies the published files.
"""

import argparse
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parents[3] / "evaluation" / "corpora"
TARGETS = {
    "graduacao_setor_v2.json": "graduacao_setor_v3.json",
    "pos_graduacao_setor_v3.json": "pos_graduacao_setor_v4.json",
    "658_2024_temporal_v2.json": "658_2024_temporal_v3.json",
    "1056_2026_temporal_v2.json": "1056_2026_temporal_v3.json",
}
LOG_NAME = "canonical_text_log_v1.json"
NAME_FIELDS = frozenset({"titulo_nome", "capitulo_nome", "secao_nome", "subsecao_nome"})

_FRACTION = re.compile(r"\$\\frac\{(\d+)\}\{(\d+)\}\$")
_EMPHASIS = re.compile(r"\*\*|__")
# Single-asterisk italics around a term ("*campus*") and a stray asterisk after punctuation.
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)([^*\n]{1,80}?)(?<!\s)\*(?![\w*])")
_STRAY_ASTERISK = re.compile(r"(?<=[.;:,!?])\*+(?=\s|$)")
_LEGAL_MARKER = r"(?:[IVXLC]+\s*[-–—]|[a-z]\)|§|Art\.?\s|Par[áa]grafo)"
_LINE_SYNTAX = (
    ("block_quote", re.compile(r"^>\s*")),
    ("bullet", re.compile(r"^[-*+]\s+")),
    ("heading", re.compile(r"^#{1,6}\s+")),
    ("auto_number", re.compile(r"^\d+\.\s+(?=" + _LEGAL_MARKER + ")")),
)
_INCISO_SEPARATOR = re.compile(r"^([IVXLC]+)\s*[-–—]\s*")
_SPACES = re.compile(r"[ \t]{2,}")


def canonicalize(text: str, counts: Counter | None = None) -> str:
    counts = Counter() if counts is None else counts

    def sub(pattern, repl, value, rule):
        result, n = pattern.subn(repl, value)
        counts[rule] += n
        return result

    if html.unescape(text) != text:
        counts["html_entity"] += 1
        text = html.unescape(text)
    text = sub(_FRACTION, r"\1/\2", text, "latex_fraction")
    text = sub(_EMPHASIS, "", text, "emphasis")
    text = sub(_ITALIC, r"\1", text, "italic")
    text = sub(_STRAY_ASTERISK, "", text, "stray_asterisk")
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        changed = True
        while changed:  # syntax can be nested: "> * a)", "- 2. I -"
            changed = False
            for rule, pattern in _LINE_SYNTAX:
                stripped = pattern.sub("", line, count=1)
                if stripped != line:
                    counts[rule] += 1
                    line, changed = stripped, True
        new = _INCISO_SEPARATOR.sub(r"\1 - ", line, count=1)
        if new != line:
            counts["inciso_separator"] += 1
            line = new
        line = sub(_SPACES, " ", line, "spaces").rstrip()
        lines.append(line)
    return "\n".join(lines)


def build_canonical_corpora(corpus_dir: Path = CORPUS_DIR) -> tuple[dict[str, str], dict]:
    published, entries, totals = {}, [], Counter()
    for source, target in TARGETS.items():
        items = json.loads((corpus_dir / source).read_text(encoding="utf-8"))
        out = []
        for index, item in enumerate(items):
            counts = Counter()
            content = canonicalize(item["conteudo"], counts)
            meta = item.get("metadados")
            if isinstance(meta, dict):
                # Hierarchy names reach the prompt and the embedding text too.
                meta = {
                    k: canonicalize(v, counts) if k in NAME_FIELDS and isinstance(v, str) else v
                    for k, v in meta.items()
                }
                out.append({**item, "conteudo": content, "metadados": meta})
            else:
                out.append({**item, "conteudo": content})
            if content != item["conteudo"]:
                entries.append(
                    dict(
                        source=source,
                        target=target,
                        index=index,
                        id=item.get("id"),
                        rules=dict(sorted(counts.items())),
                    )
                )
            totals.update({f"{target}:{rule}": n for rule, n in counts.items()})
        published[target] = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    log = {
        "scope": "Conversion syntax only (markdown, LaTeX fractions, HTML entities, spacing); "
        "every word and every provision line is kept.",
        "sources": TARGETS,
        "counts": dict(sorted(totals.items())),
        "entries": entries,
    }
    return published, log


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    published, log = build_canonical_corpora()
    published[LOG_NAME] = json.dumps(log, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        for name, text in published.items():
            (CORPUS_DIR / name).write_text(text, encoding="utf-8", newline="\n")
        return 0
    stale = [
        name
        for name, text in published.items()
        if not (CORPUS_DIR / name).is_file()
        or (CORPUS_DIR / name).read_text(encoding="utf-8") != text
    ]
    for name in stale:
        print(f"stale: {name}", file=sys.stderr)
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
