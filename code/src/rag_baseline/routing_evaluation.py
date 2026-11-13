"""Paired routing experiment, dispatched through the existing experiment_v2 runner."""

import hashlib
import json
import math
import statistics
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime

from rag_baseline.adaptive_router import JUDGE_PROMPT, ROUTING_MODES, ProbeJudge, retrieve_probe
from rag_baseline.experiment import CODE, ROOT, client_for, save_json, sha256
from rag_baseline.openrouter import OpenRouterError
from rag_baseline.router import ROUTER_PROMPT, NormativeRouter
from rag_baseline.router_probe import clarify_probe, distribution_decision
from rag_baseline.service import CorpusNotIndexedError

THRESHOLDS = (0.55, 0.60, 0.65, 0.70, 0.75, 0.80)
LABELS = ("graduacao", "pos_graduacao", "ambas", "esclarecer")
DATASET = ROOT / "evaluation/datasets/routing_v2_candidates_v1.json"
PROTOCOL = ROOT / "evaluation/protocol_router_v2_v1.md"
STABILITY_IDS = (
    "TEMP-POS-003",
    "TEMP-POS-004",
    "TEMP-GRAD-005",
    "TEMP-GRAD-001",
    "CONTROL-POS",
    "SMOKE-004",
)


def label(scope):
    return scope or "esclarecer"


def rate(n, d):
    return n / d if d else None


def routing_metrics(rows):
    matrix = {g: dict.fromkeys((*LABELS, "error"), 0) for g in LABELS}
    for r in rows:
        matrix[label(r["expected_scope"])][
            "error" if r.get("error") else label(r["final_route"])
        ] += 1
    correct = sum(matrix[g][g] for g in LABELS)
    asked = [r for r in rows if r["final_route"] is None]
    gold_clarify = [r for r in rows if r["expected_scope"] is None]
    true_clarify = sum(not r.get("error") and r["expected_scope"] is None for r in asked)
    answerable = [r for r in rows if r["expected_scope"] is not None]
    activated = [r for r in rows if r.get("probe_activated")]
    assisted_correct = sum(
        not r.get("error") and r["final_route"] == r["expected_scope"] for r in activated
    )
    f1s = []
    for g in LABELS:
        tp = matrix[g][g]
        fp = sum(matrix[h][g] for h in LABELS if h != g)
        fn = sum(matrix[g].values()) - tp
        f1s.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0)
    return dict(
        n=len(rows),
        correct_n=correct,
        route_accuracy=rate(correct, len(rows)),
        wrong_route_rate=rate(
            sum(
                r["final_route"] is not None
                and (bool(r.get("error")) or r["final_route"] != r["expected_scope"])
                for r in rows
            ),
            len(rows),
        ),
        clarification_precision=rate(true_clarify, len(asked)),
        clarification_recall=rate(true_clarify, len(gold_clarify)),
        unnecessary_clarification_rate=rate(
            sum(r["final_route"] is None for r in answerable), len(answerable)
        ),
        macro_f1=statistics.mean(f1s),
        confusion_matrix=matrix,
        errors=sum(bool(r.get("error")) for r in rows),
        probe_activation_rate=rate(len(activated), len(rows)),
        probe_resolution_rate=rate(
            sum(r["final_route"] is not None and not r.get("error") for r in activated),
            len(activated),
        ),
        probe_assisted_route_accuracy=rate(assisted_correct, len(activated)),
        probe_n=len(activated),
        clarification_output_n=len(asked),
        gold_clarification_n=len(gold_clarify),
        answerable_n=len(answerable),
    )


def select_threshold(candidates):
    if any(r["split"] != "DEV" for rows in candidates.values() for r in rows):
        raise ValueError("Calibração aceita somente DEV.")
    table = [{"threshold": t, **routing_metrics(rows)} for t, rows in sorted(candidates.items())]
    best = min(
        table,
        key=lambda m: (
            -m["macro_f1"],
            m["wrong_route_rate"],
            m["unnecessary_clarification_rate"] or 0,
            -(m["clarification_recall"] or 0),
            m["threshold"],
        ),
    )
    return dict(
        selected_threshold=best["threshold"],
        table=table,
        rule="max macro-F1; min WRR; min UCR; max clarification recall; ascending threshold",
    )


class CallRecorder:
    """Scientific requests/outputs and provider receipts; no headers or reasoning fields."""

    def __init__(self, client):
        self.client = client
        self.events = []

    def __getattr__(self, name):
        return getattr(self.client, name)

    async def _call(self, kind, request, call):
        start, offset = time.perf_counter(), len(self.client.receipts)
        event = dict(call_id=len(self.events) + 1, kind=kind, request=request, error=None)
        self.events.append(event)
        try:
            value = await call()
            if kind == "llm":
                event["output"] = value
            else:
                event["vector_dimensions"] = [len(v) for v in value]
            return value
        except OpenRouterError as exc:
            event["error"] = str(exc)
            raise
        finally:
            event["latency_seconds"] = time.perf_counter() - start
            event["receipts"] = self.client.receipts[offset:]

    async def structured_chat(self, **kwargs):
        request = dict(
            kwargs, temperature=self.client.llm_temperature, max_tokens=self.client.llm_max_tokens
        )
        return await self._call("llm", request, lambda: self.client.structured_chat(**kwargs))

    async def embed(self, texts):
        return await self._call(
            "embedding",
            dict(input=texts, model=self.client.embedding_model),
            lambda: self.client.embed(texts),
        )


def usage_for(events):
    receipts = [r for e in events for r in e.get("receipts", [])]
    usages = [r["usage"] for r in receipts if isinstance(r.get("usage"), dict)]
    costs = [u["cost"] for u in usages if isinstance(u.get("cost"), int | float)]
    tokens = [u["total_tokens"] for u in usages if isinstance(u.get("total_tokens"), int | float)]
    return dict(
        token_usage=sum(tokens) if len(tokens) == len(events) else None,
        reported_tokens=sum(tokens),
        token_coverage=rate(len(tokens), len(events)),
        cost=sum(costs) if len(costs) == len(events) else None,
        reported_cost=sum(costs),
        cost_coverage=rate(len(costs), len(events)),
    )


async def paired_route(service, intent, question, *, threshold):
    """One V1 call and one immutable probe per pair; no final retrieval/generation."""
    client = service.openrouter
    events = getattr(client, "events", [])
    offset = len(events)
    mark = time.perf_counter()
    v1 = await intent.route(question)
    router_seconds = time.perf_counter() - mark
    v1_events = events[offset:]
    v1_error = (
        v1.reason_code if v1.reason_code in ("router_error", "invalid_model_decision") else None
    )
    probe, probe_error, probe_seconds, judge_seconds, d_seconds = None, None, 0.0, 0.0, 0.0
    counters = dict(embedding_calls=0, retrieval_calls=0)
    candidates, judged = {}, None
    probe_events, judge_events = [], []
    if v1.needs_clarification:
        mark, offset = time.perf_counter(), len(events)
        try:
            probe, _ = await retrieve_probe(service, question, top_k=10, counters=counters)
        except (OpenRouterError, CorpusNotIndexedError, ValueError) as exc:
            probe_error = type(exc).__name__
        probe_seconds = time.perf_counter() - mark
        probe_events = events[offset:]
        if probe is not None:
            mark = time.perf_counter()
            chosen = distribution_decision(probe, threshold=threshold)
            d_seconds = time.perf_counter() - mark
            candidates = {
                str(t): distribution_decision(probe, threshold=t).model_dump() for t in THRESHOLDS
            }
            mark, offset = time.perf_counter(), len(events)
            judged = await ProbeJudge(client, model=intent.model).judge(question, probe)
            judge_seconds = time.perf_counter() - mark
            judge_events = events[offset:]
        else:
            chosen = clarify_probe()
    else:
        chosen = v1
    d = chosen
    llm_decision = (
        judged.decision if judged else (clarify_probe() if v1.needs_clarification else v1)
    )
    rows = []
    for mode, decision in zip(ROUTING_MODES, (v1, d, llm_decision), strict=True):
        active = mode != "intent_v1" and v1.needs_clarification
        is_judge = mode == "adaptive_llm_v2" and judged is not None
        logical_events = (
            v1_events + (probe_events if active else []) + (judge_events if is_judge else [])
        )
        error = v1_error if mode == "intent_v1" else (probe_error if active else v1_error)
        if is_judge and judged.status != "valid":
            error = "judge_" + judged.status
        evidence = probe.model_dump(mode="json") if active and probe else None
        rows.append(
            dict(
                routing_mode=mode,
                v1_decision=v1.model_dump(),
                v1_reason_code=v1.reason_code,
                probe_activated=active,
                probe=evidence,
                probe_hits=evidence["hits"] if evidence else [],
                domain_counts=evidence["domain_counts"] if evidence else {},
                best_rank_by_domain=evidence["best_rank_by_domain"] if evidence else {},
                rank_mass_by_domain=evidence["rank_mass_by_domain"] if evidence else {},
                dominance=probe.dominance if active and probe else None,
                probe_sha256=probe.sha256() if active and probe else None,
                distribution_threshold=threshold if mode == "adaptive_distribution_v2" else None,
                distribution_decision=d.model_dump()
                if active and mode == "adaptive_distribution_v2"
                else None,
                llm_judge_decision=llm_decision.model_dump() if is_judge else None,
                llm_judge_status=judged.status if is_judge else "not_called",
                final_route=decision.scope,
                needs_clarification=decision.needs_clarification,
                latency_router=router_seconds,
                latency_probe=probe_seconds if active else 0,
                latency_judge=judge_seconds if is_judge else 0,
                latency_total=router_seconds
                + (probe_seconds if active else 0)
                + (judge_seconds if is_judge else d_seconds if active else 0),
                embedding_calls=counters["embedding_calls"] if active else 0,
                retrieval_calls=counters["retrieval_calls"] if active else 0,
                llm_calls=1 + int(is_judge),
                error=error,
                call_ids=[e["call_id"] for e in logical_events],
                **usage_for(logical_events),
            )
        )
    return dict(
        v1_decision=v1.model_dump(),
        probe=probe.model_dump(mode="json") if probe else None,
        probe_sha256=probe.sha256() if probe else None,
        distribution_candidates=candidates,
        policy_rows=rows,
        calls=v1_events + probe_events + judge_events,
    )


def percentile(values, q):
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(rows, pairs):
    result = {}
    for mode in ROUTING_MODES:
        group = [r for r in rows if r["routing_mode"] == mode]
        latencies = [r["latency_total"] for r in group]
        bias = {}
        for domain in ("graduacao", "pos_graduacao"):
            relevant = [r for r in group if r["expected_scope"] == domain and r["probe"]]
            bias[domain] = dict(
                n=len(relevant),
                dominant_same_n=sum(r["probe"]["dominant_domain"] == domain for r in relevant),
                dominant_same_rate=rate(
                    sum(r["probe"]["dominant_domain"] == domain for r in relevant), len(relevant)
                ),
                crossed_route_n=sum(
                    r["final_route"] not in (None, domain, "ambas") for r in relevant
                ),
            )
        result[mode] = dict(
            **routing_metrics(group),
            decision_accuracy_on_probe=routing_metrics(group)["probe_assisted_route_accuracy"],
            efficiency=dict(
                latency_mean=statistics.mean(latencies),
                latency_p50=percentile(latencies, 0.5),
                latency_p95=percentile(latencies, 0.95) if len(group) >= 20 else None,
                **{
                    key + "_per_query": statistics.mean(r[key] for r in group)
                    for key in (
                        "llm_calls",
                        "retrieval_calls",
                        "embedding_calls",
                        "reported_tokens",
                        "reported_cost",
                    )
                },
                cost_complete_n=sum(r["cost"] is not None for r in group),
                token_complete_n=sum(r["token_usage"] is not None for r in group),
            ),
            bias_given_activated_probe=bias,
            by_category={
                c: routing_metrics([r for r in group if r["category"] == c])
                for c in sorted({r["category"] for r in group})
            },
        )
    calls = [e for p in pairs for e in p["calls"]]
    return dict(
        policies=result,
        actual_physical_work=dict(
            llm_calls=sum(e["kind"] == "llm" for e in calls),
            embedding_calls=sum(e["kind"] == "embedding" for e in calls),
            retrieval_calls=sum(p["policy_rows"][1]["retrieval_calls"] for p in pairs),
            **usage_for(calls),
        ),
        paired_note="physical calls shared; per-policy latency/cost are measured phase sums for standalone cascades, not three separately executed deployments",
    )


def scientific_inputs(dataset):
    return {
        str(p.relative_to(ROOT)): sha256(p)
        for p in [
            dataset,
            PROTOCOL,
            *sorted((CODE / "src/rag_baseline").glob("*.py")),
            CODE / "uv.lock",
            ROOT / "data/normative_registry.json",
        ]
    }


def split_sha(items, split):
    return hashlib.sha256(
        json.dumps(
            [q for q in items if q["split"] == split], ensure_ascii=False, sort_keys=True
        ).encode()
    ).hexdigest()


def stability_summary(rows):
    result = {}
    for mode in ROUTING_MODES:
        result[mode] = {}
        for item_id in STABILITY_IDS:
            group = [r for r in rows if r["routing_mode"] == mode and r["id"] == item_id]
            counts = Counter("error" if r["error"] else label(r["final_route"]) for r in group)
            result[mode][item_id] = dict(
                n=len(group),
                decisions=counts,
                expected_route_rate=routing_metrics(group)["route_accuracy"],
                route_stability_rate=max(counts.values()) / len(group),
                decision_entropy=-sum(
                    (n / len(group)) * math.log2(n / len(group)) for n in counts.values()
                ),
            )
    return result


def validate_frozen(frozen, inputs, dev_sha256, config):
    if frozen["file_sha256"] != inputs or frozen["dev_sha256"] != dev_sha256:
        raise ValueError("Insumos mudaram após a calibração.")
    if frozen["selected_threshold"] not in THRESHOLDS or frozen["config"] != config:
        raise ValueError("A configuração efetiva diverge da calibração congelada.")


def git_head_ref(path):
    return "HEAD:" + str(path).replace("\\", "/")


def git_worktree_hash(path):
    return subprocess.check_output(
        ["git", "hash-object", str(path).replace("\\", "/")], cwd=ROOT, text=True
    ).strip()


async def run_routing(output, stage, *, dataset=None, calibration=None, repetitions=10):
    from rag_baseline.api import _Runtime
    from rag_baseline.config import BaselineSettings
    from rag_baseline.incremental_index import snapshot_collection
    from rag_baseline.profiles import apply_profile
    from rag_baseline.routing_dataset import derive_dataset

    dataset = (dataset or DATASET).resolve()
    output = output.resolve()
    if output.exists():
        raise ValueError("Diretório já existe; use destino novo.")
    if stage == "prepare":
        if dataset.exists():
            raise ValueError("Dataset derivado já existe; não sobrescrever.")
        save_json(dataset, derive_dataset(ROOT))
        output.mkdir(parents=True)
        save_json(
            output / "preparation.json",
            dict(dataset=str(dataset.relative_to(ROOT)), sha256=sha256(dataset)),
        )
        return
    snapshot = json.loads(dataset.read_text(encoding="utf-8"))
    items = snapshot["items"]
    inputs = scientific_inputs(dataset)
    threshold = THRESHOLDS[0]  # calibration evaluates all candidates on the same probe
    frozen = None
    if stage in ("test", "stability"):
        if calibration is None:
            raise ValueError("Informe --calibration com o threshold congelado em DEV.")
        frozen = json.loads(calibration.read_text(encoding="utf-8"))
        threshold = frozen["selected_threshold"]
    selected = [q for q in items if q["split"] == ("TEST" if stage == "test" else "DEV")]
    rounds = 1
    if stage == "stability":
        if repetitions < 10:
            raise ValueError("Estabilidade exige pelo menos 10 repetições.")
        selected = [q for q in selected if q["id"] in STABILITY_IDS]
        if {q["id"] for q in selected} != set(STABILITY_IDS):
            raise ValueError("Casos pré-selecionados de estabilidade ausentes.")
        rounds = repetitions
    settings = apply_profile(BaselineSettings(_env_file=CODE / ".env"), "duas-regulacoes")
    if (
        settings.LLM_TEMPERATURE != 0
        or settings.RETRIEVAL_TOP_K != 5
        or settings.ROUTER_PROBE_TOP_K != 10
    ):
        raise ValueError("Este protocolo exige temperatura 0, top_k final 5 e probe 10.")
    runtime = _Runtime(settings)
    service, store = runtime.service(), runtime.store()
    before = snapshot_collection(store.collection)
    if before["count"] != 507:
        raise ValueError("Índice diferente do snapshot de 507 registros.")
    original = json.loads(
        (ROOT / "evaluation/results/router_v2_exploratory_001/preservation_before.json").read_text(
            encoding="utf-8"
        )
    )
    if before["sha256"] != original["index"]["sha256"]:
        raise ValueError("Índice mudou antes da execução.")
    client = CallRecorder(client_for(settings))
    if client.llm_temperature != 0:
        raise ValueError("Temperatura efetiva inesperada.")
    service.openrouter, service.vector_store = client, store
    intent = NormativeRouter(client, model=settings.ROUTER_MODEL)
    config = dict(
        router_model=intent.model,
        judge_model=intent.model,
        embedding_model=settings.EMBEDDING_MODEL,
        temperature=client.llm_temperature,
        max_tokens=settings.LLM_MAX_TOKENS,
        api_base_url=settings.OPENROUTER_BASE_URL,
        timeout_seconds=settings.OPENROUTER_TIMEOUT_SECONDS,
        probe_top_k=10,
        final_top_k=5,
        collection=settings.CHROMA_COLLECTION,
        distance_metric="cosine_distance",
        distribution_threshold=threshold,
        router_prompt_sha256=hashlib.sha256(ROUTER_PROMPT.encode()).hexdigest(),
        judge_prompt_sha256=hashlib.sha256(JUDGE_PROMPT.encode()).hexdigest(),
    )
    if frozen:
        validate_frozen(frozen, inputs, split_sha(items, "DEV"), config)
    committed_paths = list(inputs)
    if calibration:
        committed_paths.append(str(calibration.resolve().relative_to(ROOT)))
    dirty = [
        name
        for name in committed_paths
        if git_worktree_hash(name)
        != subprocess.check_output(
            ["git", "rev-parse", git_head_ref(name)], cwd=ROOT, text=True
        ).strip()
    ]
    if dirty:
        raise ValueError("Insumos científicos não commitados: " + ", ".join(dirty))
    output.mkdir(parents=True)
    manifest = dict(
        status="started",
        started_at=datetime.now(UTC).isoformat(),
        stage=stage,
        git_commit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        production_inputs_dirty=False,
        file_sha256=inputs,
        dataset_sha256=sha256(dataset),
        dev_sha256=split_sha(items, "DEV"),
        test_sha256=split_sha(items, "TEST"),
        config=config,
        calibration_sha256=sha256(calibration) if calibration else None,
        repetitions=rounds,
        n_items=len(selected),
        exploratory=True,
        paired_v1_and_probe=True,
        index_sha256_before=before["sha256"],
    )
    save_json(output / "manifest.json", manifest)
    rows, pairs = [], []
    for repeat in range(1, rounds + 1):
        for q in selected:
            pair = await paired_route(service, intent, q["question"], threshold=threshold)
            pair.update(id=q["id"], question=q["question"], repeat=repeat)
            for row in pair["policy_rows"]:
                row.update(q, repeat=repeat)
                rows.append(row)
                with (output / "rows.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            pairs.append(pair)
            with (output / "pairs.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(pair, ensure_ascii=False) + "\n")
            print(
                f"{repeat}/{rounds} {q['id']} probe={bool(pair['probe'])} routes="
                + str([r["final_route"] for r in pair["policy_rows"]]),
                flush=True,
            )
    if stage == "calibrate":
        candidates = {}
        for t in THRESHOLDS:
            group = []
            for p in pairs:
                row = dict(p["policy_rows"][1])
                row["distribution_threshold"] = t
                if str(t) in p["distribution_candidates"]:
                    decision = p["distribution_candidates"][str(t)]
                    row.update(
                        final_route=decision["scope"],
                        needs_clarification=decision["needs_clarification"],
                        distribution_decision=decision,
                        distribution_threshold=t,
                    )
                group.append(row)
            candidates[t] = group
        calibration_result = select_threshold(candidates)
        save_json(output / "calibration.json", calibration_result)
        threshold = calibration_result["selected_threshold"]
        save_json(
            output / "frozen_threshold.json",
            dict(
                selected_threshold=threshold,
                candidates=THRESHOLDS,
                rule=calibration_result["rule"],
                dev_sha256=manifest["dev_sha256"],
                file_sha256=inputs,
                dataset_sha256=sha256(dataset),
                config=dict(config, distribution_threshold=threshold),
                calibration_rows_sha256=sha256(output / "rows.jsonl"),
            ),
        )
        # Summaries use the selected candidate; raw rows remain the original recorded candidate.
        for p, selected_row in zip(pairs, candidates[threshold], strict=True):
            p["policy_rows"][1] = selected_row
        rows = [r for p in pairs for r in p["policy_rows"]]
        save_json(output / "selected_policy_rows.json", rows)
    save_json(output / "summary.json", summarize(rows, pairs))
    if stage == "stability":
        save_json(output / "stability.json", stability_summary(rows))
    after = snapshot_collection(store.collection)
    if after != before:
        raise ValueError("Índice alterado durante avaliação.")
    if scientific_inputs(dataset) != inputs:
        raise ValueError("Insumos alterados durante avaliação.")
    manifest.update(
        status="completed",
        finished_at=datetime.now(UTC).isoformat(),
        selected_threshold=threshold,
        index_sha256_after=after["sha256"],
        output_sha256={p.name: sha256(p) for p in output.iterdir() if p.name != "manifest.json"},
    )
    save_json(output / "manifest.json", manifest)
