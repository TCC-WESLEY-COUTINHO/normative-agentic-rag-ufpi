import pytest


def hits(sectors):
    from rag_baseline.router_probe import ProbeHit

    return [
        ProbeHit(
            rank=i, chunk_id=f"chunk-{i}", norm_id=f"norm-{s}", sector=s, distance=0.1 + i / 100
        )
        for i, s in enumerate(sectors, 1)
    ]


def test_probe_preserves_hits_and_computes_rank_weighted_features():
    from rag_baseline.router_probe import ProbeResult

    original = hits(
        ["graduacao", "graduacao", "pos_graduacao", "graduacao", "pos_graduacao", "other"]
    )
    result = ProbeResult.from_hits(original)
    assert list(result.hits) == original
    assert result.domain_counts == {"graduacao": 3, "pos_graduacao": 2}
    assert result.best_rank_by_domain == {"graduacao": 1, "pos_graduacao": 3}
    assert result.best_distance_by_domain == pytest.approx(
        {"graduacao": 0.11, "pos_graduacao": 0.13}
    )
    assert result.rank_mass_by_domain == pytest.approx({"graduacao": 1.75, "pos_graduacao": 8 / 15})
    assert result.rank_mass_share_by_domain == pytest.approx(
        {"graduacao": 105 / 137, "pos_graduacao": 32 / 137}
    )
    assert result.dominance == pytest.approx(105 / 137)
    assert result.dominant_domain == "graduacao"
    assert result.top1_domain == "graduacao"
    assert result.unknown_sector_count == 1
    assert result.best_distance_gap == pytest.approx(0.02)
    assert "content" not in result.model_dump_json()


def test_empty_and_unknown_probes_have_no_domain_evidence():
    from rag_baseline.router_probe import ProbeResult

    for supplied in ([], hits([None, "unknown"])):
        result = ProbeResult.from_hits(supplied)
        assert result.domains_present == ()
        assert result.dominance is None
        assert result.dominant_domain is None
        assert result.top1_domain is None


@pytest.mark.parametrize(
    "sectors,want",
    [
        (["graduacao"] * 4, "graduacao"),
        (["pos_graduacao"] * 4, "pos_graduacao"),
        (["graduacao", "graduacao", "pos_graduacao"], "graduacao"),
        (["graduacao", "pos_graduacao", "pos_graduacao"], None),
        ([], None),
        (["other"], None),
    ],
)
def test_distribution_routes_only_supported_single_or_dominant_domains(sectors, want):
    from rag_baseline.router_probe import ProbeResult, distribution_decision

    result = ProbeResult.from_hits(hits(sectors))
    before = result.model_dump_json()
    decisions = [distribution_decision(result, threshold=0.75) for _ in range(20)]
    assert all(d.scope == want and d.needs_clarification == (want is None) for d in decisions)
    assert all(d.scope != "ambas" for d in decisions)
    assert result.model_dump_json() == before


def test_distribution_threshold_is_inclusive_and_validated():
    from rag_baseline.router_probe import ProbeResult, distribution_decision

    result = ProbeResult.from_hits(hits(["graduacao", "graduacao", "pos_graduacao"]))
    assert distribution_decision(result, threshold=9 / 11).scope == "graduacao"
    assert distribution_decision(result, threshold=9 / 11 + 1e-12).needs_clarification
    with pytest.raises(ValueError):
        distribution_decision(result, threshold=1.1)
