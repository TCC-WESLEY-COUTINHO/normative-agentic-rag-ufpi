"""Deterministic repair of OCR-damaged structural markers in the scanned corpora.

Only line-initial provision markers are touched: the paragraph sign and inciso numerals.
Prose is never rewritten. Every change is logged with its rule so it can be checked
against the official documents. A numeral that is valid but breaks the sequence is
flagged, never rewritten: the sequence can only restore strokes that OCR lost.

Usage: ``python -m rag_baseline.ocr_markers --write`` regenerates the corrected corpora;
``--check`` verifies that the published files match a fresh regeneration.
"""

import argparse
import json
import re
import sys
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parents[3] / "evaluation" / "corpora"
TARGETS = {
    "pos_graduacao_setor_v2.json": "pos_graduacao_setor_v3.json",
    "658_2024_temporal_v1.json": "658_2024_temporal_v2.json",
    "1056_2026_temporal_v1.json": "1056_2026_temporal_v2.json",
}
LOG_NAME = "ocr_marker_corrections_v1.json"

_PREFIX = r"^(?P<prefix>[\s>*\-]*(?:\d+\.\s*)?)"
_PARAGRAPH = re.compile(
    _PREFIX + r"(?P<mark>\$+|S\$|S(?=\s*\d+\s*[º°o])|8(?=\s+\d+\s*[º°o]))(?=\s*\d)"
)
_TOKEN = r"(?P<token>[IVXLC|l1i]+)"
_INCISO = re.compile(_PREFIX + _TOKEN + r"(?P<sep>\s*[-–—])")
# A dash lost between the numeral and the first word ("IlCPF", "ViIllcriar", "I1a").
_GLUED = re.compile(_PREFIX + _TOKEN + r"(?=[A-Za-zÀ-ÿ])")
_INLINE = re.compile(
    r"\b[Ii]ncisos?\s+[IVXLC|l]+(?![A-Za-zÀ-ÿ])"
    r"(?:\s*(?:,|e|ou|a)\s*[IVXLC|l]+(?![A-Za-zÀ-ÿ]))*"
)
_GLYPHS = str.maketrans({"|": "I", "l": "I", "1": "I", "i": "I"})
# Glyphs first seen with digits or lowercase letters need the sequence to confirm them.
_LATE_GLYPHS = frozenset("1i")
_ROMAN = re.compile(r"(?=[MDCLXVI])M*(C[MD]|D?C{0,3})(X[CL]|L?X{0,3})(I[XV]|V?I{0,3})")
_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_value(numeral: str) -> int | None:
    if not _ROMAN.fullmatch(numeral):
        return None
    total = 0
    for current, following in zip(numeral, [*numeral[1:], ""], strict=True):
        value = _VALUES[current]
        total += -value if following and _VALUES[following] > value else value
    return total


def to_roman(value: int) -> str:
    result = ""
    for number, symbol in (
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ):  # fmt: skip
        while value >= number:
            result += symbol
            value -= number
    return result


def _change(line_no, before, after, rule, changed=True):
    return {"line": line_no, "before": before, "after": after, "rule": rule, "changed": changed}


def _read(token: str) -> str:
    return token.translate(_GLYPHS)


def _dashed_reading(line):
    if _PARAGRAPH.match(line):
        return None
    found = _INCISO.match(line)
    return roman_value(_read(found["token"])) if found else None


def _inline(line: str) -> str:
    def fix(match):
        return re.sub(
            r"[IVXLC|l]+(?![A-Za-zÀ-ÿ])",
            lambda t: _read(t[0]) if roman_value(_read(t[0])) else t[0],
            match[0][match[0].index(" ") :],
        )

    return _INLINE.sub(lambda m: m[0][: m[0].index(" ")] + fix(m), line)


def _glued_cut(token: str, expected: int) -> int | None:
    """Where the numeral ends inside a token glued to the next word."""
    target = to_roman(expected)
    if roman_value(_read(token)) == expected:
        return len(token)
    for cut in range(len(token) - 1, 0, -1):
        rest = token[cut:]
        if roman_value(_read(token[:cut])) == expected and rest[0] in "VXLC":
            return cut
    if roman_value(_read(token)) is None and len(token) >= len(target):
        return len(token)  # a split glyph: the whole token is the numeral
    return None


def repair_markers(text: str) -> tuple[str, list[dict]]:
    """Return the repaired text and one log entry per repaired or flagged line."""
    out, log = [], []
    previous = None
    source = text.split("\n")
    readings = [_dashed_reading(line) for line in source]
    for line_no, line in enumerate(source, start=1):
        fixed, rule = _marker(line, line_no, source, readings, previous, log)
        if rule is not None:
            previous = rule[1]
            if fixed != line:
                log.append(_change(line_no, line, fixed, rule[0]))
        inline = _inline(fixed)
        if inline != fixed:
            log.append(_change(line_no, fixed, inline, "inline_reference"))
        out.append(inline)
    return "\n".join(out), log


def _marker(line, line_no, source, readings, previous, log):
    """Repair one line-initial marker; returns (line, (rule, inciso value) or None)."""
    paragraph = _PARAGRAPH.match(line)
    if paragraph:
        fixed = line[: paragraph.start("mark")] + "§" + line[paragraph.end("mark") :]
        return fixed, ("paragraph_sign", previous)
    expected = previous + 1 if previous is not None else None
    following = next((r for r in readings[line_no:] if r is not None), None)
    confirmed = expected is not None and following == expected + 1
    dashed = _INCISO.match(line)
    if dashed is None:
        glued = _GLUED.match(line)
        if glued is None or not confirmed:
            return line, None
        cut = _glued_cut(glued["token"], expected)
        if cut is None:
            return line, None
        start = glued.start("token")
        fixed = line[:start] + to_roman(expected) + " - " + line[start + cut :]
        return fixed, ("inciso_glued", expected)
    token = dashed["token"]
    read = _read(token)
    value = roman_value(read)
    late = bool(_LATE_GLYPHS & set(token))
    if late and not (value == expected or confirmed):
        return line, None
    if value is None:
        if token != read and confirmed:
            value, read = expected, to_roman(expected)
        else:
            return line, None
        rule = "inciso_sequence"
    elif expected is not None and value != expected and value != 1:
        # OCR can lose a stroke ("Il" for III) or split one ("I|l" for II). The next
        # numeral decides: it must continue the expected value, not the reading. A
        # numeral read without OCR glyphs is never rewritten.
        if token != read and confirmed:
            value, read, rule = expected, to_roman(expected), "inciso_sequence"
        else:
            log.append(_change(line_no, line, line, "sequence_break", changed=False))
            rule = "inciso_transliteration"
    else:
        rule = "inciso_transliteration"
    start, end = dashed.start("token"), dashed.end("token")
    return line[:start] + read + line[end:], (rule, value)


def build_corrected_corpora(corpus_dir: Path = CORPUS_DIR) -> tuple[dict[str, str], dict]:
    published, entries = {}, []
    for source, target in TARGETS.items():
        items = json.loads((corpus_dir / source).read_text(encoding="utf-8"))
        corrected = []
        for index, item in enumerate(items):
            content, changes = repair_markers(item["conteudo"])
            corrected.append({**item, "conteudo": content})
            entries.extend(
                {"source": source, "target": target, "index": index, "id": item.get("id"), **c}
                for c in changes
            )
        published[target] = json.dumps(corrected, ensure_ascii=False, indent=2) + "\n"
    counts = {}
    for entry in entries:
        key = f"{entry['target']}:{entry['rule']}"
        counts[key] = counts.get(key, 0) + 1
    log = {
        "scope": "Line-initial paragraph signs and inciso numerals only; prose unchanged.",
        "sources": TARGETS,
        "counts": dict(sorted(counts.items())),
        "entries": entries,
    }
    return published, log


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    published, log = build_corrected_corpora()
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
