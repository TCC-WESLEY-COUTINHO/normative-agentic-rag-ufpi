import asyncio
import importlib
import json
from collections import Counter
from types import SimpleNamespace

import pytest


def test_natural_gold_counts_and_ambiguous_actions():
    runner = importlib.import_module("rag_baseline.experiment_v2")
    items, corpora = runner.load_v2()
    post = [q for q in items if q["sector"] == "pos_graduacao"]
    assert Counter(q["category"] for q in post) == {"direta": 8, "aberta": 8, "ambigua": 4}
    assert len(items) == 40
    assert all("segundo a Resolução" not in q["question"] for q in items)
    assert all(q["expected_action"] == "clarify" for q in post[-4:])
    assert len(corpora["ufpi-956-2025"]) == 62


def test_question_prompt_does_not_contain_hidden_labels():
    runner = importlib.import_module("rag_baseline.experiment_v2")
    q = {
        "question": "Posso cancelar?",
        "sector": "SECRET_SECTOR",
        "reference_answer": "SECRET_GOLD",
    }
    prompt = runner.user_prompt(q, [])
    assert "Posso cancelar?" in prompt
    assert "SECRET" not in prompt


def test_ambiguous_questions_have_no_norm_specific_recall():
    runner = importlib.import_module("rag_baseline.experiment_v2")
    assert runner.metrics_for({"expected_action": "clarify"}, []) is None


def test_score_requires_both_complete_answer_and_evidence():
    runner = importlib.import_module("rag_baseline.experiment_v2")
    assert runner.composite_score("answer", False, True, True, False) == 0
    assert runner.composite_score("answer", True, False, True, False) == 1
    assert runner.composite_score("answer", True, True, False, False) == 1
    assert runner.composite_score("answer", True, True, True, False) == 2
    assert runner.composite_score("clarify", True, True, False, True) == 2
    assert runner.composite_score("clarify", True, True, False, False) == 0


def test_shared_attendance_accepts_either_norm():
    from rag_baseline.models import RetrievedChunk

    runner = importlib.import_module("rag_baseline.experiment_v2")
    items, corpora = runner.load_v2()
    question = next(q for q in items if q["id"] == "GRAD2-002")
    assert question["expected_action"] == "answer"
    chunk = next(c for c in corpora["ufpi-956-2025"] if c.article_number == "20")
    result = runner.metrics_for(
        question, [RetrievedChunk(**chunk.model_dump(), rank=1, distance=0)]
    )
    assert result["evidence_complete_at_5"] == 1


def test_summary_has_category_denominators():
    runner = importlib.import_module("rag_baseline.experiment_v2")
    row = {
        "norm_id": "ufpi-956-2025",
        "condition": "isolated",
        "category": "direta",
        "metrics": {"recall_at_5": 1},
        "error": None,
    }
    summary = runner.summarize([row])
    assert summary["groups"][row["norm_id"]]["isolated"]["by_category"]["direta"]["n"] == 1


def test_two_stages_keep_all_pairs_and_reject_mutated_results(tmp_path, monkeypatch):
    runner = importlib.import_module("rag_baseline.experiment_v2")

    class FakeClient:
        receipts = []

        async def embed(self, texts):
            return [[1.0, (i + 1) / 500] for i, _ in enumerate(texts)]

        async def chat(self, **kwargs):
            assert kwargs["system_prompt"] == runner.PROMPT
            return "Resposta simulada; não constitui resultado científico."

    settings = SimpleNamespace(
        OPENROUTER_API_KEY="fake",
        EMBEDDING_MODEL="fake",
        LLM_MODEL="fake",
        LLM_MAX_TOKENS=800,
        OPENROUTER_BASE_URL="https://invalid.example",
    )
    monkeypatch.setattr(runner, "BaselineSettings", lambda **kwargs: settings)
    monkeypatch.setattr(runner, "CODE", tmp_path / "code")
    monkeypatch.setattr(runner, "client_for", lambda settings: FakeClient())
    monkeypatch.setattr(runner, "frozen_files", lambda: [])
    output = tmp_path / "simulated_pilot"
    asyncio.run(runner.run(output, "isolated"))
    saved = (output / "rows.jsonl").read_bytes()
    (output / "rows.jsonl").write_bytes(saved + b"\n")
    with pytest.raises(ValueError, match="Respostas isoladas alteradas"):
        asyncio.run(runner.run(output, "combined"))
    (output / "rows.jsonl").write_bytes(saved)
    asyncio.run(runner.run(output, "combined"))
    rows = [
        json.loads(line)
        for line in (output / "rows.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == len({(r["id"], r["condition"]) for r in rows}) == 80
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["indexed_counts"] == {
        "ufpi-956-2025": 62,
        "ufpi-177-2012": 376,
        "combined": 438,
    }
    assert manifest["status"] == "completed"
