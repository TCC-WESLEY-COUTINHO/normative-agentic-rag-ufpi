"""Read the two evaluation Markdown files and the matching candidate golds, read-only.

The question is the only field that may reach the pipeline (`QuestionInput`). Reference
answers, cited devices and expected evidence are kept in `ScoringKey`, which the
runners never pass to retrieval, reranking or generation.
"""

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

FILES = {
    "graduacao": "questoes_para_avaliar_o_agente.md",
    "pos_graduacao": "questoes_para_avaliar_o_agente_pos_graduacao.md",
}
GOLDS = {
    "graduacao": "evaluation/datasets/graduacao_v2.json",
    "pos_graduacao": "evaluation/datasets/pos_graduacao_v2.json",
}
PREFIX = {"graduacao": "GRAD", "pos_graduacao": "POS"}
GOLD_PREFIX = {"graduacao": "GRAD2", "pos_graduacao": "POS2"}

_QUESTION = re.compile(r"^(\d+)\.\s+(.+?)\s*$")
_BRACKET = re.compile(r"\[([^\[\]]+)\]")
_INLINE_ARTICLE = re.compile(r"\((Art\.\s*\d+[^)]*)\)")


@dataclass(frozen=True)
class QuestionInput:
    """Everything the pipeline is allowed to see."""

    qid: str
    question: str


@dataclass(frozen=True)
class ScoringKey:
    """Used only after execution, for scoring."""

    qid: str
    sector: str
    file: str
    number: int
    reference_answer: str
    cited_devices: tuple[str, ...]
    gold_id: str | None
    gold_question_matches: bool
    expected_action: str | None
    evidence: tuple[tuple[str, str], ...]
    alternative_sets: tuple[tuple[tuple[str, str], ...], ...]
    required_facts: tuple[str, ...]
    evidence_status: str
    review_notes: tuple[str, ...] = field(default=())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    return " ".join(
        "".join(c for c in text if not unicodedata.combining(c))
        .replace("’", "'")
        .split()
    )


def parse_markdown(text: str):
    """Return [(number, question, answer)] in file order. Answers are indented lines."""
    items, current = [], None
    for line in text.splitlines():
        match = _QUESTION.match(line)
        if match and not line.startswith((" ", "\t")):
            if current:
                items.append(current)
            current = [int(match[1]), match[2], []]
        elif current is not None and line.strip():
            current[2].append(line.strip())
    if current:
        items.append(current)
    return [(n, q, " ".join(a)) for n, q, a in items]


def cited_devices(answer: str) -> tuple[str, ...]:
    found = [m.strip() for m in _BRACKET.findall(answer)]
    found += [m.strip() for m in _INLINE_ARTICLE.findall(answer)]
    return tuple(found)


_POS_CITATION = re.compile(r"Resolução CEPEX/UFPI nº 956/2025,\s*art\.\s*([^\]]+)")


def markdown_articles(answer: str) -> tuple[tuple[str, str], ...]:
    """Only the explicit 956/2025 citation form is unambiguous; graduação numbers are not."""
    result = []
    for group in _POS_CITATION.findall(answer):
        for part in group.split(","):
            match = re.match(r"\s*(\d+)\s*$", part) or (
                re.match(r"\s*(\d+)\b", part) if not result else None
            )
            if match and ("ufpi-956-2025", match[1]) not in result:
                result.append(("ufpi-956-2025", match[1]))
    return tuple(result)


def _pairs(evidence):
    return tuple((e["norm_id"], str(e["article_number"])) for e in evidence or ())


def load(repo_root: Path, data_dir: Path):
    """Return (inputs, keys, manifest). Never writes."""
    inputs, keys, files = [], [], {}
    for sector, name in FILES.items():
        raw = (Path(data_dir) / name).read_bytes()
        gold_path = Path(repo_root) / GOLDS[sector]
        gold_raw = gold_path.read_bytes()
        files[name] = dict(sha256=sha256_bytes(raw), bytes=len(raw))
        files[GOLDS[sector]] = dict(sha256=sha256_bytes(gold_raw), bytes=len(gold_raw))
        gold = {
            item["id"]: item for item in json.loads(gold_raw.decode("utf-8"))["items"]
        }
        for number, question, answer in parse_markdown(raw.decode("utf-8")):
            qid = f"{PREFIX[sector]}-{number:02d}"
            gold_id = f"{GOLD_PREFIX[sector]}-{number:03d}"
            item = gold.get(gold_id)
            matches = bool(item) and fold(
                item.get("question_original") or item["question"]
            ) == fold(question)
            notes = []
            for key in ("audit_note", "interpretive_note"):
                if item and item.get(key):
                    notes.append(f"{key}: {item[key]}")
            evidence = _pairs(item.get("evidence")) if item and matches else ()
            status = "determined_by_candidate_gold" if evidence else "not_applicable"
            if item and item.get("interpretive_note"):
                status = "determined_by_candidate_gold_needs_review"
            explicit = markdown_articles(answer)
            if not evidence and explicit:
                evidence, status = explicit, "determined_by_markdown_citation"
                notes.append(
                    "candidate gold question wording differs; evidence from Markdown citation"
                )
            elif evidence and explicit and set(explicit) != set(evidence):
                notes.append(
                    f"markdown citation {sorted(explicit)} differs from gold {sorted(evidence)}"
                )
            inputs.append(QuestionInput(qid=qid, question=question))
            keys.append(
                ScoringKey(
                    qid=qid,
                    sector=sector,
                    file=name,
                    number=number,
                    reference_answer=answer,
                    cited_devices=cited_devices(answer),
                    gold_id=gold_id if item else None,
                    gold_question_matches=matches,
                    expected_action=item.get("expected_action") if item else None,
                    evidence=evidence,
                    alternative_sets=tuple(
                        _pairs(s) for s in (item.get("alternative_evidence_sets") or ())
                    )
                    if item and matches
                    else (),
                    required_facts=tuple(item.get("required_facts") or ())
                    if item
                    else (),
                    evidence_status=status,
                    review_notes=tuple(notes),
                )
            )
    return inputs, keys, dict(files=files, duplicates=duplicates(inputs))


def _terms(text):
    return {w for w in re.findall(r"[a-z0-9]{3,}", fold(text))}


def duplicates(inputs, threshold=0.6):
    """Exact duplicates after folding and near duplicates by term Jaccard."""
    result = []
    for i, a in enumerate(inputs):
        for b in inputs[i + 1 :]:
            ta, tb = _terms(a.question), _terms(b.question)
            jaccard = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
            exact = fold(a.question) == fold(b.question)
            if exact or jaccard >= threshold:
                result.append(
                    dict(a=a.qid, b=b.qid, exact=exact, jaccard=round(jaccard, 3))
                )
    return result
