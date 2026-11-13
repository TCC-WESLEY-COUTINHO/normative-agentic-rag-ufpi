import json

import pytest

from rag_baseline.experiment import ROOT


def test_metrics_use_fixed_classes_and_keep_failures_visible():
    from rag_baseline.routing_evaluation import routing_metrics

    rows = [
        dict(expected_scope=g, final_route=p, error=None, probe_activated=False)
        for g, p in [
            ("graduacao", "graduacao"),
            ("pos_graduacao", "graduacao"),
            (None, None),
            ("ambas", None),
        ]
    ]
    m = routing_metrics(rows)
    assert m["route_accuracy"] == 0.5
    assert m["wrong_route_rate"] == 0.25
    assert m["clarification_precision"] == 0.5
    assert m["clarification_recall"] == 1
    assert m["unnecessary_clarification_rate"] == pytest.approx(1 / 3)
    assert m["macro_f1"] == pytest.approx(1 / 3)
    rows[2]["error"] = "judge_invalid"
    m = routing_metrics(rows)
    assert m["route_accuracy"] == 0.25
    assert m["clarification_recall"] == 0
    assert m["confusion_matrix"]["esclarecer"]["error"] == 1
    rows[0]["error"] = "failed_with_route"
    assert routing_metrics(rows)["wrong_route_rate"] == 0.5


def test_calibration_rejects_test_and_has_declared_final_tie_rule():
    from rag_baseline.routing_evaluation import select_threshold

    rows = [
        dict(expected_scope=None, final_route=None, error=None, split="DEV", probe_activated=True)
    ]
    assert select_threshold({0.8: rows, 0.55: rows})["selected_threshold"] == 0.55
    with pytest.raises(ValueError, match="DEV"):
        select_threshold({0.55: [dict(rows[0], split="TEST")]})


def test_frozen_experiment_rejects_effective_model_or_endpoint_changes():
    from rag_baseline.routing_evaluation import validate_frozen

    frozen = dict(
        file_sha256={"source": "digest"},
        dev_sha256="dev",
        selected_threshold=0.7,
        config=dict(router_model="frozen-model", api_base_url="frozen-endpoint"),
    )
    validate_frozen(frozen, {"source": "digest"}, "dev", frozen["config"])
    for field in ("router_model", "api_base_url"):
        with pytest.raises(ValueError, match="configuração"):
            validate_frozen(
                frozen, {"source": "digest"}, "dev", dict(frozen["config"], **{field: "changed"})
            )


def test_git_object_reference_uses_forward_slashes_on_windows(monkeypatch):
    from rag_baseline.routing_evaluation import git_head_ref, git_worktree_hash

    assert (
        git_head_ref(r"evaluation\datasets\routing.json") == "HEAD:evaluation/datasets/routing.json"
    )
    commands = []

    def capture(command, **kwargs):
        commands.append(command)
        return "digest\n"

    monkeypatch.setattr("rag_baseline.routing_evaluation.subprocess.check_output", capture)
    assert git_worktree_hash(r"evaluation\datasets\routing.json") == "digest"
    assert commands == [["git", "hash-object", "evaluation/datasets/routing.json"]]


def test_derived_dataset_has_no_duplicate_split_leakage_or_gold_text(monkeypatch):
    from rag_baseline.routing_dataset import canonical_question, derive_dataset

    d = derive_dataset(ROOT)
    groups = {}
    for item in d["items"]:
        key = canonical_question(item["question"])
        assert key not in groups
        groups[key] = item["split"]
        assert not {"answer", "reference_answer", "evidence", "required_facts"} & item.keys()
        if item["id"].startswith(("TEMP-", "CONTROL-", "REGRESSION-", "SMOKE-")):
            assert item["split"] == "DEV"
    for split in ("DEV", "TEST"):
        assert {i["category"] for i in d["items"] if i["split"] == split} == {
            "explicit_graduacao",
            "explicit_pos",
            "cross_domain",
            "ambiguous",
        }
    assert derive_dataset(ROOT) == d
    assert d == json.loads(
        (ROOT / "evaluation/datasets/routing_v2_candidates_v1.json").read_bytes()
    )
    assert d["status"] == "exploratory_candidate"
    assert d["source_sha256_representation"] == "lf_normalized"
    assert all("\\" not in name for name in d["source_sha256"])
    from pathlib import Path

    read_bytes = Path.read_bytes
    for eol in (b"\n", b"\r\n"):

        def represented_bytes(path):
            return read_bytes(path).replace(b"\r\n", b"\n").replace(b"\n", eol)

        monkeypatch.setattr(Path, "read_bytes", represented_bytes)
        assert derive_dataset(ROOT) == d


@pytest.mark.asyncio
async def test_paired_policies_share_v1_and_exact_probe_and_count_physical_calls():
    from test_adaptive_router_v2 import Intent, service

    from rag_baseline.routing_evaluation import paired_route

    rag = service()
    intent = Intent()
    pair = await paired_route(rag, intent, "Na pós-graduação, posso trancar?", threshold=0.7)
    assert len(rag.openrouter.embeds) == 1
    assert len(rag.vector_store.calls) == 1
    assert len(rag.openrouter.judgments) == 1
    assert len(intent.calls) == 1
    assert pair["probe_sha256"] == pair["policy_rows"][1]["probe_sha256"]
    assert pair["probe_sha256"] == pair["policy_rows"][2]["probe_sha256"]
    assert pair["policy_rows"][0]["embedding_calls"] == 0
    assert [r["llm_calls"] for r in pair["policy_rows"]] == [1, 1, 2]
    assert not rag.openrouter.generations


@pytest.mark.asyncio
async def test_paired_direct_route_skips_all_additional_work():
    from test_adaptive_router_v2 import Intent, service

    from rag_baseline.routing_evaluation import paired_route

    rag = service()
    pair = await paired_route(rag, Intent("ambas"), "Compare os níveis", threshold=0.7)
    assert not rag.openrouter.embeds and not rag.openrouter.judgments
    assert all(r["final_route"] == "ambas" for r in pair["policy_rows"])
