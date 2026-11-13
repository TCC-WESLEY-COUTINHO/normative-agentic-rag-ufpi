"""Real-context checks; select provider captures with CITATION_REGRESSION_RUN."""

import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from rag_baseline.corpus import load_corpus
from rag_baseline.prompts import V2_SYSTEM_PROMPT

ROOT = Path(__file__).resolve().parents[3]


def test_real_article_53_places_deadline_before_first_paragraph():
    chunk = next(
        c
        for c in load_corpus(
            ROOT / "evaluation/corpora/pos_graduacao_setor_v2.json", id_prefix="ufpi-956-2025"
        )
        if c.article_number == "53"
    )
    caput, paragraphs = chunk.content.split("- $ 1º", 1)
    assert "antecedência mínima de dez dias" in caput
    assert "dez dias" not in paragraphs
    assert chunk.article_label == "Art. 53"


def test_real_generation_does_not_assign_caput_deadline_to_paragraph_one():
    selected = os.environ.get("CITATION_REGRESSION_RUN")
    if not selected:
        pytest.skip("Select a real fixed-context run with CITATION_REGRESSION_RUN")
    path = Path(selected)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    raw = (path / "rows.jsonl").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["artifact_sha256"]["rows.jsonl"]
    rows = [json.loads(s) for s in raw.decode("utf-8").splitlines()]
    assert len(rows) >= 10
    failures = []
    for row in rows:
        assert row["calls"][0]["request"]["messages"][0]["content"] == V2_SYSTEM_PROMPT
        assert row["case_id"] == "TEMP-POS-001"
        assert "ufpi-956-2025-art-53-idx-000051" in row["final_context_ids"]
        assert row["raw_equals_service"]
        answer = row["answer"]
        assert "dez dias" in answer.lower()
        assert re.search(r"art(?:igo|\.)?\s*53\b", answer, re.I)
        if re.search(r"§\s*1(?!\d)|parágrafo\s*(?:1(?!\d)|primeiro\b)", answer, re.I):
            failures.append(row["run"])
    assert not failures, f"Unsupported paragraph-one attribution in runs {failures}"
