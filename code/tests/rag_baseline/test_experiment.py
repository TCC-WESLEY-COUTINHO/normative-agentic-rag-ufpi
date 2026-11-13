import hashlib
import json
import math
from unittest.mock import Mock

import pytest

from rag_baseline.experiment import load_gold, paired_summary, retrieval_metrics, token_f1


def test_retrieval_metrics_distinguish_norms_and_penalize_missing_evidence():
    gold = {("post", "3"), ("post", "4")}
    results = [("grad", "3"), ("post", "4"), ("post", "4")]
    metrics = retrieval_metrics(gold, results, "post")
    assert metrics["recall_at_1"] == 0
    assert metrics["recall_at_5"] == 0.5
    assert metrics["mrr_at_5"] == 0.5
    assert metrics["evidence_complete_at_5"] == 0
    assert metrics["wrong_norm_at_5"] == pytest.approx(1 / 3)
    assert metrics["ndcg_at_5"] == pytest.approx((1 / math.log2(3)) / (1 + 1 / math.log2(3)))


def test_empty_retrieval_has_zero_coverage_and_undefined_wrong_norm():
    metrics = retrieval_metrics({("post", "3")}, [], "post")
    assert metrics["recall_at_5"] == 0
    assert metrics["mrr_at_5"] == 0
    assert metrics["wrong_norm_at_5"] is None


def test_pairing_rejects_missing_or_duplicate_conditions():
    with pytest.raises(ValueError, match="par"):
        paired_summary([{"id": "a", "condition": "isolated", "norm_id": "post"}])


def test_paired_summary_keeps_zero_differences_zero():
    rows = []
    for qid, norm in [("a", "grad"), ("b", "post")]:
        for condition in ["isolated", "combined"]:
            rows.append(
                {
                    "id": qid,
                    "norm_id": norm,
                    "condition": condition,
                    "metrics": {"recall_at_5": 1.0},
                }
            )
    summary = paired_summary(rows)
    assert summary["delta_recall_at_5"] == 0
    assert summary["bootstrap_95_ci"] == [0, 0]


def test_token_f1_is_only_overlap_and_does_not_claim_semantic_correctness():
    assert token_f1("Sim, sete.", "sete") == pytest.approx(2 / 3)
    assert token_f1("", "sete") == 0


def test_frozen_gold_matches_actual_corpus(monkeypatch):
    items, corpora = load_gold()
    assert len(items) == 40
    assert {norm: len(chunks) for norm, chunks in corpora.items()} == {
        "ufpi-177-2012": 376,
        "ufpi-956-2025": 62,
    }
    from rag_baseline import experiment

    assert all("review" not in item for item in items)
    for path in experiment.DATASETS:
        assert json.loads(path.read_text(encoding="utf-8"))["status"] == "candidate_gold"
    invalid = Mock()
    invalid.read_text.return_value = json.dumps({"status": "other", "items": []})
    monkeypatch.setattr(experiment, "DATASETS", [invalid])
    with pytest.raises(ValueError, match="Este piloto exige o snapshot candidato documentado"):
        load_gold()


def test_published_artifacts_hashes_are_independent_of_checkout_eol():
    import re
    from pathlib import PurePosixPath, PureWindowsPath

    from rag_baseline.experiment import ROOT

    receipt = json.loads((ROOT / "evaluation/published_artifacts.json").read_bytes())
    assert set(receipt) == {"schema_version", "artifacts"}
    assert receipt["schema_version"] == "2.0"
    artifacts = receipt["artifacts"]
    assert isinstance(artifacts, list) and artifacts

    def check_text(value):
        if isinstance(value, str):
            assert "\\" not in value
            assert not PurePosixPath(value).is_absolute() and not PureWindowsPath(value).drive
            assert not re.search(r"[A-Za-z]:/|~/|(?<![\w./#])/", value)
            assert not re.search(
                r"h[u]man|[.]agent[-]notes|c[l]aude|c[o]dex|c[h]atgpt|ai[-]memory"
                r"|pending[_ -]*(?:review|validation)|(?:review|validation)[_ -]*pending"
                r"|awaiting[_ -]*(?:review|validation)|needs[_ -]*review",
                value,
                re.IGNORECASE,
            )
        elif isinstance(value, dict):
            for nested in value.values():
                check_text(nested)
        elif isinstance(value, list):
            for nested in value:
                check_text(nested)
        else:
            assert value is None

    check_text(receipt)
    source_ids, published_paths = set(), set()
    required = {
        "source_artifact_id",
        "source_sha256",
        "source_commit",
        "scientific_role",
        "published_path",
        "published_sha256",
        "disposition",
    }
    representations = {"lf_normalized", "crlf_normalized", "bytes_as_stored"}
    private_sources = {
        artifact["source_artifact_id"]: artifact
        for artifact in artifacts
        if artifact["disposition"] == "private_raw_only"
    }
    for artifact in artifacts:
        assert required <= artifact.keys()
        source_id = artifact["source_artifact_id"]
        assert isinstance(source_id, str) and source_id
        assert source_id not in source_ids
        source_ids.add(source_id)
        assert not PurePosixPath(source_id).is_absolute()
        assert not PureWindowsPath(source_id).drive
        assert "\\" not in source_id
        assert not re.search(r"h[u]man|[.]agent[-]notes", source_id, re.IGNORECASE)
        assert re.fullmatch(r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+", source_id)
        assert all(part not in {".", ".."} for part in source_id.split("/"))
        assert re.fullmatch(r"[0-9a-f]{40}", artifact["source_commit"])
        assert isinstance(artifact["scientific_role"], str) and artifact["scientific_role"]
        if artifact["disposition"] == "published_derived":
            assert artifact.keys() == required | {"eol_representation", "derived_from"}
            assert artifact["source_sha256"] is None
            assert artifact["eol_representation"] == "lf_normalized"
            sources = artifact["derived_from"]
            assert isinstance(sources, list)
            for source in sources:
                assert source.keys() == {"source_artifact_id", "source_sha256"}
                assert re.fullmatch(r"[0-9a-f]{64}", source["source_sha256"])
            run = source_id.split("/")[0]
            expected_sources = {
                f"{run}/{name}": private_sources[f"{run}/{name}"]["source_sha256"]
                for name in ("preservation.json", "test_results.json")
            }
            assert len(sources) == len(expected_sources)
            assert {
                source["source_artifact_id"]: source["source_sha256"] for source in sources
            } == expected_sources
            assert all(
                private_sources[source_id]["source_commit"] == artifact["source_commit"]
                for source_id in expected_sources
            )
        else:
            assert re.fullmatch(r"[0-9a-f]{64}", artifact["source_sha256"])
            if artifact["disposition"] == "private_raw_only":
                assert artifact.keys() == required
            else:
                assert artifact["disposition"] == "published"
                mandatory = required | {"eol_representation"}
                allowed = mandatory | {"historical_recorded_sha256"}
                if source_id == "decisions.md":
                    mandatory |= {"historical_receipt_date", "historical_receipt_relation"}
                    allowed |= mandatory
                    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", artifact["historical_receipt_date"])
                    assert isinstance(artifact["historical_receipt_relation"], str)
                assert mandatory <= artifact.keys() <= allowed
        if "historical_recorded_sha256" in artifact:
            history = artifact["historical_recorded_sha256"]
            assert isinstance(history, list) and history
            for record in history:
                assert (
                    {"sha256", "eol_representation"}
                    <= record.keys()
                    <= {
                        "sha256",
                        "eol_representation",
                        "recorded_in",
                        "recorded_as",
                        "source_artifact_id",
                        "recorded_at_commit",
                        "scientific_role",
                    }
                )
                assert re.fullmatch(r"[0-9a-f]{64}", record["sha256"])
                assert record["eol_representation"] in representations
                assert ("recorded_in" in record) != ("recorded_as" in record)
                if "recorded_in" in record:
                    assert (ROOT / record["recorded_in"].split("#")[0]).is_file()
                else:
                    assert record["recorded_as"] in {
                        "published_value_before_interpretive_note",
                        "published_value_before_reprojection",
                    }
                if "recorded_at_commit" in record:
                    assert re.fullmatch(r"[0-9a-f]{40}", record["recorded_at_commit"])
        if artifact["disposition"] == "private_raw_only":
            assert artifact["published_path"] is None
            assert artifact["published_sha256"] is None
            assert not (ROOT / "evaluation/results" / source_id).exists()
            continue
        assert artifact["disposition"] in {"published", "published_derived"}
        path = artifact["published_path"]
        assert isinstance(path, str) and path
        assert not PurePosixPath(path).is_absolute() and not PureWindowsPath(path).drive
        assert "\\" not in path and ".." not in PurePosixPath(path).parts
        assert path not in published_paths
        published_paths.add(path)
        assert (ROOT / path).is_file()
        assert re.fullmatch(r"[0-9a-f]{64}", artifact["published_sha256"])
        raw = (ROOT / path).read_bytes()
        lf = raw.replace(b"\r\n", b"\n")
        variants = (lf, lf.replace(b"\n", b"\r\n"))
        representation = artifact["eol_representation"]
        assert representation in representations
        for variant in variants:
            normalized = variant.replace(b"\r\n", b"\n")
            if representation == "lf_normalized":
                candidates = (normalized,)
            elif representation == "crlf_normalized":
                candidates = (normalized.replace(b"\n", b"\r\n"),)
            else:
                candidates = (normalized, normalized.replace(b"\n", b"\r\n"))
            assert artifact["published_sha256"] in {
                hashlib.sha256(candidate).hexdigest() for candidate in candidates
            }
    assert source_ids == {
        "agent_normative_integration_v1_001/REPORT.md",
        "agent_normative_integration_v1_001/execution_log.jsonl",
        "agentic_integration_audit_v1_001/REPORT.md",
        "agentic_integration_audit_v1_001/execution_log.jsonl",
        "agentic_integration_audit_v1_001/manifest.json",
        "agentic_temporal_hardening_v1_001/REPORT.md",
        "calculator_tool_routing_v1_001/REPORT.md",
        "calculator_tool_routing_v1_001/execution_log.jsonl",
        "calculator_tool_routing_v1_001/finalize_evidence.py",
        "cli_001/REPORT.md",
        "container_runtime_smoke_v1_001/REPORT.md",
        "container_runtime_smoke_v1_001/attempt_01/mounts_normative-rag-runtime-smoke-v1-controlled.json",
        "container_runtime_smoke_v1_001/attempt_01/mounts_normative-rag-runtime-smoke-v1-controlled.log",
        "container_runtime_smoke_v1_001/attempt_01/mounts_normative-rag-runtime-smoke-v1.json",
        "container_runtime_smoke_v1_001/attempt_01/mounts_normative-rag-runtime-smoke-v1.log",
        "container_runtime_smoke_v1_001/attempt_01/operations.py",
        "container_runtime_smoke_v1_001/attempt_01/repository_git_root.log",
        "container_runtime_smoke_v1_001/attempt_01/repository_realpath.log",
        "container_runtime_smoke_v1_001/attempt_01/snapshot_before.log",
        "container_runtime_smoke_v1_001/attempt_02/operations.py",
        "container_runtime_smoke_v1_001/attempt_03_before_compose_fix/mounts_normative-rag-runtime-smoke-v1-controlled.json",
        "container_runtime_smoke_v1_001/attempt_03_before_compose_fix/mounts_normative-rag-runtime-smoke-v1-controlled.log",
        "container_runtime_smoke_v1_001/attempt_03_before_compose_fix/mounts_normative-rag-runtime-smoke-v1-invalid-registry.json",
        "container_runtime_smoke_v1_001/attempt_03_before_compose_fix/mounts_normative-rag-runtime-smoke-v1-invalid-registry.log",
        "container_runtime_smoke_v1_001/attempt_03_before_compose_fix/mounts_normative-rag-runtime-smoke-v1-missing-index.json",
        "container_runtime_smoke_v1_001/attempt_03_before_compose_fix/mounts_normative-rag-runtime-smoke-v1-missing-index.log",
        "container_runtime_smoke_v1_001/attempt_03_before_compose_fix/mounts_normative-rag-runtime-smoke-v1-missing-provider.json",
        "container_runtime_smoke_v1_001/attempt_03_before_compose_fix/mounts_normative-rag-runtime-smoke-v1-missing-provider.log",
        "container_runtime_smoke_v1_001/attempt_03_before_compose_fix/mounts_normative-rag-runtime-smoke-v1.json",
        "container_runtime_smoke_v1_001/attempt_03_before_compose_fix/mounts_normative-rag-runtime-smoke-v1.log",
        "container_runtime_smoke_v1_001/attempt_03_before_compose_fix/operations.py",
        "container_runtime_smoke_v1_001/diff_staged_initial_raw_output.log",
        "container_runtime_smoke_v1_001/execution_log.jsonl",
        "container_runtime_smoke_v1_001/finalize_evidence.py",
        "container_runtime_smoke_v1_001/initial_audit.json",
        "container_runtime_smoke_v1_001/linux_incomplete_test_context_red/linux_tests_full.log",
        "container_runtime_smoke_v1_001/linux_incomplete_test_context_red/linux_tests_rag_baseline.log",
        "container_runtime_smoke_v1_001/local_commits_before_evidence.json",
        "container_runtime_smoke_v1_001/mounts_normative-rag-runtime-smoke-v1-controlled.json",
        "container_runtime_smoke_v1_001/mounts_normative-rag-runtime-smoke-v1-controlled.log",
        "container_runtime_smoke_v1_001/mounts_normative-rag-runtime-smoke-v1-invalid-registry.json",
        "container_runtime_smoke_v1_001/mounts_normative-rag-runtime-smoke-v1-invalid-registry.log",
        "container_runtime_smoke_v1_001/mounts_normative-rag-runtime-smoke-v1-missing-index.json",
        "container_runtime_smoke_v1_001/mounts_normative-rag-runtime-smoke-v1-missing-index.log",
        "container_runtime_smoke_v1_001/mounts_normative-rag-runtime-smoke-v1-missing-provider.json",
        "container_runtime_smoke_v1_001/mounts_normative-rag-runtime-smoke-v1-missing-provider.log",
        "container_runtime_smoke_v1_001/mounts_normative-rag-runtime-smoke-v1.json",
        "container_runtime_smoke_v1_001/mounts_normative-rag-runtime-smoke-v1.log",
        "container_runtime_smoke_v1_001/operations.py",
        "container_runtime_smoke_v1_001/packaging_before.json",
        "container_runtime_smoke_v1_001/post_runtime_audit.py",
        "container_runtime_smoke_v1_001/preservation_before.json",
        "container_runtime_smoke_v1_001/repository_git_root.log",
        "container_runtime_smoke_v1_001/repository_realpath.log",
        "container_runtime_smoke_v1_001/snapshot_before.log",
        "container_runtime_smoke_v1_001/verification.json",
        "conversation_memory_followups_v1_001/REPORT.md",
        "conversation_memory_followups_v1_001/execution_log.jsonl",
        "datasets/VALIDATION_V2.md",
        "datasets/agentic_smoke_v1.json",
        "datasets/graduacao_v1.json",
        "datasets/graduacao_v1.md",
        "datasets/graduacao_v2.json",
        "datasets/graduacao_v2.md",
        "datasets/pos_graduacao_v1.json",
        "datasets/pos_graduacao_v1.md",
        "datasets/pos_graduacao_v2.json",
        "datasets/pos_graduacao_v2.md",
        "datasets/routing_v2_candidates_v1.json",
        "datasets/temporal_candidates_v1.json",
        "datasets/temporal_candidates_v2.json",
        "datasets/temporal_generation_grounding_v1.json",
        "datasets/temporal_graduacao_v1.json",
        "datasets/temporal_pos_v1.json",
        "decisions.md",
        "normative_tool_facade_v1_001/REPORT.md",
        "normative_tool_facade_v1_001/execution_log.jsonl",
        "normative_tool_facade_v1_001/manifest.json",
        "pilot_001/REPORT.md",
        "pilot_001/review_template.json",
        "pilot_001/summary.json",
        "pilot_003/PRIMARY_ANALYSIS.md",
        "pilot_003/REPORT.md",
        "pilot_003/audit.json",
        "pilot_003/primary_summary.json",
        "pilot_003/review_template.json",
        "pilot_003/rows.jsonl",
        "pilot_003/summary.json",
        "pre_freeze_conversation_policy_compact_references_v1_001/REPORT.md",
        "pre_freeze_conversation_policy_compact_references_v1_001/audit.py",
        "pre_freeze_conversation_policy_compact_references_v1_001/execution_log.jsonl",
        "pre_freeze_conversation_policy_compact_references_v1_001/interrupted_work_audit.json",
        "pre_freeze_conversation_policy_compact_references_v1_001/local_runtime.py",
        "pre_freeze_conversation_policy_compact_references_v1_001/review_findings.json",
        "pre_freeze_conversation_policy_compact_references_v1_001/runtime_smoke.py",
        "pre_freeze_conversation_policy_compact_references_v1_001/test_results.json",
        "pre_freeze_defect_correction_v1_001/REPORT.md",
        "pre_freeze_defect_correction_v1_001/compatibility.log",
        "pre_freeze_defect_correction_v1_001/decision_log.jsonl",
        "pre_freeze_defect_correction_v1_001/execution_log.jsonl",
        "pre_freeze_defect_correction_v1_001/focused_green.log",
        "pre_freeze_defect_correction_v1_001/full_final.junit.xml",
        "pre_freeze_defect_correction_v1_001/full_final.log",
        "pre_freeze_defect_correction_v1_001/full_final_router_contract.junit.xml",
        "pre_freeze_defect_correction_v1_001/full_final_router_contract.log",
        "pre_freeze_defect_correction_v1_001/full_final_with_headings.junit.xml",
        "pre_freeze_defect_correction_v1_001/full_final_with_headings.log",
        "pre_freeze_defect_correction_v1_001/guard_and_regressions_final.log",
        "pre_freeze_defect_correction_v1_001/preservation_before.json",
        "pre_freeze_defect_correction_v1_001/rag_baseline.junit.xml",
        "pre_freeze_defect_correction_v1_001/rag_baseline.log",
        "pre_freeze_defect_correction_v1_001/rag_baseline_final.junit.xml",
        "pre_freeze_defect_correction_v1_001/rag_baseline_final.log",
        "pre_freeze_defect_correction_v1_001/reproduction_workspace.json",
        "pre_freeze_defect_correction_v1_001/router_subtype_red.log",
        "pre_freeze_defect_correction_v1_001/tdd_red.log",
        "pre_freeze_defect_correction_v1_001/test_results.json",
        "pre_freeze_defect_correction_v1_001/verification.json",
        "pre_freeze_explicit_sector_temporal_fallback_v1_001/REPORT.md",
        "pre_freeze_explicit_sector_temporal_fallback_v1_001/audit.py",
        "pre_freeze_explicit_sector_temporal_fallback_v1_001/case_b_diagnosis.json",
        "pre_freeze_explicit_sector_temporal_fallback_v1_001/execution_log.jsonl",
        "pre_freeze_explicit_sector_temporal_fallback_v1_001/review_findings.json",
        "pre_freeze_explicit_sector_temporal_fallback_v1_001/test_results.json",
        "pre_freeze_historical_snapshot_local_runtime_v1_001/REPORT.md",
        "pre_freeze_historical_snapshot_local_runtime_v1_001/audit.py",
        "pre_freeze_historical_snapshot_local_runtime_v1_001/execution_log.jsonl",
        "pre_freeze_historical_snapshot_local_runtime_v1_001/local_runtime.py",
        "pre_freeze_historical_snapshot_local_runtime_v1_001/review_findings.json",
        "pre_freeze_historical_snapshot_local_runtime_v1_001/root_cause.json",
        "pre_freeze_historical_snapshot_local_runtime_v1_001/test_results.json",
        "pre_freeze_ux_answer_reliability_v2_001/REPORT.md",
        "pre_freeze_ux_answer_reliability_v2_001/decision_log.jsonl",
        "pre_freeze_ux_answer_reliability_v2_001/execution_log.jsonl",
        "pre_freeze_ux_answer_reliability_v2_001/execution_summary.json",
        "pre_freeze_ux_answer_reliability_v2_001/preservation.json",
        "pre_freeze_ux_answer_reliability_v2_001/regression_cases.json",
        "pre_freeze_ux_answer_reliability_v2_001/review_findings.json",
        "pre_freeze_ux_answer_reliability_v2_001/test_results.json",
        "pre_freeze_ux_dataset_diagnostic_v2_001/REPORT.md",
        "pre_freeze_ux_dataset_diagnostic_v2_001/data_inventory.json",
        "pre_freeze_ux_dataset_diagnostic_v2_001/dataset_run.jsonl",
        "pre_freeze_ux_dataset_diagnostic_v2_001/dataset_usage_audit.json",
        "pre_freeze_ux_dataset_diagnostic_v2_001/decision_log.jsonl",
        "pre_freeze_ux_dataset_diagnostic_v2_001/execution_log.jsonl",
        "pre_freeze_ux_dataset_diagnostic_v2_001/execution_summary.json",
        "pre_freeze_ux_dataset_diagnostic_v2_001/preservation.json",
        "pre_freeze_ux_dataset_diagnostic_v2_001/regression_cases.json",
        "pre_freeze_ux_dataset_diagnostic_v2_001/review_cases.jsonl",
        "pre_freeze_ux_dataset_diagnostic_v2_001/review_findings.json",
        "pre_freeze_ux_dataset_diagnostic_v2_001/router_diagnostics.json",
        "pre_freeze_ux_dataset_diagnostic_v2_001/test_results.json",
        "retrieval_strategies_v1_001/REPORT.md",
        "retrieval_strategies_v1_001/execution_log.jsonl",
        "retrieval_strategies_v1_001/manifest.json",
        "runtime_registration_packaging_v1_001/REPORT.md",
        "runtime_registration_packaging_v1_001/execution_log.jsonl",
        "runtime_registration_packaging_v1_001/finalize_evidence.py",
        "runtime_registration_packaging_v1_001/preservation_before.json",
        "runtime_registration_packaging_v1_001/pytest_client.txt",
        "runtime_registration_packaging_v1_001/pytest_full.txt",
        "runtime_registration_packaging_v1_001/pytest_rag_baseline.txt",
        "runtime_registration_packaging_v1_001/pytest_runtime.txt",
        "runtime_registration_packaging_v1_001/pytest_service.txt",
        "runtime_registration_packaging_v1_001/tdd_green_initial.txt",
        "runtime_registration_packaging_v1_001/tdd_integration_green.txt",
        "runtime_registration_packaging_v1_001/tdd_lifecycle_green.txt",
        "runtime_registration_packaging_v1_001/tdd_red.txt",
        "runtime_registration_packaging_v1_001/tdd_review_green.txt",
        "runtime_registration_packaging_v1_001/tdd_review_red.txt",
        "runtime_registration_packaging_v1_001/tdd_review_red_confirmed.txt",
        "runtime_registration_packaging_v1_001/test_results.json",
        "runtime_registration_packaging_v1_001/verification.json",
        "runtime_registration_packaging_v1_001/verification_initial.json",
        "structured_normative_output_v1_001/REPORT.md",
        "structured_normative_output_v2_001/REPORT.md",
        "tcc_ui_integration_v1_001/REPORT.md",
        "tcc_ui_integration_v1_001/attempt_01_env_configuration/local_smoke.log",
        "tcc_ui_integration_v1_001/attempt_01_env_configuration/temporary_workspace.json",
        "tcc_ui_integration_v1_001/evidence_audit.py",
        "tcc_ui_integration_v1_001/execution_log.jsonl",
        "tcc_ui_integration_v1_001/focused_final.log",
        "tcc_ui_integration_v1_001/full.junit.xml",
        "tcc_ui_integration_v1_001/full.log",
        "tcc_ui_integration_v1_001/full_final.log",
        "tcc_ui_integration_v1_001/local_smoke.log",
        "tcc_ui_integration_v1_001/preservation_before.json",
        "tcc_ui_integration_v1_001/review_regression_green.log",
        "tcc_ui_integration_v1_001/review_regression_red.log",
        "tcc_ui_integration_v1_001/tdd_green.log",
        "tcc_ui_integration_v1_001/tdd_green_final.log",
        "tcc_ui_integration_v1_001/tdd_red.log",
        "tcc_ui_integration_v1_001/tdd_red_contract.log",
        "tcc_ui_integration_v1_001/temporary_workspace.json",
        "tcc_ui_integration_v1_001/test_results.json",
        "temporal_evolution_v1_001/comparison.json",
        "temporal_generation_grounding_v1_001/REPORT.md",
        "terminal_ui_001/VERIFICATION.md",
        "typed_normative_transport_v1_001/REPORT.md",
        "typed_normative_transport_v1_001/execution_log.jsonl",
        "protocol.md",
        "protocol_agentic_v1.md",
        "protocol_router_v2_v1.md",
        "protocol_temporal_v1.md",
        "protocol_v2.md",
        "publication_projection.json",
        "agentic_integration_audit_v1_001/preservation_before.json",
        "agentic_smoke_comparison_001/OBSERVATIONS.md",
        "agentic_temporal_hardening_v1_001/preservation.json",
        "agentic_temporal_hardening_v1_001/preservation_before.json",
        "agent_normative_integration_v1_001/preservation_before.json",
        "calculator_tool_routing_v1_001/preservation_before.json",
        "cli_003/REPORT.md",
        "conversation_memory_followups_v1_001/preservation_before.json",
        "failure_analysis_v1/baseline_001/preservation.json",
        "failure_analysis_v1/preservation_after.json",
        "failure_analysis_v1/REPORT.md",
        "normative_tool_facade_v1_001/preservation_before.json",
        "retrieval_strategies_v1_001/preservation_before.json",
        "router_v2_exploratory_001/preservation_after.json",
        "router_v2_exploratory_001/preservation_before.json",
        "router_v2_exploratory_001/REPORT.md",
        "structured_normative_output_v1_001/annotation_protocol.json",
        "structured_normative_output_v1_001/preservation_before.json",
        "structured_normative_output_v2_001/preservation_before.json",
        "temporal_evolution_v1_001/preservation_after.json",
        "temporal_evolution_v1_001/preservation_before.json",
        "temporal_evolution_v1_001/REPORT.md",
        "temporal_generation_grounding_v1_001/preservation_before.json",
        "terminal_ui_001/PRIMARY_ANALYSIS.md",
        "terminal_ui_001/REPORT.md",
        "typed_normative_transport_v1_001/decision_log.jsonl",
        "typed_normative_transport_v1_001/preservation_before.json",
    }
    provenance_fields = (
        "source_artifact_id",
        "published_path",
        "source_sha256",
        "source_commit",
        "disposition",
        "derived_from",
        "historical_recorded_sha256",
    )
    provenance = [
        {key: artifact[key] for key in provenance_fields if key in artifact}
        for artifact in sorted(artifacts, key=lambda artifact: artifact["source_artifact_id"])
    ]
    canonical = json.dumps(
        provenance, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    assert (
        hashlib.sha256(canonical).hexdigest()
        == "61442ea457638c5a2b64612565cfa52f5439a79f1ae67d2ac5e99b47b5e2ae3e"
    )
    assert {
        artifact["source_artifact_id"]
        for artifact in artifacts
        if artifact["disposition"] == "private_raw_only"
    } == {
        "pre_freeze_ux_answer_reliability_v2_001/execution_log.jsonl",
        "pre_freeze_ux_answer_reliability_v2_001/preservation.json",
        "pre_freeze_ux_answer_reliability_v2_001/test_results.json",
        "pre_freeze_ux_dataset_diagnostic_v2_001/execution_log.jsonl",
        "pre_freeze_ux_dataset_diagnostic_v2_001/preservation.json",
        "pre_freeze_ux_dataset_diagnostic_v2_001/test_results.json",
    }


def test_frozen_audit_reads_review_schema_after_byte_verification(monkeypatch):
    from copy import deepcopy
    from pathlib import Path

    from rag_baseline import audit_v2
    from rag_baseline.experiment import ROOT

    frozen = ROOT / "evaluation/results/pilot_003"
    output = ROOT / "offline-input"
    report = ROOT / "offline-report"
    read_text = Path.read_text
    documents = {}
    for name in ("manifest.json", "summary.json", "primary_summary.json", "blinding_key.json"):
        documents[output / name] = read_text(frozen / name, encoding="utf-8")
    rows = [
        json.loads(line) for line in read_text(frozen / "rows.jsonl", encoding="utf-8").splitlines()
    ]
    template_name = "review_template.json"
    documents[output / template_name] = read_text(frozen / template_name, encoding="utf-8")
    documents[output / "rows.jsonl"] = "\n".join(json.dumps(row) for row in rows)
    manifest = json.loads(documents[output / "manifest.json"])
    manifest["file_sha256"] = {"code/src/rag_baseline/experiment_v2.py": "expected"}
    documents[output / "manifest.json"] = json.dumps(manifest)
    originals = dict(documents)
    saved, events = {}, []
    metrics_for = audit_v2.metrics_for

    def checked_metrics(row, chunks):
        assert events and events[0] == "bytes_verified"
        return metrics_for(row, chunks)

    def digest(path):
        if path == ROOT / "code/src/rag_baseline/experiment_v2.py":
            events.append("bytes_verified")
            return "expected"
        return "row-digest"

    exists = Path.exists
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda path, **kw: documents[path] if path in documents else read_text(path, **kw),
    )
    monkeypatch.setattr(
        Path, "exists", lambda path: False if path == report else path in documents or exists(path)
    )
    monkeypatch.setattr(Path, "mkdir", lambda path, **kw: None)
    monkeypatch.setattr(audit_v2, "sha256", digest)
    monkeypatch.setattr(audit_v2, "metrics_for", checked_metrics)
    monkeypatch.setattr(
        audit_v2, "save_json", lambda path, value: saved.update({path: deepcopy(value)})
    )
    result = audit_v2.audit(output, report)
    assert result["metrics_recomputed_equal"] and result["summary_recomputed_equal"]
    assert result["primary_summary_recomputed_equal"]
    assert result["review_scores_filled"] == 0
    assert report / "review_template.json" in saved
    assert documents == originals
    for score in (0, 1, 2):
        changed = deepcopy(rows)
        changed[0]["review_score_0_2"] = score
        documents[output / "rows.jsonl"] = "\n".join(json.dumps(row) for row in changed)
        with pytest.raises(ValueError):
            audit_v2.audit(output, report)
    documents[output / "rows.jsonl"] = originals[output / "rows.jsonl"]
    missing = deepcopy(rows)
    missing[0].pop("review_score_0_2")
    documents[output / "rows.jsonl"] = "\n".join(json.dumps(row) for row in missing)
    with pytest.raises(KeyError, match="review_score_0_2"):
        audit_v2.audit(output, report)
    documents[output / "rows.jsonl"] = originals[output / "rows.jsonl"]
    documents.pop(output / template_name)
    audit_v2.audit(output, report)
    assert report / template_name in saved
    documents[output / template_name] = originals[output / template_name]
    form = json.loads(documents[output / template_name])
    form[0]["score_0_2"] = 2
    documents[output / template_name] = json.dumps(form)
    with pytest.raises(ValueError, match="existente modificado"):
        audit_v2.audit(output, report)
    events.clear()
    monkeypatch.setattr(audit_v2, "sha256", lambda path: "different")
    with pytest.raises(ValueError, match="Snapshot"):
        audit_v2.audit(output, report)
    assert not events
