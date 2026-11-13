import importlib
import json

import pytest

from rag_baseline.experiment_v2 import load_v2


def populate(directory):
    items, _ = load_v2()
    for filename, group, scope in (
        ("pos_pos.jsonl", "pos_graduacao", "pos_graduacao"),
        ("grad_grad.jsonl", "graduacao", "graduacao"),
        ("pos_ambos.jsonl", "pos_graduacao", "ambos"),
        ("grad_ambos.jsonl", "graduacao", "ambos"),
    ):
        rows = [
            {"question": q["question"], "sector": scope, "error": "HTTP 504"}
            for q in items
            if q["sector"] == group
        ]
        (directory / filename).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
            encoding="utf-8",
        )


def test_failed_generation_does_not_imply_zero_retrieval(tmp_path):
    populate(tmp_path)
    audit = importlib.import_module("rag_baseline.audit_terminal").audit
    result = audit(tmp_path)
    assert result["n"] == 80
    assert result["errors"] == 80
    assert result["groups"]["pos_pos.jsonl"]["answerable_n"] == 16
    assert result["groups"]["pos_pos.jsonl"]["metrics_observed_n"] == 0
    assert result["groups"]["pos_pos.jsonl"]["metrics"] is None
    assert result["review_scores"] is None


def test_auditor_rejects_scope_different_from_preselected_condition(tmp_path):
    populate(tmp_path)
    path = tmp_path / "pos_pos.jsonl"
    path.write_text(path.read_text("utf-8").replace('"pos_graduacao"', '"graduacao"'), "utf-8")
    audit = importlib.import_module("rag_baseline.audit_terminal").audit
    with pytest.raises(ValueError, match="escopo"):
        audit(tmp_path)


def test_auditor_rejects_missing_question_instead_of_dropping_it(tmp_path):
    populate(tmp_path)
    path = tmp_path / "pos_pos.jsonl"
    rows = path.read_text("utf-8").splitlines()
    path.write_text("\n".join(rows[:-1]), "utf-8")
    audit = importlib.import_module("rag_baseline.audit_terminal").audit
    with pytest.raises(ValueError, match="Perguntas"):
        audit(tmp_path)
