"""Metrics computed only from RUNS.jsonl and the scoring keys. Absent data stays absent.

Sufficiency labels here are a proxy (expected articles present in the filtered context).
They are not reviewed labels and do not measure whether the evidence answers the question.

Usage: python -m evaluation.adaptive_rag.analyze RUN_DIR [RUN_DIR ...] --out DIR
"""

import argparse
import csv
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .dataset import load

REPO = Path(__file__).resolve().parents[2]
CONDITIONS = ("A", "B", "C", "D", "E", "K10", "S")
_ID = re.compile(r"^(?P<norm>.+?)-art-(?P<article>[^-]+)(?:-idx-\d+)?$")


def pair(chunk_id):
    match = _ID.match(chunk_id or "")
    return (match["norm"], match["article"]) if match else None


def pairs(ids):
    return [p for p in (pair(i) for i in ids) if p]


def last_turn(row):
    return row["turns"][-1] if row.get("turns") else {}


def evidence_lists(row):
    """(first-round filtered, final filtered) article lists, in delivery order."""
    trace = row.get("adaptive_trace") or {}
    rounds = trace.get("filtered_evidence_rounds")
    if rounds:
        return pairs(rounds[0]), pairs(rounds[-1])
    result = last_turn(row).get("normative_result") or {}
    states = (result.get("temporal_provenance") or {}).get("evidence_states") or []
    final = [(s["source_norm"], str(s["source_article"])) for s in states]
    return final, final


def initial_ids(row):
    trace = row.get("adaptive_trace") or {}
    if trace.get("initial_evidence_ids") is not None:
        return trace["initial_evidence_ids"]
    audit = (last_turn(row).get("internal_audit") or {}).get("retrieval_audit") or {}
    return [c["id"] for c in audit.get("returned_candidates") or []]


def best_recall(found, key):
    """Recall against the expected set, or the alternative set most favourable to it."""
    options = [set(key.evidence), *(set(s) for s in key.alternative_sets)]
    options = [o for o in options if o]
    if not options:
        return None, False
    found = set(found)
    best = max(options, key=lambda o: len(o & found) / len(o))
    return len(best & found) / len(best), best <= found


def reciprocal_rank(found, key):
    relevant = set(key.evidence).union(*(set(s) for s in key.alternative_sets), set())
    return next((1 / i for i, p in enumerate(found, 1) if p in relevant), 0.0)


def outcome(row):
    if not row.get("executed"):
        return "error" if row.get("error") else "not_run"
    turn = last_turn(row)
    if turn.get("action") and "DIRECT" in turn["action"]:
        return "direct_out_of_scope"
    result = turn.get("normative_result") or {}
    if result.get("status") == "CLARIFICATION":
        return "clarification_unresolved"
    if result.get("status") == "ERROR":
        return "error_" + str(result.get("error_code"))
    return result.get("core_status") or "unknown"


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    position = max(0, math.ceil(q * len(ordered)) - 1)
    return ordered[position]


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def usage_totals(row):
    totals = Counter()
    purposes = Counter()
    for call in row.get("provider_calls") or []:
        purposes[call["purpose"]] += 1
        usage = call.get("usage") or {}
        totals["prompt_tokens"] += usage.get("prompt_tokens") or 0
        totals["completion_tokens"] += usage.get("completion_tokens") or 0
        if usage.get("cost") is not None:
            totals["cost_usd"] += usage["cost"]
        else:
            totals["calls_without_cost"] += 1
    return totals, purposes


def summarize(rows, keys):
    executed = [r for r in rows if r.get("executed")]
    scored = []
    for row in executed:
        key = keys[row["query_id"]]
        first, final = evidence_lists(row)
        # Scope-gate exits and clarification requests never reach retrieval; reported apart.
        if not key.evidence or outcome(row) in (
            "direct_out_of_scope",
            "clarification_unresolved",
        ):
            continue
        recall, full = best_recall(final, key)
        first_recall, first_full = best_recall(first, key)
        relevant = set(key.evidence).union(
            *(set(s) for s in key.alternative_sets), set()
        )
        scored.append(
            dict(
                row=row,
                recall=recall,
                full=full,
                first_recall=first_recall,
                first_full=first_full,
                rr=reciprocal_rank(final, key),
                delivered=len(final),
                initial=len(initial_ids(row)),
                precision=len(set(final) & relevant) / len(final) if final else None,
            )
        )
    terminal = Counter(outcome(r) for r in rows)
    traces = [r.get("adaptive_trace") or {} for r in executed]
    decisions = Counter(
        t["sufficiency_rounds"][0]["status"]
        for t in traces
        if t.get("sufficiency_rounds")
    )
    actions = Counter(
        t.get("sufficiency_action") for t in traces if t.get("sufficiency_rounds")
    )
    supplemented = [
        s
        for s in scored
        if (s["row"].get("adaptive_trace") or {}).get("additional_retrieval")
    ]
    proxy = Counter()
    for item in scored:
        trace = item["row"].get("adaptive_trace") or {}
        if not trace.get("sufficiency_rounds"):
            continue
        status = trace["sufficiency_rounds"][0]["status"]
        covered = item["first_full"]
        if status == "sufficient":
            proxy[
                "said_sufficient_and_covered"
                if covered
                else "said_sufficient_not_covered"
            ] += 1
        elif status == "missing_user_facts":
            proxy[
                "missing_user_facts_covered"
                if covered
                else "missing_user_facts_not_covered"
            ] += 1
        elif status == "verifier_error":
            proxy["verifier_error"] += 1
        else:
            proxy[
                "said_insufficient_but_covered"
                if covered
                else "said_insufficient_not_covered"
            ] += 1
    delivered = Counter()
    for trace in traces:
        final = trace.get("final_outcome")
        if final in ("accepted", "regenerated"):
            action = trace.get("sufficiency_action")
            if action in ("partial", "conditional"):
                delivered[f"delivered_{action}"] += 1
            if trace.get("omission_note"):
                delivered["delivered_with_omission_note"] += 1
    claims = Counter()
    for trace in traces:
        rounds = trace.get("claim_rounds") or []
        if not rounds:
            continue
        claims[f"first_round_{rounds[0]['status']}"] += 1
        if rounds[0].get("reason"):
            claims[f"first_round_reason_{rounds[0]['reason']}"] += 1
        if rounds[0].get("omitted_requirements"):
            claims["first_round_with_omission"] += 1
        claims["discarded_spans"] += len(rounds[0].get("discarded") or [])
        for claim in rounds[0]["claims"]:
            claims[f"verdict_{claim['verdict']}"] += 1
            if claim.get("downgrade_reason"):
                claims["programmatic_downgrades"] += 1
    totals, purposes, latency = (
        Counter(),
        Counter(),
        [r["latency_seconds"] for r in executed],
    )
    for row in executed:
        usage, used = usage_totals(row)
        totals.update(usage)
        purposes.update(used)
    nodes = defaultdict(list)
    for trace in traces:
        for name, value in (trace.get("node_latency_ms") or {}).items():
            nodes[name].append(value)
    runs = len(executed)
    return dict(
        runs_planned=len(rows),
        runs_executed=runs,
        scored_questions=len(scored),
        recall=mean(s["recall"] for s in scored),
        full_coverage=sum(s["full"] for s in scored),
        mrr=mean(s["rr"] for s in scored),
        precision_incomplete_labels=mean(s["precision"] for s in scored),
        mean_initial_chunks=mean(s["initial"] for s in scored),
        mean_delivered_chunks=mean(s["delivered"] for s in scored),
        supplement_triggered=len(supplemented),
        supplement_coverage_gain=sum(
            1 for s in supplemented if s["full"] and not s["first_full"]
        ),
        supplement_recall_gain_questions=sum(
            1 for s in supplemented if (s["recall"] or 0) > (s["first_recall"] or 0)
        ),
        supplement_chunks_added=sum(
            len((s["row"]["adaptive_trace"] or {}).get("additional_evidence_ids") or [])
            for s in supplemented
        ),
        outcomes=dict(terminal),
        sufficiency_first_decision=dict(decisions),
        sufficiency_final_action=dict(actions),
        sufficiency_vs_proxy=dict(proxy),
        claims=dict(claims),
        delivered=dict(delivered),
        repair_attempts=sum(t.get("repair_attempts", 0) for t in traces),
        semantic_fallbacks=sum(1 for t in traces if t.get("semantic_fallback")),
        latency_p50_s=percentile(latency, 0.5),
        latency_p95_s=percentile(latency, 0.95),
        node_latency_mean_ms={
            k: round(statistics.fmean(v), 1) for k, v in sorted(nodes.items())
        },
        provider_calls=dict(purposes),
        llm_calls_per_run=round(
            sum(v for k, v in purposes.items() if k != "embedding") / runs, 2
        )
        if runs
        else None,
        searches_per_run=round(purposes["embedding"] / runs, 2) if runs else None,
        prompt_tokens=totals["prompt_tokens"],
        completion_tokens=totals["completion_tokens"],
        cost_usd=round(totals["cost_usd"], 6),
        calls_without_reported_cost=totals["calls_without_cost"],
    )


def review_rows(rows):
    for row in rows:
        trace = row.get("adaptive_trace") or {}
        for index, report in enumerate(trace.get("claim_rounds") or []):
            for claim in report["claims"]:
                yield dict(
                    query_id=row["query_id"],
                    condition=row["configuration_id"],
                    round=index,
                    report_status=report["status"],
                    source=claim.get("source", claim.get("kind")),
                    material=claim["material"],
                    model_verdict=claim["model_verdict"],
                    verdict=claim["verdict"],
                    downgrade_reason=claim["downgrade_reason"],
                    evidence_ids="|".join(claim["evidence_ids"]),
                    claim=claim["text"],
                    evidence_quote=claim.get(
                        "evidence_quote", claim.get("explanation", "")
                    ),
                    omitted_requirements="|".join(
                        report.get("omitted_requirements") or []
                    ),
                )


def main(sources, directory: Path):
    rows, seen = [], set()
    for source in sources:
        for line in (source / "RUNS.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            pair_id = (row["query_id"], row["configuration_id"])
            # Rows a later continuation executed replace the "not run" placeholders;
            # a pair executed twice is counted once (the earliest record).
            if (row.get("executed") or row.get("error")) and pair_id not in seen:
                rows.append(row)
                seen.add(pair_id)
    for source in sources:
        for line in (source / "RUNS.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if (row["query_id"], row["configuration_id"]) not in seen:
                rows.append(row)
                seen.add((row["query_id"], row["configuration_id"]))
    directory.mkdir(parents=True, exist_ok=True)
    _, keys, _ = load(REPO, REPO / "data")
    keys = {k.qid: k for k in keys}
    metrics = {}
    for name in CONDITIONS:
        subset = [r for r in rows if r["configuration_id"] == name]
        if subset:
            metrics[name] = summarize(subset, keys)
    (directory / "METRICS.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    columns = [
        "runs_executed",
        "scored_questions",
        "recall",
        "full_coverage",
        "mrr",
        "mean_delivered_chunks",
        "supplement_triggered",
        "supplement_coverage_gain",
        "latency_p50_s",
        "latency_p95_s",
        "llm_calls_per_run",
        "cost_usd",
    ]
    with (directory / "SUMMARY.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["condition", *columns, "outcomes"])
        for name, item in metrics.items():
            writer.writerow(
                [name, *(item[c] for c in columns), json.dumps(item["outcomes"])]
            )
    review = list(review_rows(rows))
    if review:
        with (directory / "claims_for_review.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=list(review[0]))
            writer.writeheader()
            writer.writerows(review)
    json.dump(metrics, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    main(args.sources, args.out)
