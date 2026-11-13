import json

import pytest

from rag_baseline.models import RetrievedChunk
from rag_baseline.versioning import NormativeRegistry, VersionFilter


def entry(norm, status="desconhecida", **extra):
    return dict(
        norm_id=norm,
        sector="pos_graduacao",
        status=status,
        sources=[norm],
        legal_basis=None
        if status == "desconhecida"
        else {"source": "test resolution", "article": "62", "text": "Explicit test evidence."},
        **extra,
    )


def chunk(norm, rank=1):
    return RetrievedChunk(
        id=f"{norm}-art-1-idx-000000",
        content=f"Content {norm}",
        source=norm,
        sector="pos_graduacao",
        article_number="1",
        article_label="Art. 1",
        original_index=0,
        distance=rank / 10,
        rank=rank,
    )


def registry():
    return NormativeRegistry(
        norms=[
            entry("current", "vigente"),
            entry("old", "substituida", superseded_by="current"),
            entry("revoked", "revogada"),
            entry("unknown"),
        ]
    )


def test_version_filter_keeps_current_unknown_and_unregistered_and_audits_removals():
    values = [
        chunk(n, i)
        for i, n in enumerate(["old", "current", "revoked", "unknown", "unregistered"], 1)
    ]
    kept, audit = VersionFilter(registry()).apply(values)
    assert [c.source for c in kept] == ["current", "unknown", "unregistered"]
    assert [c.rank for c in kept] == [1, 2, 3]
    assert len(audit.pre_filter_references) == 5
    assert len(audit.final_references) == 3
    assert [r.reason for r in audit.removed_references] == ["substituida", "revogada"]
    assert audit.removed_references[0].superseded_by == "current"
    assert audit.removed_references[0].legal_basis.article == "62"
    assert len(audit.unknown_norm_ids) == 2


def test_historical_query_retains_obsolete_with_explicit_audit_status():
    kept, audit = VersionFilter(registry()).apply([chunk("old")], historical=True)
    assert len(kept) == 1
    assert audit.historical
    assert audit.norm_statuses == {"old": "substituida"}
    assert not audit.removed_references


@pytest.mark.parametrize(
    "norms",
    [
        [entry("old", "substituida", superseded_by="missing")],
        [entry("a"), entry("a")],
        [entry("a", supersedes=["missing"])],
        [entry("a", superseded_by="a")],
        [dict(norm_id="old", sector="pos_graduacao", status="revogada", sources=["old"])],
    ],
)
def test_invalid_registry_fails_explicitly(norms):
    with pytest.raises(ValueError):
        NormativeRegistry(norms=norms)


def test_registry_load_rejects_missing_documentary_evidence(tmp_path):
    value = entry("old", "revogada")
    value["legal_basis"]["source_path"] = "missing.json"
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"norms": [value]}), encoding="utf-8")
    with pytest.raises(ValueError, match="evidência"):
        NormativeRegistry.load(path)


def test_prefilter_excludes_only_explicitly_obsolete_sources():
    assert set(VersionFilter(registry()).excluded_sources()) == {"old", "revoked"}
