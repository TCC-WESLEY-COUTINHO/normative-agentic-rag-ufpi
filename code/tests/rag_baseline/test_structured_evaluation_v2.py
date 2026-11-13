"""Scientific accounting distinguishes supported mentions, exposure and utility."""

import importlib
import json

import pytest

from tests.rag_baseline.test_normative_output import case


def evaluation():
    return importlib.import_module("rag_baseline.structured_evaluation_v2")


def row(action="accepted", *, chronology=False, completed=True, false_positive=False):
    return dict(
        raw=dict(
            unsupported_locator=False,
            unsupported_chronology=chronology,
            temporal_contradiction=False,
        ),
        final=dict(
            unsupported_locator=False, unsupported_chronology=False, temporal_contradiction=False
        ),
        official_reference_entries=5,
        official_reference_invalid_entries=0,
        supported_locator_mentions=[dict(guard_rejected=False), dict(guard_rejected=True)],
        guard_action=action,
        completed=completed,
        guard_false_positive=false_positive,
        chronology_detected=chronology,
    )


def test_metrics_use_distinct_units_and_do_not_infer_completion_from_guard_acceptance():
    rows = [
        row(),
        row("fallback", chronology=True, completed=False),
        row("regenerated", false_positive=True),
        row(completed=False),
    ]
    metrics = evaluation().summarize(rows, [dict(detected=True), dict(detected=False)])
    assert metrics["SLAR"] == dict(numerator=4, denominator=8, value=0.5)
    assert metrics["SLFRR"] == dict(numerator=4, denominator=8, value=0.5)
    assert metrics["official_reference_response"]["denominator"] == 4
    assert metrics["official_reference_entry"]["denominator"] == 20
    assert metrics["raw_UCER"]["numerator"] == 1
    assert metrics["known_chronology_detection_recall"]["value"] == 0.5
    assert metrics["guard_activation"]["numerator"] == 2
    assert metrics["regeneration_success"] == dict(numerator=1, denominator=2, value=0.5)
    assert metrics["fallback"]["numerator"] == 1
    assert metrics["answer_completion"]["numerator"] == 2
    assert metrics["guard_false_positive"]["numerator"] == 1


def test_zero_denominators_are_null_not_perfect_scores():
    metrics = evaluation().summarize([], [])
    assert metrics["SLAR"]["value"] is None
    assert metrics["regeneration_success"]["value"] is None
    assert metrics["known_chronology_detection_recall"]["value"] is None


def test_missing_annotations_and_completed_fallback_are_rejected():
    bad = row()
    bad["raw"]["unsupported_chronology"] = None
    with pytest.raises(ValueError):
        evaluation().summarize([bad], [])
    with pytest.raises(ValueError):
        evaluation().summarize([row("fallback", completed=True)], [])


def test_changed_frozen_code_or_context_prevents_provider_execution(tmp_path):
    source = tmp_path / "frozen.txt"
    source.write_text("fixed", encoding="utf-8")
    manifest = {"frozen.txt": evaluation().sha(source)}
    evaluation().verify_hashes(tmp_path, manifest)
    source.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="frozen.txt"):
        evaluation().verify_hashes(tmp_path, manifest)


@pytest.mark.asyncio
async def test_invalid_retry_run_preserves_first_raw_and_does_not_reuse_previous_receipt(
    tmp_path, monkeypatch
):
    from rag_baseline import experiment
    from rag_baseline.config import BaselineSettings
    from rag_baseline.openrouter import OpenRouterError

    module = evaluation()
    settings = BaselineSettings(_env_file=None, OPENROUTER_API_KEY="fake-test-only")
    item, _, grounding = case("H_citation")
    frozen = dict(
        item,
        grounding=grounding.model_dump(mode="json"),
        official_references=[],
        allowed_content_locators=[],
        allowed_temporal_facts={},
    )
    from rag_baseline.content_locators import ContentLocatorPolicy
    from rag_baseline.normative_output import allowed_temporal_facts, normative_references

    _, chunks, _ = case("H_citation")
    refs = normative_references(chunks, grounding)
    frozen.update(
        official_references=[r.model_dump() for r in refs],
        allowed_content_locators=[
            p.model_dump()
            for p in ContentLocatorPolicy.for_generation(item["question"], grounding, refs, chunks)[
                1
            ]
        ],
        allowed_temporal_facts=allowed_temporal_facts(grounding).model_dump(),
        repetitions=1,
    )
    (tmp_path / "frozen_inputs.json").write_text(json.dumps([frozen]), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            dict(
                frozen_hashes={},
                settings=module.config(settings),
                execution_status="prepared",
                experimental_head="test",
            )
        ),
        encoding="utf-8",
    )
    (tmp_path / "execution_log.jsonl").write_text("", encoding="utf-8")

    class FailedRetry:
        llm_model = "fake"

        def __init__(self):
            self.receipts = []

        async def chat(self, **kwargs):
            if self.receipts:
                raise OpenRouterError("fake retry failure")
            self.receipts.append(dict(id="first", usage=dict(total_tokens=10)))
            return "Art. 53, § 9º."

    monkeypatch.setattr(module, "settings_for", lambda: settings)
    monkeypatch.setattr(experiment, "client_for", lambda _: FailedRetry())
    with pytest.raises(ExceptionGroup):
        await module.run(tmp_path)
    calls = module.jsonl(tmp_path / "provider_calls.jsonl")
    assert calls[0]["token_usage"] == dict(total_tokens=10)
    assert calls[1]["success"] is False and calls[1]["token_usage"] is None
    raw = module.jsonl(tmp_path / "raw_generations.jsonl")
    assert raw[0]["raw_answer"] == "Art. 53, § 9º."
    assert (
        module.jsonl(tmp_path / "guard_results.jsonl")[0]["audit"]["regeneration_error"]
        == "OpenRouterError"
    )
    assert (
        json.loads((tmp_path / "manifest.json").read_text("utf-8"))["execution_status"]
        == "invalid_do_not_resume"
    )


@pytest.mark.asyncio
async def test_successful_raw_is_durable_before_trial_completion_or_cancellation(tmp_path):
    module = evaluation()
    (tmp_path / "execution_log.jsonl").touch()

    class Provider:
        receipts = []
        llm_model = "fake"

        async def chat(self, **kwargs):
            return "Raw preserved before the caller can fail or be cancelled."

    recorder = module.Recorder(Provider(), tmp_path, {"id": "test"}, 1, {})
    answer = await recorder.chat(system_prompt="fixed", user_prompt="fixed")
    assert module.jsonl(tmp_path / "provider_attempts.jsonl")[0]["raw_answer"] == answer
    assert not (tmp_path / "raw_generations.jsonl").exists()


def test_prepare_anchors_context_bytes_to_historical_v1_manifest(tmp_path, monkeypatch):
    module = evaluation()
    contexts = tmp_path / "frozen_contexts.json"
    contexts.write_text("original", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps(dict(source_hashes={"frozen_contexts.json": module.sha(contexts)})),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "V1", tmp_path)
    monkeypatch.setattr(module, "CONTEXTS", contexts)
    module.verify_v1_source()
    contexts.write_text("altered before prepare", encoding="utf-8")
    with pytest.raises(ValueError, match="V1"):
        module.verify_v1_source()
