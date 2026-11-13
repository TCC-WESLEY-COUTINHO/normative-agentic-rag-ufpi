import asyncio
import hashlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.rag_baseline.test_audit_terminal import populate

ROOT = Path(__file__).resolve().parents[3]
FROZEN = ROOT / "evaluation/results/temporal_generation_grounding_v1_001/frozen_contexts.json"
GOOD = "A defesa deve ser divulgada com a antecedência prevista."
BAD = "Fonte: art. 53, §9º."


class FakeClient:
    llm_model = "test-model"

    def __init__(self, answers):
        self.answers = iter(answers)
        self.receipts = []

    async def chat(self, **payload):
        answer = next(self.answers)
        if isinstance(answer, Exception):
            raise answer
        return answer


def run_phase(monkeypatch, tmp_path, phase, answers):
    module = importlib.import_module("rag_baseline.generation_evaluation")
    case = next(c for c in json.loads(FROZEN.read_text("utf-8")) if c["id"] == "H_citation")
    case["repetitions"] = 1
    output = tmp_path / "run"
    output.mkdir()
    (output / "frozen_contexts.json").write_text(json.dumps([case]), encoding="utf-8")
    manifest = {
        "dataset_sha256": "fixed",
        "calls_per_phase": 1,
        "settings": {"llm_model": "test-model", "max_tokens": 10},
    }
    (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    settings = SimpleNamespace(
        LLM_MODEL="test-model", LLM_MAX_TOKENS=10, EMBEDDING_MODEL="test-embedding"
    )
    monkeypatch.setattr(module, "settings_for", lambda: settings)
    monkeypatch.setattr(module, "dataset_sha256_crlf", lambda path: "fixed")
    monkeypatch.setattr(module, "client_for", lambda value: FakeClient(answers))
    asyncio.run(module.run_phase(output, phase))
    rows = (output / f"{phase}.jsonl").read_text("utf-8").splitlines()
    assert len(rows) == 1
    return json.loads(rows[0])


def test_accepted_generation_keeps_raw_and_final_apart(monkeypatch, tmp_path):
    row = run_phase(monkeypatch, tmp_path, "after", [GOOD])
    assert row["error"] is None
    assert row["raw_answer"] == GOOD
    assert row["regenerated_answer"] is None
    assert row["final_answer"] != row["raw_answer"]
    assert GOOD in row["final_answer"]
    assert row["guard_action"] == "accepted"
    assert row["guard_violations"] == []
    assert row["second_guard_violations"] == []
    assert row["fallback_reason"] is None
    assert len(row["prompts"]) == 1


def test_regeneration_records_each_attempt_and_its_prompt(monkeypatch, tmp_path):
    row = run_phase(monkeypatch, tmp_path, "after", [BAD, GOOD])
    assert row["error"] is None
    assert row["raw_answer"] == BAD
    assert row["regenerated_answer"] == GOOD
    assert GOOD in row["final_answer"]
    assert row["guard_action"] == "regenerated"
    assert row["guard_violations"]
    assert row["second_guard_violations"] == []
    assert row["fallback_reason"] is None
    assert len(row["prompts"]) == 2
    assert row["prompts"][1]["user_prompt"].startswith(row["prompts"][0]["user_prompt"])
    assert row["prompt"] == row["prompts"][0]


def test_rejected_regeneration_states_the_fallback_reason(monkeypatch, tmp_path):
    row = run_phase(monkeypatch, tmp_path, "after", [BAD, BAD])
    assert row["raw_answer"] == BAD
    assert row["regenerated_answer"] == BAD
    assert BAD not in row["final_answer"]
    assert row["guard_action"] == "fallback"
    assert row["second_guard_violations"]
    assert row["fallback_reason"] == "second_guard_rejected"


def test_failed_regeneration_states_the_fallback_reason(monkeypatch, tmp_path):
    from rag_baseline.openrouter import OpenRouterError

    row = run_phase(monkeypatch, tmp_path, "after", [BAD, OpenRouterError("simulated failure")])
    assert row["error"] is None
    assert row["raw_answer"] == BAD
    assert row["regenerated_answer"] is None
    assert row["guard_action"] == "fallback"
    assert row["regeneration_error"] == "OpenRouterError"
    assert row["fallback_reason"] == "regeneration_error"


def test_phase_without_guard_has_no_guard_decision(monkeypatch, tmp_path):
    row = run_phase(monkeypatch, tmp_path, "before", [GOOD])
    assert row["raw_answer"] == row["final_answer"] == GOOD
    assert row["guard_action"] is None
    assert row["fallback_reason"] is None
    assert len(row["prompts"]) == 1


def test_provider_failure_on_first_attempt_is_an_error_not_an_answer(monkeypatch, tmp_path):
    from rag_baseline.openrouter import OpenRouterError

    row = run_phase(monkeypatch, tmp_path, "after", [OpenRouterError("simulated failure")])
    assert row["error"] == "OpenRouterError"
    assert row["raw_answer"] is None
    assert row["final_answer"] is None
    assert row["guard_action"] is None


def digest_tree(directory):
    return {
        p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


def terminal_input(directory):
    directory.mkdir()
    populate(directory)
    return directory


def cli_input(directory):
    from rag_baseline.experiment_v2 import load_v2

    directory.mkdir()
    items, _ = load_v2()
    for filename, sector in (
        ("pos_responses.jsonl", "pos_graduacao"),
        ("grad_responses.jsonl", "graduacao"),
    ):
        rows = [
            {
                "question": q["question"],
                "collection": "ufpi_duas_regulacoes_setor",
                "references": [],
                "error": "HTTP 504",
            }
            for q in items
            if q["sector"] == sector
        ]
        (directory / filename).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )
    return directory


AUDITS = [
    ("rag_baseline.audit_terminal", terminal_input),
    ("rag_baseline.audit_cli", cli_input),
]


@pytest.mark.parametrize("name, build", AUDITS)
def test_audit_without_output_leaves_the_input_untouched(tmp_path, name, build):
    directory = build(tmp_path / "input")
    before = digest_tree(directory)
    summary = importlib.import_module(name).audit(directory)
    assert summary["review_scores"] is None
    assert digest_tree(directory) == before


@pytest.mark.parametrize("name, build", AUDITS)
def test_audit_writes_only_to_the_explicit_output(tmp_path, name, build):
    directory = build(tmp_path / "input")
    before = digest_tree(directory)
    output = tmp_path / "report"
    summary = importlib.import_module(name).audit(directory, output_dir=output)
    assert digest_tree(directory) == before
    assert sorted(p.name for p in output.iterdir()) == ["row_metrics.json", "summary.json"]
    assert json.loads((output / "summary.json").read_text("utf-8")) == summary


@pytest.mark.parametrize("name, build", AUDITS)
@pytest.mark.parametrize("inside", ["", "nested"])
def test_audit_refuses_output_inside_the_input(tmp_path, name, build, inside):
    directory = build(tmp_path / "input")
    before = digest_tree(directory)
    with pytest.raises(ValueError, match="fora do diretório de entrada"):
        importlib.import_module(name).audit(directory, output_dir=directory / inside)
    assert digest_tree(directory) == before


@pytest.mark.parametrize("name, build", AUDITS)
def test_audit_refuses_output_that_already_has_files(tmp_path, name, build):
    directory = build(tmp_path / "input")
    output = tmp_path / "report"
    output.mkdir()
    (output / "summary.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="vazio"):
        importlib.import_module(name).audit(directory, output_dir=output)
    assert (output / "summary.json").read_text("utf-8") == "{}"
