"""Offline retrieval and execution audit for CLI outputs; no answer-quality scoring."""

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

from rag_baseline.experiment import retrieval_metrics, save_json, sha256
from rag_baseline.experiment_v2 import load_v2
from rag_baseline.routing import question_sector


def save_outside_input(directory: Path, output_dir: Path | None, files: dict):
    """Write audit outputs only to an explicit, empty directory outside the input."""
    if output_dir is None:
        return
    if output_dir.resolve().is_relative_to(directory.resolve()):
        raise ValueError("A saída da auditoria deve ficar fora do diretório de entrada.")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("O diretório de saída da auditoria deve estar vazio.")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        save_json(output_dir / name, value)


def audit(directory: Path, output_dir: Path | None = None):
    items, corpora = load_v2()
    source_norm = {chunk.source: norm for norm, chunks in corpora.items() for chunk in chunks}
    by_question = {q["question"]: q for q in items}
    groups, row_metrics = {}, []
    for filename, sector in (
        ("pos_responses.jsonl", "pos_graduacao"),
        ("grad_responses.jsonl", "graduacao"),
    ):
        path = directory / filename
        if not path.exists():
            continue
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        expected = {q["question"] for q in items if q["sector"] == sector}
        if len(rows) != 20 or {r["question"] for r in rows} != expected:
            raise ValueError(f"Perguntas ausentes, duplicadas ou diferentes: {filename}")
        eligible, wrong_scope = [], []
        for row in rows:
            q = by_question[row["question"]]
            if row["collection"] != "ufpi_duas_regulacoes_setor":
                raise ValueError("Coleção diferente da conjunta.")
            ranked = [
                (source_norm[ref["source"]], ref["article_number"]) for ref in row["references"]
            ]
            if q["expected_action"] == "answer":
                sets = q.get("alternative_evidence_sets", [q["evidence"]])
                alternatives = [
                    retrieval_metrics(
                        {(e["norm_id"], e["article_number"]) for e in group}, ranked, q["norm_id"]
                    )
                    for group in sets
                ]
                metrics = {
                    k: (
                        max(m[k] for m in alternatives)
                        if k != "wrong_norm_at_5"
                        else alternatives[0][k]
                    )
                    for k in alternatives[0]
                }
                eligible.append(metrics)
            else:
                metrics = None
            explicit = question_sector(row["question"])
            if explicit and any(ref.get("sector") != explicit for ref in row["references"]):
                wrong_scope.append(q["id"])
            row_metrics.append(
                {
                    "id": q["id"],
                    "expected_action": q["expected_action"],
                    "response_kind": "error"
                    if row["error"]
                    else row.get("response_kind", "generated"),
                    "metrics": metrics,
                    "error": row["error"],
                    "review_score_0_2": None,
                }
            )
        average_metrics = {}
        if eligible:
            for metric in eligible[0]:
                values = [m[metric] for m in eligible if m[metric] is not None]
                average_metrics[metric] = statistics.mean(values) if values else None
        groups[sector] = {
            "n": len(rows),
            "answerable_n": len(eligible),
            "clarification_expected_n": len(rows) - len(eligible),
            "observed_response_kinds": dict(
                Counter(
                    "error" if r["error"] else r.get("response_kind", "generated") for r in rows
                )
            ),
            "errors": sum(r["error"] is not None for r in rows),
            "wrong_scope_for_explicit_level": wrong_scope,
            "metrics": average_metrics or None,
            "output_sha256": sha256(path),
        }
    summary = {
        "kind": "development_cli_audit",
        "groups": groups,
        "review_answer_accuracy": None,
        "review_scores": None,
        "scope_policy_is_not_a_learned_router": True,
        "interpretation": "Retrieval and execution checks, not normative answer accuracy or a controlled ablation.",
    }
    save_outside_input(
        directory, output_dir, {"summary.json": summary, "row_metrics.json": row_metrics}
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.directory, args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
