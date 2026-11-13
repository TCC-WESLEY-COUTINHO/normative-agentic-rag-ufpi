import pytest
from test_agentic_pipeline import runtime

from rag_baseline.agentic_evaluation import (
    normalize_item,
    router_metrics,
    summarize,
    validate_index_snapshot,
    version_metrics,
)
from rag_baseline.corpus import normalize_chunk
from rag_baseline.experiment import retrieval_metrics
from rag_baseline.models import RetrievedChunk
from rag_baseline.vector_store import ChromaVectorStore
from rag_baseline.versioning import NormativeRegistry, VersionFilter


def test_router_metrics_four_way_confusion_and_clarification_denominators():
    def row(expected, predicted, error=None):
        return dict(
            expected_scope=None if expected == "esclarecer" else expected,
            expected_action="esclarecer" if expected == "esclarecer" else "responder",
            router_decision=dict(
                scope=None if predicted == "esclarecer" else predicted,
                needs_clarification=predicted == "esclarecer",
            ),
            error=error,
        )

    rows = [
        row("graduacao", "graduacao"),
        row("pos_graduacao", "graduacao"),
        row("ambas", "ambas"),
        row("esclarecer", "esclarecer"),
        row("graduacao", "esclarecer"),
        row("esclarecer", "pos_graduacao"),
    ]
    result = router_metrics(rows)
    assert result["route_accuracy"] == 0.5
    assert result["wrong_route_rate"] == 0.5
    assert result["clarification_recall"] == 0.5
    assert result["clarification_precision"] == 0.5
    assert result["confusion_matrix"]["pos_graduacao"]["graduacao"] == 1
    assert result["n"] == 6


def test_router_error_is_not_credited_as_correct_clarification():
    result = router_metrics(
        [
            dict(
                expected_scope=None,
                expected_action="esclarecer",
                router_decision=dict(scope=None, needs_clarification=True),
                error="router_error",
            )
        ]
    )
    assert result["route_accuracy"] == 0
    assert result["clarification_recall"] == 0
    assert result["errors"] == 1
    assert router_metrics([])["route_accuracy"] is None


def test_downstream_generation_error_does_not_change_route_accuracy():
    result = router_metrics(
        [
            dict(
                expected_scope="graduacao",
                expected_action="responder",
                router_decision=dict(scope="graduacao", needs_clarification=False),
                error="OpenRouterError",
            )
        ]
    )
    assert result["route_accuracy"] == 1
    assert result["errors"] == 0


def test_version_metrics_measure_generator_exposure_and_current_evidence():
    registry = NormativeRegistry(
        norms=[
            dict(
                norm_id="old",
                sources=["old"],
                sector="pos_graduacao",
                status="revogada",
                legal_basis=dict(source="fixture", article="1", text="Revocation evidence"),
            )
        ]
    )
    chunks = [
        RetrievedChunk(
            id=f"{n}-art-1-idx-0",
            source=n,
            content=n,
            article_number="1",
            article_label="Art. 1",
            original_index=0,
            distance=0.1,
            rank=i,
        )
        for i, n in enumerate(["old", "current"], 1)
    ]
    vf = VersionFilter(registry)
    before = version_metrics(chunks, vf, current_evidence={("current", "1")})
    assert before["obsolete_context_rate_at_5"] == 0.5
    assert before["compliance_violation"] == 1
    assert before["current_norm_hit_at_5"] == 1
    final, audit = vf.apply(chunks)
    after = version_metrics(final, vf, audit=audit)
    assert after["obsolete_context_rate_at_5"] == 0
    assert after["removal_count"] == 1
    assert after["removal_reasons"] == {"revogada": 1}
    assert version_metrics(chunks, vf, historical=True)["compliance_violation"] == 0
    assert version_metrics([], vf)["obsolete_context_rate_at_5"] is None


def test_retrieval_metrics_accept_two_applicable_norms_without_article_collision():
    result = retrieval_metrics({("a", "1"), ("b", "1")}, [("b", "1"), ("a", "1")], {"a", "b"})
    assert result["recall_at_1"] == 0.5
    assert result["recall_at_5"] == 1
    assert result["wrong_norm_at_5"] == 0


def test_normalizing_candidate_labels_never_changes_source_item():
    source = dict(
        id="amb", sector="graduacao", question="Posso cancelar?", expected_action="clarify"
    )
    result = normalize_item(source)
    assert result["expected_scope"] is None
    assert result["expected_action"] == "esclarecer"
    assert source["expected_action"] == "clarify"
    assert "expected_scope" not in source


@pytest.mark.parametrize(
    "value",
    [
        dict(expected_scope="invalid", expected_action="responder"),
        dict(expected_scope="graduacao", expected_action="esclarecer"),
    ],
)
def test_invalid_evaluation_labels_fail_instead_of_imputing_oracle(value):
    with pytest.raises(ValueError):
        normalize_item(value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "condition,route_calls,has_old",
    [
        ("oracle", 0, True),
        ("both", 0, True),
        ("router", 1, True),
        ("router-version", 1, False),
        ("oracle-version", 0, False),
    ],
)
async def test_experiment_conditions_separate_routing_from_version_filter(
    tmp_path, condition, route_calls, has_old
):
    from rag_baseline.agentic_evaluation import RecordingStore, evaluate_item

    service, remote, agent = runtime(tmp_path, ["pos_graduacao"])
    service.vector_store = RecordingStore(service.vector_store)
    item = dict(
        id="test",
        question="Qual o prazo para divulgar a defesa?",
        expected_scope="pos_graduacao",
        expected_action="responder",
        norm_id="pos2",
        evidence=[dict(norm_id="pos2", article_number="2", text="Content pos2")],
    )
    row = await evaluate_item(item, condition, service, agent.router, agent.version_filter)
    assert row["error"] is None
    assert len(remote.routes) == route_calls
    assert any(c["source"] == "old" for c in row["final_references"]) == has_old
    assert row["generation_performed"]
    assert row["version_metrics"]["compliance_violation"] == int(has_old)
    assert row["retrieval_metrics"] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["both", "router-version"])
async def test_generation_failure_preserves_route_and_exposed_context_for_evaluation(
    tmp_path, condition
):
    from rag_baseline.agentic_evaluation import RecordingStore, evaluate_item, router_metrics
    from rag_baseline.openrouter import OpenRouterError

    service, remote, agent = runtime(tmp_path, ["pos_graduacao"])
    service.vector_store = RecordingStore(service.vector_store)

    async def fail(**payload):
        raise OpenRouterError("Provider unavailable")

    remote.chat = fail
    item = dict(
        id="failure",
        question="Pós-graduação?",
        expected_scope="pos_graduacao",
        expected_action="responder",
        norm_id="pos2",
        evidence=[dict(norm_id="pos2", article_number="2", text="Content pos2")],
    )
    row = await evaluate_item(item, condition, service, agent.router, agent.version_filter)
    assert row["error"]
    assert len(row["final_references"]) == 5
    assert row["generation_performed"]
    if condition == "router-version":
        assert row["router_decision"]["scope"] == "pos_graduacao"
        assert router_metrics([row])["route_accuracy"] == 1


def test_index_snapshot_rejects_wrong_article_metadata_before_experiment(tmp_path):
    store = ChromaVectorStore(tmp_path, "metadata-audit")
    chunk = normalize_chunk(
        dict(
            conteudo="Evidence article 1",
            metadados=dict(fonte="fixture", setor="graduacao", artigo_numero="1"),
        ),
        0,
        id_prefix="norm",
    )
    store.upsert([chunk], [[1.0, 0.0]])
    validate_index_snapshot(store, {"norm": [chunk]})
    metadata = store._metadata(chunk)
    metadata["article_number"] = "999"
    store.collection.update(ids=[chunk.id], metadatas=[metadata])
    with pytest.raises(ValueError, match="metadados"):
        validate_index_snapshot(store, {"norm": [chunk]})


@pytest.mark.asyncio
async def test_evaluation_preserves_source_labels_and_reports_stratified_denominators(tmp_path):
    from rag_baseline.agentic_evaluation import RecordingStore, evaluate_item

    service, _, agent = runtime(tmp_path, ["pos_graduacao"])
    service.vector_store = RecordingStore(service.vector_store)
    item = dict(
        id="stratum",
        category="direta",
        sector="pos_graduacao",
        norm_id="pos2",
        question="Pós-graduação?",
        expected_scope="pos_graduacao",
        expected_action="responder",
        evidence=[dict(norm_id="pos2", article_number="2", text="Content pos2")],
    )
    row = await evaluate_item(item, "router-version", service, agent.router, agent.version_filter)
    assert row["category"] == "direta"
    assert row["norm_id"] == "pos2"
    assert row["dataset_sector"] == "pos_graduacao"
    summary = summarize([row])
    assert summary["by_sector"]["pos_graduacao"]["n"] == 1
    assert summary["by_category"]["direta"]["retrieval_answerable_n"] == 1
    assert summary["by_sector_category"]["pos_graduacao"]["direta"]["router"]["n"] == 1
