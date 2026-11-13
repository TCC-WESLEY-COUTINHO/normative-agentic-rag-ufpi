import pytest

from rag_baseline.analyze_experiment import per_norm_summary


def test_opposite_effects_do_not_disappear_in_per_norm_results():
    # Pooling before stratifying would conceal both effects behind zero.
    rows = [
        {"id": "a", "norm_id": "grad", "condition": "isolated", "metrics": {"recall_at_5": 1}},
        {"id": "a", "norm_id": "grad", "condition": "combined", "metrics": {"recall_at_5": 0}},
        {"id": "b", "norm_id": "post", "condition": "isolated", "metrics": {"recall_at_5": 0}},
        {"id": "b", "norm_id": "post", "condition": "combined", "metrics": {"recall_at_5": 1}},
    ]
    result = per_norm_summary(rows)
    assert result["grad"]["delta_recall_at_5"] == -1
    assert result["grad"]["bootstrap_95_ci"] == [-1, -1]
    assert result["post"]["delta_recall_at_5"] == 1
    assert result["post"]["bootstrap_95_ci"] == [1, 1]
    assert result["grad"]["n_pairs"] == result["post"]["n_pairs"] == 1


def test_per_norm_summary_rejects_incomplete_pairs():
    with pytest.raises(ValueError, match="par"):
        per_norm_summary([{"id": "a", "norm_id": "grad", "condition": "isolated"}])
