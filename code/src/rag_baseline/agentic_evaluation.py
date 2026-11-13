"""Evaluation helpers for the existing experiment_v2 runner (no separate CLI)."""

import hashlib
import json
import statistics
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from rag_baseline.agentic import AgenticRagService, is_historical_question
from rag_baseline.experiment import CODE, ROOT, client_for, retrieval_metrics, save_json, sha256
from rag_baseline.experiment_v2 import load_v2, metrics_for
from rag_baseline.prompts import V2_SYSTEM_PROMPT
from rag_baseline.router import ROUTER_PROMPT, NormativeRouter
from rag_baseline.versioning import REGISTRY_PATH, NormativeRegistry, VersionFilter

CONDITIONS = ("oracle", "both", "router", "router-version", "oracle-version")
LABELS = ("graduacao", "pos_graduacao", "ambas", "esclarecer")


def normalize_item(item):
    result = dict(item)
    action = {"answer": "responder", "clarify": "esclarecer"}.get(
        item.get("expected_action"), item.get("expected_action")
    )
    scope = item.get("expected_scope", None if action == "esclarecer" else item.get("sector"))
    if action not in ("responder", "esclarecer") or scope not in (*LABELS[:3], None):
        raise ValueError("Rótulo candidato inválido.")
    if (action == "esclarecer") != (scope is None):
        raise ValueError("Rótulos de ação/escopo inconsistentes.")
    result.update(expected_scope=scope, expected_action=action)
    return result


def router_metrics(rows):
    rows = [r for r in rows if r.get("router_decision") is not None]
    matrix = {a: dict.fromkeys(LABELS, 0) for a in LABELS}
    correct = true_clarify = expected_clarify = predicted_clarify = errors = 0
    for row in rows:
        expected = "esclarecer" if row["expected_action"] == "esclarecer" else row["expected_scope"]
        decision = row["router_decision"]
        predicted = "esclarecer" if decision["needs_clarification"] else decision["scope"]
        matrix[expected][predicted] += 1
        failed = row.get("error") in ("router_error", "invalid_model_decision")
        errors += failed
        correct += expected == predicted and not failed
        expected_clarify += expected == "esclarecer"
        predicted_clarify += predicted == "esclarecer"
        true_clarify += expected == predicted == "esclarecer" and not failed
    return dict(
        n=len(rows),
        errors=errors,
        route_accuracy=correct / len(rows) if rows else None,
        wrong_route_rate=1 - correct / len(rows) if rows else None,
        clarification_recall=true_clarify / expected_clarify if expected_clarify else None,
        clarification_precision=true_clarify / predicted_clarify if predicted_clarify else None,
        expected_clarification_n=expected_clarify,
        predicted_clarification_n=predicted_clarify,
        confusion_matrix=matrix,
    )


def version_metrics(
    chunks,
    version_filter,
    *,
    historical=False,
    audit=None,
    current_evidence=None,
    target_provision=None,
):
    top = chunks[:5]
    obsolete = sum(
        not historical
        and (record := version_filter.registry.record_for(c)) is not None
        and record.status in ("substituida", "revogada")
        for c in top
    )
    ranked = {(c.id.split("-art-")[0], c.article_number) for c in top}
    if audit:
        ranked.update(
            (a.amendment.effective_text_source, a.amendment.legal_basis.article)
            for a in audit.amended_references
        )
    outdated = sum(
        not historical
        and (record := version_filter.registry.record_for(c)) is not None
        and any(
            c.article_number == a.target.article and a.previous_text in c.content
            for a in record.amendments
        )
        for c in top
    )
    target_outdated = None
    if target_provision and not historical:
        target_outdated = int(
            any(
                (record := version_filter.registry.record_for(c)) is not None
                and record.norm_id == target_provision["norm_id"]
                and any(
                    a.target.article == c.article_number == target_provision["article"]
                    and a.target.paragraph == target_provision["paragraph"]
                    and a.previous_text in c.content
                    for a in record.amendments
                )
                for c in top
            )
        )
    reasons = Counter(r.reason for r in audit.removed_references) if audit else Counter()
    return dict(
        obsolete_context_rate_at_5=obsolete / len(top) if top else None,
        compliance_violation=int(obsolete > 0 or outdated > 0),
        delivered_context_n=len(top),
        obsolete_context_n=obsolete,
        outdated_provision_context_n=outdated,
        outdated_provision_exposure=target_outdated,
        applied_amendment_n=len(audit.amended_references) if audit else 0,
        current_norm_hit_at_5=int(bool(ranked & current_evidence)) if current_evidence else None,
        removal_count=sum(reasons.values()),
        removal_reasons=dict(reasons),
        prefilter_excluded_norm_ids=audit.prefilter_excluded_norm_ids if audit else [],
    )


class RecordingStore:
    """Read-only observation of the existing store, without changing rankings."""

    def __init__(self, store):
        self.store = store
        self.last = []

    def count(self):
        return self.store.count()

    def query(self, *args, **kwargs):
        self.last = self.store.query(*args, **kwargs)
        return self.last


async def evaluate_item(item, condition, service, router, version_filter):
    from rag_baseline.versioning import VersionAudit

    q = normalize_item(item)
    started = time.perf_counter()
    result, error, selected, audit = None, None, None, None
    generation_attempted = False
    final, pre, removed = [], [], []
    service.vector_store.last = []
    historical = is_historical_question(
        q["question"],
        obsolete_norm_ids=[n.norm_id for n in version_filter.obsolete_records()],
    )
    try:
        if condition in ("router", "router-version"):
            result = await AgenticRagService(service, router, version_filter).query(
                q["question"], use_version_filter=condition == "router-version"
            )
            selected = result.selected_scope
            error = result.error
            if result.version_filter:
                audit = VersionAudit.model_validate(result.version_filter)
                pre, final, removed = (
                    audit.pre_filter_references,
                    audit.final_references,
                    audit.removed_references,
                )
        elif condition.startswith("oracle") and q["expected_action"] == "esclarecer":
            # No oracle sector exists. Keep the row but do not invent personal context.
            pass
        else:
            selected = "ambas" if condition == "both" else q["expected_scope"]
            sector = None if selected == "ambas" else selected
            if condition == "oracle-version":
                pre = await service.retrieve(
                    q["question"],
                    sector=sector,
                    excluded_sources=[] if historical else version_filter.excluded_sources(),
                )
                final, audit = version_filter.apply(pre, historical=historical, top_k=service.top_k)
                if not historical:
                    audit.prefilter_exclusions = version_filter.obsolete_records()
                    audit.prefilter_excluded_norm_ids = [
                        n.norm_id for n in audit.prefilter_exclusions
                    ]
                removed = audit.removed_references
                notice = (
                    "CONSULTA HISTÓRICA. Status por norma: " + str(audit.norm_statuses)
                    if historical
                    else None
                )
                if final:
                    generation_attempted = True
                    result = await service.generate(q["question"], final, context_notice=notice)
            else:
                pre = final = await service.retrieve(q["question"], sector=sector)
                generation_attempted = True
                result = await service.generate(q["question"].strip(), final)
    except Exception as exc:
        # Never persist arbitrary provider bodies, keys or internal model text.
        error = type(exc).__name__
        pre = service.vector_store.last
        if audit is None and not generation_attempted:
            final = []
    answerable = q["expected_action"] == "responder"
    retrieval = None
    if answerable:
        if q.get("alternative_evidence_sets"):
            retrieval = metrics_for({**q, "expected_action": "answer"}, final)
        else:
            gold = {(e["norm_id"], e["article_number"]) for e in q["evidence"]}
            norms = q.get("applicable_norm_ids") or (
                {e["norm_id"] for e in q["evidence"]}
                if q["expected_scope"] == "ambas"
                else q["norm_id"]
            )
            retrieval = retrieval_metrics(
                gold, [(c.id.split("-art-")[0], c.article_number) for c in final], norms
            )
    current = {(e["norm_id"], e["article_number"]) for e in q.get("current_evidence", [])}
    return dict(
        id=q["id"],
        norm_id=q.get("norm_id"),
        dataset_sector=q.get("sector") or q["expected_scope"],
        domain=q.get("domain") or q.get("sector") or q["expected_scope"],
        temporal_relation=q.get("temporal_relation"),
        category=q.get("category"),
        question=q["question"],
        expected_scope=q["expected_scope"],
        expected_action=q["expected_action"],
        condition=condition,
        router_decision=result.route if result else None,
        needs_clarification=result.needs_clarification if result else None,
        selected_scope=selected,
        oracle_not_applicable=(condition.startswith("oracle") and not answerable),
        pre_filter_references=[c.model_dump() for c in pre],
        removed_references=[r.model_dump(mode="json") for r in removed],
        amended_references=[a.model_dump(mode="json") for a in audit.amended_references]
        if audit
        else [],
        final_references=[c.model_dump() for c in final],
        prefilter_exclusions=[n.model_dump(mode="json") for n in audit.prefilter_exclusions]
        if audit
        else [],
        answer=result.answer if result else None,
        error=error,
        latency=time.perf_counter() - started,
        retrieval_metrics=retrieval,
        version_metrics=version_metrics(
            final,
            version_filter,
            historical=historical,
            audit=audit,
            current_evidence=current,
            target_provision=q.get("target_provision"),
        ),
        generation_performed=generation_attempted
        or bool(result and result.generation_attempts > 0),
        review_score_0_2=None,
        review_required_facts=None,
        review_unsupported_claims=None,
        review_wrong_norm=None,
        review_citation_precision=None,
        review_citation_coverage=None,
    )


def _summarize_group(rows):
    def means(values):
        keys = {k for row in values for k, v in row.items() if isinstance(v, int | float)}
        return {
            k: statistics.mean(r[k] for r in values if isinstance(r.get(k), int | float))
            for k in sorted(keys)
        }

    exposed = [r["version_metrics"] for r in rows if r["generation_performed"]]
    total_contexts = sum(r["delivered_context_n"] for r in exposed)
    targeted = [r for r in exposed if r.get("outdated_provision_exposure") is not None]
    return dict(
        n=len(rows),
        failures=sum(r["error"] is not None for r in rows),
        router=router_metrics(rows),
        retrieval=means([r["retrieval_metrics"] for r in rows if r["retrieval_metrics"]]),
        retrieval_answerable_n=sum(r["retrieval_metrics"] is not None for r in rows),
        version=dict(
            generated_question_n=len(exposed),
            obsolete_context_rate_at_5=(
                sum(r["obsolete_context_n"] for r in exposed) / total_contexts
                if total_contexts
                else None
            ),
            compliance_violation_rate=(
                statistics.mean(r["compliance_violation"] for r in exposed) if exposed else None
            ),
            removal_count=sum(r["version_metrics"]["removal_count"] for r in rows),
            removal_reasons=dict(
                Counter(
                    reason
                    for row in rows
                    for reason, count in row["version_metrics"]["removal_reasons"].items()
                    for _ in range(count)
                )
            ),
            current_norm_hit_at_5=means(
                [
                    r["version_metrics"]
                    for r in rows
                    if r["version_metrics"]["current_norm_hit_at_5"] is not None
                ]
            ).get("current_norm_hit_at_5"),
            outdated_provision_query_n=len(targeted),
            outdated_provision_exposed_query_n=sum(
                r["outdated_provision_exposure"] for r in targeted
            ),
            outdated_provision_exposure_rate=statistics.mean(
                r["outdated_provision_exposure"] for r in targeted
            )
            if targeted
            else None,
            applied_amendment_n=sum(r.get("applied_amendment_n", 0) for r in exposed),
        ),
        review_scores=None,
    )


def summarize(rows):
    def groups(field, subset):
        labels = sorted({str(r.get(field) or "unspecified") for r in subset})
        return {
            label: _summarize_group(
                [r for r in subset if str(r.get(field) or "unspecified") == label]
            )
            for label in labels
        }

    return {
        **_summarize_group(rows),
        "by_sector": groups("dataset_sector", rows),
        "by_norm": groups("norm_id", rows),
        "by_category": groups("category", rows),
        "by_domain": groups("domain", rows),
        "by_temporal_relation": groups("temporal_relation", rows),
        "by_sector_category": {
            sector: groups(
                "category",
                [r for r in rows if str(r.get("dataset_sector") or "unspecified") == sector],
            )
            for sector in sorted({str(r.get("dataset_sector") or "unspecified") for r in rows})
        },
    }


def validate_index_snapshot(store, corpora):
    from rag_baseline.vector_store import ChromaVectorStore

    expected = {c.id: c for cs in corpora.values() for c in cs}
    indexed = store.collection.get(include=["documents", "metadatas"])
    if set(indexed["ids"]) != set(expected):
        raise ValueError("Índice local diverge dos corpora congelados; não será alterado.")
    for chunk_id, content, metadata in zip(
        indexed["ids"], indexed["documents"], indexed["metadatas"], strict=True
    ):
        chunk = expected[chunk_id]
        if chunk.content != content or ChromaVectorStore._metadata(chunk) != metadata:
            raise ValueError(
                "Texto ou metadados do índice divergem dos corpora; não será alterado."
            )


async def run_condition(output: Path, condition: str, dataset: Path | None = None, limit=None):
    from rag_baseline.api import _Runtime
    from rag_baseline.config import BaselineSettings
    from rag_baseline.profiles import apply_profile

    if condition not in CONDITIONS:
        raise ValueError("Condição desconhecida.")
    items, corpora = load_v2()
    dataset_paths = [
        ROOT / f"evaluation/datasets/{sector}_v2.json" for sector in ("graduacao", "pos_graduacao")
    ]
    if dataset is not None:
        snapshot = json.loads(dataset.read_text(encoding="utf-8"))
        if not snapshot.get("candidate_gold"):
            raise ValueError("Dataset adicional deve declarar candidate_gold=true.")
        items = snapshot["items"]
        dataset_paths.append(dataset.resolve())
    # Legacy V2 snapshots stay frozen. Only this runner loads the additional corpora.
    from rag_baseline.corpus import load_corpus

    temporal_paths = list((ROOT / "evaluation/corpora").glob("*_temporal_v1.json"))
    for corpus_path in temporal_paths:
        raw = json.loads(corpus_path.read_text(encoding="utf-8"))
        norm_id = raw[0]["metadados"]["norm_id"]
        if norm_id in corpora:
            raise ValueError("Corpus temporal duplicado.")
        corpora[norm_id] = load_corpus(corpus_path, id_prefix=norm_id)
    items = [normalize_item(q) for q in items]
    if limit is not None:
        if limit < 1:
            raise ValueError("--limit deve ser positivo.")
        items = items[:limit]
    if not items or len({q["id"] for q in items}) != len(items):
        raise ValueError("Itens ausentes ou IDs duplicados.")
    lookup = {(n, c.article_number): c.content for n, cs in corpora.items() for c in cs}
    for q in items:
        if q["expected_action"] == "responder":
            if not q.get("evidence"):
                raise ValueError("Item respondível sem qrels.")
            for e in q["evidence"] + q.get("current_evidence", []):
                if lookup.get((e["norm_id"], e["article_number"])) != e["text"]:
                    raise ValueError("Evidência candidata diverge do corpus.")
    settings = apply_profile(BaselineSettings(_env_file=CODE / ".env"), "duas-regulacoes")
    if not settings.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY ausente.")
    if settings.RETRIEVAL_TOP_K != 5:
        raise ValueError("Este protocolo exige top_k=5.")
    registry = NormativeRegistry.load()
    runtime = _Runtime(settings)
    store = runtime.store()
    validate_index_snapshot(store, corpora)
    client = client_for(settings)
    service = runtime.service()
    service.openrouter = client
    service.vector_store = RecordingStore(store)
    router = NormativeRouter(client, model=settings.ROUTER_MODEL)
    vf = VersionFilter(registry)
    paths = [
        *dataset_paths,
        REGISTRY_PATH,
        ROOT / "evaluation/datasets/router_labels_v1.json",
        ROOT / "evaluation/protocol_agentic_v1.md",
        *([ROOT / "evaluation/protocol_temporal_v1.md"] if temporal_paths else []),
        *temporal_paths,
        *sorted((ROOT / "evaluation/provenance").glob("*.json")),
        *(ROOT / "evaluation/corpora").glob("*_setor_v2.json"),
        CODE / "uv.lock",
        *sorted((CODE / "src/rag_baseline").glob("*.py")),
        CODE / "src/agents/chatbot_ufpi_agentic.py",
        CODE / "src/agents/agents.py",
    ]
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = dict(
        status="started",
        condition=condition,
        candidate_gold=True,
        started_at=datetime.now(UTC).isoformat(),
        git_commit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        git_dirty=bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
        inputs_dirty=bool(
            subprocess.check_output(
                [
                    "git",
                    "status",
                    "--porcelain",
                    "--",
                    *[str(p.resolve().relative_to(ROOT)) for p in paths],
                ],
                cwd=ROOT,
                text=True,
            ).strip()
        ),
        file_sha256={str(p.resolve().relative_to(ROOT)): sha256(p) for p in paths},
        registry_sha256=sha256(REGISTRY_PATH),
        dataset_sha256={p.name: sha256(p) for p in dataset_paths},
        corpus_sha256={
            p.name: sha256(p) for p in (ROOT / "evaluation/corpora").glob("*_setor_v2.json")
        },
        model=settings.LLM_MODEL,
        router_model=router.model,
        embedding=settings.EMBEDDING_MODEL,
        top_k=5,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        prompt_hashes={
            "generator": hashlib.sha256(V2_SYSTEM_PROMPT.encode()).hexdigest(),
            "router": hashlib.sha256(ROUTER_PROMPT.encode()).hexdigest(),
        },
        collection=settings.CHROMA_COLLECTION,
        indexed_chunks=store.count(),
        index_embedding_provenance="not_recorded_by_existing_indexer",
        repetitions=1,
        item_ids=[q["id"] for q in items],
        limit=limit,
        retrieval_strategy="dense_top5; version conditions prefilter explicit obsolete sources then defensive postfilter",
        temporal_obsolete_corpus_ingested="ufpi-658-2024" in corpora,
        temporal_amending_corpus_ingested="ufpi-1056-2026" in corpora,
    )
    save_json(output / "manifest.json", manifest)
    save_json(
        output / "router_labels.json",
        [
            dict(
                id=q["id"], expected_scope=q["expected_scope"], expected_action=q["expected_action"]
            )
            for q in items
        ],
    )
    rows = []
    with (output / "rows.jsonl").open("x", encoding="utf-8") as stream:
        for q in items:
            receipt_start = len(client.receipts)
            row = await evaluate_item(q, condition, service, router, vf)
            row["provider_receipts"] = client.receipts[receipt_start:]
            rows.append(row)
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            print(
                f"{len(rows)}/{len(items)} {q['id']} {condition} error={row['error']}", flush=True
            )
    save_json(output / "summary.json", summarize(rows))
    manifest.update(
        status="completed",
        finished_at=datetime.now(UTC).isoformat(),
        failures=sum(r["error"] is not None for r in rows),
        rows_sha256=sha256(output / "rows.jsonl"),
        labels_sha256=sha256(output / "router_labels.json"),
    )
    save_json(output / "manifest.json", manifest)
