"""Mutation checks for exploratory measurements, independent of provider access."""

import asyncio
import copy
from pathlib import Path

import pytest
from evaluation.exploratory.battery import parse_sse, validate_output
from evaluation.exploratory.catalog import build_plan, validate_plan
from evaluation.exploratory.evaluate import evaluate_turn, summarize
from evaluation.exploratory.service_observer import Budget, BudgetStop, sanitize

ROOT = Path(__file__).resolve().parents[3]


def sample():
    case = dict(
        case_id="C",
        category="C1",
        conversation_id="A",
        turn=1,
        question="Qual o prazo?",
        expected=dict(
            status=["ANSWER"],
            sector="graduacao",
            unequivocal_continuation=True,
            sector_must_not_be=["pos_graduacao"],
            forbidden_terms=[],
            evidence=[dict(norm_id="ufpi-177-2012", article_number="115")],
        ),
    )
    run = dict(
        case_id="C",
        conversation_id="A",
        turn=1,
        question=case["question"],
        request_id="r",
        response_request_id="r",
        response_thread_id="A",
        response_question=case["question"],
        executed=True,
        antecedent_available=True,
        sector="graduacao",
        status="ANSWER",
        core_status="accepted",
        final_answer="Pedido em 3 dias.",
        raw_generation="Pedido em 3 dias.",
        observed_final_answer="Pedido em 3 dias.",
        sse_ok=True,
        correlation_id="op",
        observed_correlation_id="op",
        references=[dict(norm_id="ufpi-177-2012", article="115")],
        chunks=[dict(norm_id="ufpi-177-2012", article_number="115", content="Pedido em 3 dias.")],
    )
    return case, run


def check(change, key):
    case, run = sample()
    run.update(change)
    assert evaluate_turn(case, run)[key]["verdict"] == "fail"


def test_conversation_id_swap():
    check(dict(conversation_id="B"), "association")


def test_sector_swap():
    check(dict(sector="pos_graduacao"), "routing")


def test_question_answer_swap():
    check(dict(response_question="Outra pergunta"), "association")


def test_response_content_swap_detected_against_graph():
    check(dict(final_answer="Resposta de outra conversa"), "association")


def test_wrong_norm_reference():
    check(dict(references=[dict(norm_id="ufpi-956-2025", article="115")]), "reference")


def test_wrong_applied_year():
    case, run = sample()
    case["expected"]["requested_year"] = 2023
    run["final_answer"] = "Em 2025 aplica-se a regra."
    assert evaluate_turn(case, run)["temporal"]["verdict"] == "fail"


def test_fallback_is_not_substantive_answer():
    check(dict(core_status="fallback"), "task_completion")


def test_sse_failure_cannot_be_ignored():
    check(dict(sse_ok=False), "transport")


def test_not_run_is_never_pass():
    case, run = sample()
    run["executed"] = False
    assert {v["verdict"] for v in evaluate_turn(case, run).values()} == {"not_run"}


def test_raw_and_final_are_evaluated_separately():
    case, run = sample()
    run.update(raw_generation="Art. 999, 30 dias.", final_answer="Pedido em 3 dias.")
    result = evaluate_turn(case, run)
    assert result["generation_changed"]["verdict"] == "fail"
    assert result["unsupported_claim"]["verdict"] == "unknown"


def test_denominator_excludes_unknown_and_not_run():
    rows = [
        dict(category="G", checks={"routing": dict(verdict=v)})
        for v in ["pass", "fail", "unknown", "not_run"]
    ]
    metric = summarize(rows)["overall"]["routing"]
    assert metric["numerator"] == 1 and metric["denominator"] == 2
    assert metric["unknown"] == 1 and metric["not_run"] == 1


def test_boolean_is_not_integer():
    case, run = sample()
    run["turn"] = True
    assert evaluate_turn(case, run)["association"]["verdict"] == "fail"


def test_answer_without_evidence_is_not_grounded():
    case, run = sample()
    run["chunks"] = []
    assert evaluate_turn(case, run)["unsupported_claim"]["verdict"] == "unknown"
    assert evaluate_turn(case, run)["task_completion"]["verdict"] == "unknown"


def test_cost_limit_stops():
    budget = Budget(3, 3, 0.01)
    budget.before(
        "/chat/completions",
        dict(
            model="qwen/qwen3-30b-a3b-instruct-2507",
            messages=[dict(role="user", content="question")],
            max_tokens=800,
        ),
    )
    with pytest.raises(BudgetStop):
        budget.after({"usage": {"cost": 0.01}})
    with pytest.raises(BudgetStop):
        budget.before(
            "/chat/completions",
            dict(
                model="qwen/qwen3-30b-a3b-instruct-2507",
                messages=[dict(role="user", content="question")],
                max_tokens=800,
            ),
        )
    assert budget.budget_stopped


def test_missing_cost_stops():
    budget = Budget(3, 3, 1)
    with pytest.raises(BudgetStop):
        budget.after({"usage": {}})
    assert budget.budget_stopped and not budget.cost_reliable


def test_boolean_cost_is_rejected():
    with pytest.raises(BudgetStop):
        Budget(1, 1, 1).after({"usage": {"cost": True}})


def test_request_limit_stops_before_next_request():
    budget = Budget(1, 2, 1)
    budget.before(
        "/chat/completions",
        dict(
            model="qwen/qwen3-30b-a3b-instruct-2507",
            messages=[dict(role="user", content="question")],
            max_tokens=800,
        ),
    )
    budget.after({"usage": {"cost": 0}})
    with pytest.raises(BudgetStop):
        budget.before(
            "/chat/completions",
            dict(
                model="qwen/qwen3-30b-a3b-instruct-2507",
                messages=[dict(role="user", content="question")],
                max_tokens=800,
            ),
        )
    assert budget.chat_requests == 1


def test_embedding_request_limit_is_separate():
    budget = Budget(2, 1, 1)
    budget.before(
        "/embeddings", dict(model="openai/text-embedding-3-small", input=["embedding fixture text"])
    )
    budget.after({"usage": {"cost": 0}})
    with pytest.raises(BudgetStop):
        budget.before(
            "/embeddings",
            dict(model="openai/text-embedding-3-small", input=["embedding fixture text"]),
        )
    assert budget.chat_requests == 0 and budget.embedding_requests == 1


def test_plan_over_160_fails():
    with pytest.raises(ValueError):
        validate_plan([{}] * 161)


def test_results_output_rejected():
    with pytest.raises(ValueError):
        validate_output(ROOT / "evaluation/results/new", ROOT)


def test_any_repository_output_rejected():
    with pytest.raises(ValueError):
        validate_output(ROOT / "evaluation/exploratory/out", ROOT)


def test_catalog_counts_and_duplicates():
    plan, cases = build_plan(ROOT)
    assert plan["user_messages"] == len(cases) == 160
    assert plan["messages_by_category"] == dict(G=80, C1=4, C2=21, B=10, I=8, D=8, T=14, S=8, L=7)
    assert sum(bool(c["duplicate_of"]) for c in cases if c["category"] == "G") >= 20
    assert all(c["expected"] for c in cases)


def test_clarify_v2_does_not_append_sector_reply():
    _, cases = build_plan(ROOT)
    for case in cases:
        if (
            case.get("version") == "v2"
            and case.get("labels", {}).get("expected_action") == "clarify"
        ):
            assert case["turn"] == 1
            assert case["expected"]["status"] == ["CLARIFICATION"]


def test_second_call_conversation_is_exact():
    from evaluation.exploratory.catalog import INITIAL

    _, cases = build_plan(ROOT)
    assert [c["question"] for c in cases if c["category"] == "C1"] == [
        INITIAL,
        "graduação",
        "E qual é o prazo para fazer esse pedido?",
        "e como fazer requerimento?",
    ]
    followups = [c for c in cases if c["category"] == "C2"]
    assert len({c["conversation_id"] for c in followups}) == 7
    assert all(c["question"] == INITIAL for c in followups if c["turn"] == 1)


def test_all_candidate_questions_are_preserved():
    from evaluation.exploratory.catalog import dataset_rows

    _, cases = build_plan(ROOT)
    for dataset in {c["dataset"] for c in cases if c["category"] == "G"}:
        source = dataset_rows(ROOT / dataset)
        actual = [c for c in cases if c["dataset"] == dataset]
        assert len(actual) == len(source) == 20
        assert [(c["source_case_id"], c["question"]) for c in actual] == [
            (r["id"], r["question"]) for r in source
        ]


def test_sse_requires_done_and_final_message():
    with pytest.raises(ValueError):
        parse_sse(['data: {"type":"message","content":{"type":"ai","content":"x"}}', ""])


def test_sse_error_even_with_done():
    with pytest.raises(ValueError):
        parse_sse(['data: {"type":"error","content":"failed"}', "", "data: [DONE]", ""])


def test_sse_preserves_authoritative_message():
    result = parse_sse(
        ['data: {"type":"message","content":{"type":"ai","content":"x"}}', "", "data: [DONE]", ""]
    )
    assert result["content"] == "x"


def test_sse_rejects_typed_content_swap():
    with pytest.raises(ValueError):
        parse_sse(
            [
                'data: {"type":"message","content":{"type":"ai","content":"x","normative_result":{"status":"ANSWER","answer":"y"}}}',
                "",
                "data: [DONE]",
                "",
            ]
        )


def test_system_prompts_and_reasoning_are_not_persisted():
    safe = sanitize(
        dict(
            messages=[
                dict(role="system", content="private instructions"),
                dict(role="user", content="my question"),
            ],
            reasoning="private",
        )
    )
    assert "private" not in str(safe)
    assert safe["messages"][0]["content_hash"]
    assert "content" not in safe["messages"][1]
    assert safe["messages"][1]["content_hash"]


def test_unequivocal_followup_reclarification_fails():
    check(dict(status="CLARIFICATION"), "continuity")


def test_reference_only_text_is_excluded_from_body_claims():
    case, run = sample()
    run["final_answer"] += "\n\nReferências:\nArt. 999. Em 2025."
    assert evaluate_turn(case, run)["unsupported_claim"]["verdict"] == "unknown"


def test_unknown_fact_match_never_certifies_accuracy():
    case, run = sample()
    case["expected"]["required_facts"] = ["Pedido em 3 dias."]
    assert evaluate_turn(case, run)["required_facts"]["verdict"] == "unknown"


def test_observer_record_failure_is_contained(tmp_path):
    from evaluation.exploratory.service_observer import TraceWriter

    writer = TraceWriter(tmp_path / "trace.jsonl")

    def broken_extraction():
        raise RuntimeError("extraction failed")

    writer.record("generation", broken_extraction)
    assert writer.dropped_records == 1
    writer.record("next", {"value": 1})
    assert '"next"' in writer.path.read_text(encoding="utf-8")


def test_mounted_index_is_rejected(tmp_path):
    from evaluation.exploratory.service_observer import validate_runtime_paths

    index = tmp_path / "index"
    index.mkdir()
    state = tmp_path / "state.sqlite"
    state.touch()
    with pytest.raises(ValueError, match="mounted index"):
        validate_runtime_paths(ROOT, tmp_path, index, state, index)


def test_historical_caveat_is_not_current_validity_claim():
    case, run = sample()
    case["expected"]["historical_wording"] = True
    run["final_answer"] = "Não é possível afirmar que está vigente hoje."
    assert evaluate_turn(case, run)["temporal"]["verdict"] == "unknown"


def test_cross_turn_inconsistency_has_excerpts():
    from evaluation.exploratory.evaluate import cross_turn_findings

    case, a = sample()
    b = copy.deepcopy(a)
    a["effective_question"] = b["effective_question"] = "Segunda chamada na graduação"
    b.update(turn=2, final_answer="Pedido em 5 dias.")
    findings = cross_turn_findings([a, b])
    assert findings and findings[0]["classification"] == "cross_turn_inconsistency"
    assert findings[0]["excerpts"] and findings[0]["articles"]


def test_async_observer_records_original_exception(monkeypatch):
    from evaluation.exploratory.service_observer import install_observers

    from rag_baseline import agentic
    from rag_baseline.openrouter import OpenRouterClient
    from rag_baseline.router import NormativeRouter
    from rag_baseline.scope_gate import NormativeScopeGate
    from rag_baseline.service import RagService
    from rag_baseline.tool_facade import NormativeRagFacade
    from rag_baseline.versioning import VersionFilter

    class Recorder:
        dropped_records = 0
        records = []

        def record(self, event, factory):
            try:
                self.records.append((event, factory()))
            except Exception:
                self.dropped_records += 1

    error = LookupError("generation fixture failed")

    async def broken_generate(*args, **kwargs):
        raise error

    for obj, name in [
        (OpenRouterClient, "_post"),
        (RagService, "generate"),
        (NormativeRagFacade, "query"),
        (NormativeRouter, "route"),
        (NormativeScopeGate, "classify"),
        (VersionFilter, "apply"),
        (agentic.AgenticRagService, "query"),
        (agentic, "classify_temporal_intent"),
    ]:
        monkeypatch.setattr(obj, name, getattr(obj, name))
    monkeypatch.setattr(RagService, "generate", broken_generate)
    recorder = Recorder()
    install_observers(recorder, Budget(10, 10, 1))
    with pytest.raises(LookupError) as caught:
        asyncio.run(RagService.generate(None, "question", []))
    assert caught.value is error
    assert recorder.dropped_records == 0
    assert recorder.records[0][1]["error"] == "LookupError"


def test_continuation_independent_action_is_functional_failure():
    case, row = sample()
    row["conversation_action"] = "NORMATIVE_RAG"
    checks = evaluate_turn(case, row)
    assert checks["continuity"]["verdict"] == "fail"
    assert "NORMATIVE_RAG" in str(checks["continuity"]["detail"])


def test_initial_clarification_is_not_redundant():
    _, cases = build_plan(ROOT)
    case = next(c for c in cases if c["category"] == "C1" and c["turn"] == 1)
    _, row = sample()
    row.update(status="CLARIFICATION", final_answer="Graduação ou pós-graduação?")
    checks = evaluate_turn(case, row)
    assert checks["clarification"]["verdict"] == "pass"
    assert checks["redundant_clarification"]["verdict"] == "unknown"


def test_chunk_identity_uses_real_chunk_id_when_metadata_is_missing():
    case, row = sample()
    row["chunks"] = [
        dict(
            id="ufpi-177-2012-art-115-idx-000114",
            norm_id=None,
            article_number="115",
            content="Pedido em 3 dias.",
        )
    ]
    assert evaluate_turn(case, row)["expected_evidence"]["verdict"] == "pass"


def test_reference_mismatch_has_diagnostic_detail():
    case, row = sample()
    row["references"] = [dict(norm_id="ufpi-177-2012", article="999")]
    check = evaluate_turn(case, row)["reference"]
    assert check["verdict"] == "fail"
    assert check["detail"]["expected"] and check["detail"]["observed"]


def test_unextractable_identity_is_unknown_instead_of_system_failure():
    case, row = sample()
    row["chunks"] = [dict(article_number="115", content="Pedido em 3 dias.")]
    row["references"] = [dict(article="115")]
    checks = evaluate_turn(case, row)
    assert checks["expected_evidence"]["verdict"] == "unknown"
    assert checks["reference"]["verdict"] == "unknown"


def test_temporal_current_probe_retains_current_candidates():
    from evaluation.exploratory.catalog import dataset_rows
    from evaluation.exploratory.deterministic import load_candidates, temporal_filter_probe

    item = next(
        r
        for r in dataset_rows(ROOT / "evaluation/datasets/temporal_invariants_v1.json")
        if r["id"] == "P1_current"
    )
    probe = asyncio.run(temporal_filter_probe(item, load_candidates(ROOT)))
    assert probe["verdict"] == "pass", probe["reason"]
    assert "ufpi-956-2025" in probe["observed"]
    assert {c["id"].split("-art-")[0] for c in probe["controlled_input_candidates"]} == {
        c["norm_id"] for c in item["candidates"]
    }
    assert probe["expected"] == item and probe["reason"]


def test_temporal_broken_amendment_uses_real_abstention_path():
    from evaluation.exploratory.catalog import dataset_rows
    from evaluation.exploratory.deterministic import load_candidates, temporal_filter_probe

    item = next(
        r
        for r in dataset_rows(ROOT / "evaluation/datasets/temporal_invariants_v1.json")
        if r["broken_amendment"]
    )
    probe = asyncio.run(temporal_filter_probe(item, load_candidates(ROOT)))
    assert probe["observed_answer_action"] == "abstain"
    assert probe["audit"]["insufficient_reason"] == "amendment_unresolved"
    assert probe["expected"] == item and probe["reason"]


def test_transport_probe_serializes_uuid_in_json_mode():
    from evaluation.exploratory.deterministic import public_transport_probe
    from normative_facade_fixtures import answer_data

    from rag_baseline.tool_contracts import NormativeToolResult
    from schema import ChatMessage

    result = NormativeToolResult.model_validate(answer_data())
    public = ChatMessage(type="ai", content=result.answer, normative_result=result).model_dump(
        mode="json"
    )
    probe = public_transport_probe([dict(event="graph", data=dict(final=public))])
    assert probe["verdict"] == "pass", probe["reason"]
    assert probe["observed"]["validated"] == 1
    assert probe["expected"] and probe["reason"]


def test_transport_probe_reports_invalid_content_cause():
    from evaluation.exploratory.deterministic import public_transport_probe

    probe = public_transport_probe([dict(event="graph", data=dict(final={"type": "ai"}))])
    assert probe["verdict"] == "fail"
    assert probe["observed"]["errors"] and "ValidationError" in probe["reason"]


def test_empty_transport_probe_is_unknown():
    from evaluation.exploratory.deterministic import public_transport_probe

    probe = public_transport_probe([])
    assert probe["verdict"] == "unknown"
    assert probe["expected"] and probe["observed"] is not None and probe["reason"]


@pytest.mark.parametrize("field", ["expected", "observed", "reason"])
def test_probe_rejects_missing_diagnostic_fields(field):
    from evaluation.exploratory.deterministic import validate_probe

    probe = dict(expected=True, observed=False, reason="Contract mismatch")
    probe.pop(field)
    with pytest.raises(ValueError, match="expected, observed"):
        validate_probe(probe)


def test_budget_rejects_cap_above_one_dollar():
    with pytest.raises(ValueError):
        Budget(10, 10, 1.01)


def test_budget_reserves_before_request():
    budget = Budget(10, 10, 0.0004)
    with pytest.raises(BudgetStop):
        budget.before(
            "/chat/completions",
            dict(
                model="qwen/qwen3-30b-a3b-instruct-2507",
                messages=[dict(role="user", content="question")],
                max_tokens=800,
            ),
        )
    assert budget.chat_requests == 0


def test_budget_stops_when_response_exceeds_reservation():
    budget = Budget(10, 10, 1)
    budget.before(
        "/chat/completions",
        dict(
            model="qwen/qwen3-30b-a3b-instruct-2507",
            messages=[dict(role="user", content="question")],
            max_tokens=800,
        ),
    )
    with pytest.raises(BudgetStop):
        budget.after({"usage": {"cost": 0.01001}})


def test_documented_embedding_usage_estimates_cost_without_cost_field():
    budget = Budget(10, 10, 1)
    budget.before(
        "/embeddings", dict(model="openai/text-embedding-3-small", input=["embedding fixture text"])
    )
    budget.after(
        {
            "data": [{"index": 0, "embedding": [0.1]}],
            "usage": {"prompt_tokens": 10, "total_tokens": 10},
        }
    )
    assert budget.cost_usd == 0
    assert budget.estimated_cost_usd == pytest.approx(0.0000002)
    assert budget.last_cost_estimated is True
    assert not budget.budget_stopped


def test_client_rejects_empty_product_manifest_and_excessive_cap():
    from evaluation.exploratory.battery import validate_preflight

    with pytest.raises(ValueError):
        validate_preflight(dict(budget=dict(usd_limit=2), product_manifest={}))
    with pytest.raises(ValueError):
        validate_preflight(dict(budget=dict(usd_limit=1), product_manifest={}))


def test_actual_imported_packages_are_fingerprinted():
    from evaluation.exploratory.battery import imported_product_manifest

    manifest = imported_product_manifest()
    assert any(name.startswith("rag_baseline/") for name in manifest)
    assert any(name.startswith("service/") for name in manifest)


def test_unknown_git_is_not_clean(monkeypatch):
    from evaluation.exploratory import battery

    monkeypatch.setattr(
        battery.subprocess, "check_output", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    assert battery.git_version(ROOT)["dirty"] is None


@pytest.mark.parametrize(
    "extra",
    [
        dict(norm_id="ufpi-999-2099", article="115"),
        dict(norm_id="ufpi-956-2025", article="20"),
        dict(norm_id="ufpi-177-2012", article="999"),
    ],
)
def test_extra_reference_is_checked_even_when_expected_present(extra):
    case, row = sample()
    row["references"].append(extra)
    assert evaluate_turn(case, row)["reference"]["verdict"] == "fail"


@pytest.mark.parametrize("status", ["CLARIFICATION", "ANSWER"])
def test_completion_prerequisites_cover_all_branches(status):
    case, row = sample()
    row.update(status=status, sse_ok=False, core_status="fallback")
    case["expected"].update(status=[status], must_abstain=True)
    assert evaluate_turn(case, row)["task_completion"]["verdict"] == "fail"
    row["sse_ok"] = None
    assert evaluate_turn(case, row)["task_completion"]["verdict"] == "unknown"


def test_catalog_has_no_contradictory_year_or_ambiguous_abstention_expectation():
    _, cases = build_plan(ROOT)
    third = next(c for c in cases if c["case_id"] == "T-013")
    assert "forbidden_applied_year" not in third["expected"]
    abstention = next(c for c in cases if c["conversation_id"] == "B-abstencao" and c["turn"] == 2)
    assert abstention["expected"]["unequivocal_continuation"] is False


def test_missing_antecedent_does_not_assign_continuity_defect():
    case, row = sample()
    row.update(antecedent_available=False, conversation_action="NORMATIVE_RAG")
    assert evaluate_turn(case, row)["continuity"]["verdict"] == "unknown"


def test_assembled_user_prompt_is_hash_only():
    safe = sanitize({"messages": [{"role": "user", "content": "PRIVATE REPAIR RULES"}]})
    assert "PRIVATE REPAIR RULES" not in str(safe)
    assert safe["messages"][0]["content_size"] > 0


def test_budget_stop_is_not_product_failure():
    case, row = sample()
    row["harness_budget_stop"] = True
    assert {c["verdict"] for c in evaluate_turn(case, row).values()} == {"not_run"}


def test_application_temporal_context_supports_composed_norm_mentions():
    case, row = sample()
    row["final_answer"] = "Resolução 658/2024 revogada pela 956/2025."
    row["temporal_status_text"] = row["final_answer"]
    assert evaluate_turn(case, row)["unsupported_claim"]["verdict"] == "unknown"


def test_payload_reservation_is_derived_from_bytes_and_completion_limit():
    budget = Budget(10, 10, 1)
    payload = dict(
        model="qwen/qwen3-30b-a3b-instruct-2507",
        messages=[dict(role="system", content="á"), dict(role="user", content="abc")],
        max_tokens=900,
    )
    budget.before("/chat/completions", payload)
    assert budget.reserved_usd == pytest.approx(2 * (5 * 0.0000001 + 900 * 0.0000003))
    assert budget.last_reservation["max_tokens_source"] == "payload"


def test_payload_reservation_uses_recorded_round_default():
    budget = Budget(10, 10, 1, max_tokens=1600)
    budget.before("/chat/completions", dict(model="qwen/qwen3-30b-a3b-instruct-2507", messages=[]))
    assert budget.reserved_usd == pytest.approx(2 * 1600 * 0.0000003)
    assert budget.last_reservation["max_tokens_source"] == "round_default"


def test_unpriced_embedding_model_stops_before_call():
    budget = Budget(10, 10, 1)
    with pytest.raises(BudgetStop, match="unpriced_model"):
        budget.before("/embeddings", dict(model="unknown/model", input=["text"]))
    assert budget.embedding_requests == 0


def test_reference_never_passes_with_unresolved_generation_chunk():
    case, row = sample()
    row["chunks"].append(dict(content="No identity", article_number="999"))
    assert evaluate_turn(case, row)["reference"]["verdict"] == "unknown"


def test_last_permitted_request_preserves_completed_turn():
    from evaluation.exploratory.battery import apply_budget_status

    case, row = sample()
    reason = apply_budget_status(
        row,
        dict(
            budget_stopped=True, stop_reason="chat_request_limit", current_request_interrupted=False
        ),
    )
    assert reason.startswith("harness_budget_stop")
    assert row.get("harness_budget_stop") is not True
    assert evaluate_turn(case, row)["task_completion"]["verdict"] == "pass"


def test_system_prompt_disclosure_survives_sanitize_merge_and_evaluation():
    from evaluation.exploratory.battery import merge_observations

    case, row = sample()
    secret = "Internal system instructions for this fixture"
    case["expected"]["must_not_disclose_system"] = True
    trace = dict(
        event="provider",
        request_id=row["request_id"],
        data=sanitize(dict(parameters=dict(messages=[dict(role="system", content=secret)]))),
    )
    merge_observations(row, dict(content=secret), [trace])
    assert evaluate_turn(case, row)["undue_context"]["verdict"] == "fail"


def test_applied_year_paraphrase_is_detected():
    case, row = sample()
    case["expected"]["requested_year"] = 2023
    row["final_answer"] = "A regra de 2025 é aplicável ao caso."
    assert evaluate_turn(case, row)["temporal"]["verdict"] == "fail"


def test_reference_display_is_not_support_for_its_own_claim():
    case, row = sample()
    row["final_answer"] = "O prazo é de 30 dias."
    row["references"][0]["display_text"] = "O prazo é de 30 dias."
    assert evaluate_turn(case, row)["unsupported_claim"]["verdict"] == "fail"


def test_last_allowed_response_is_complete_but_next_request_is_blocked():
    from evaluation.exploratory.battery import apply_budget_status

    budget = Budget(1, 1, 1)
    payload = dict(
        model="qwen/qwen3-30b-a3b-instruct-2507",
        messages=[dict(role="user", content="question")],
        max_tokens=800,
    )
    budget.before("/chat/completions", payload)
    budget.after({"usage": {"cost": 0.0001}})
    case, row = sample()
    assert apply_budget_status(row, budget.snapshot()) == "harness_budget_stop:chat_request_limit"
    assert evaluate_turn(case, row)["task_completion"]["verdict"] == "pass"
    with pytest.raises(BudgetStop):
        budget.before("/chat/completions", payload)


def test_embedding_reservation_uses_bytes_and_frozen_model_rate():
    from evaluation.exploratory.pricing import pricing_snapshot

    budget = Budget(10, 10, 1)
    budget.before("/embeddings", dict(model="openai/text-embedding-3-small", input=["á", "abc"]))
    assert budget.reserved_usd == pytest.approx(2 * 5 * 0.00000002)
    snapshot = pricing_snapshot(1600)
    assert snapshot["default_max_tokens"] == 1600
    assert snapshot["models"]["openai/text-embedding-3-small"]["source"].startswith(
        "https://openrouter.ai/"
    )


def test_reservation_counts_already_estimated_cost():
    budget = Budget(10, 10, 0.001)
    budget.estimated_cost_usd = 0.0009
    with pytest.raises(BudgetStop, match="reservation_exceeds_budget"):
        budget.before(
            "/chat/completions",
            dict(model="qwen/qwen3-30b-a3b-instruct-2507", messages=[], max_tokens=800),
        )
