"""Recalculate V2 metrics and produce independent-review forms without API calls."""

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from rag_baseline.experiment import ROOT, save_json, sha256
from rag_baseline.experiment_v2 import metrics_for, summarize, user_prompt
from rag_baseline.models import RetrievedChunk


def audit(output: Path, report_dir: Path, raw_snapshot: Path | None = None):
    if report_dir.resolve().is_relative_to((ROOT / "evaluation").resolve()):
        raise ValueError("O relatório deve ficar fora de evaluation/.")
    if report_dir.exists() and any(report_dir.iterdir()):
        raise ValueError("O diretório do relatório deve estar vazio.")
    report_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        json.loads(line)
        for line in (output / "rows.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "completed" or len(rows) != 80:
        raise ValueError("Esperados dois estágios completos, com 80 registros.")
    frozen = {}
    for name, expected in manifest["file_sha256"].items():
        relative = Path(name)
        current = ROOT / relative
        archived = raw_snapshot / relative if raw_snapshot else None
        if current.is_file() and sha256(current) == expected:
            frozen[name] = "working_tree"
        elif archived and archived.is_file() and sha256(archived) == expected:
            frozen[name] = "local_execution_snapshot"
        else:
            raise ValueError(f"Snapshot de execução indisponível ou divergente: {name}")
    pairs = Counter((row["id"], row["condition"]) for row in rows)
    if len(pairs) != 80 or set(pairs.values()) != {1}:
        raise ValueError("Par ausente ou duplicado.")
    ids = {row["id"] for row in rows}
    if len(ids) != 40 or any(
        (qid, condition) not in pairs for qid in ids for condition in ("isolated", "combined")
    ):
        raise ValueError("Condições incompletas.")
    for row in rows:
        chunks = [RetrievedChunk(**chunk) for chunk in row["retrieved"]]
        if metrics_for(row, chunks) != row["metrics"]:
            raise ValueError(f"Métrica divergente: {row['id']} {row['condition']}")
        if row["review_score_0_2"] is not None:
            raise ValueError("Campo de escore inesperadamente preenchido.")
        if row["user_prompt"] != user_prompt(row, chunks):
            raise ValueError("Formato de prompt divergente.")
    expected_hash = hashlib.sha256(manifest["config"]["system_prompt"].encode()).hexdigest()
    if expected_hash != manifest["config"]["system_prompt_sha256"]:
        raise ValueError("Hash de system prompt divergente.")
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    if summarize(rows) != summary:
        raise ValueError("Resumo divergente da recomputação.")
    primary = json.loads((output / "primary_summary.json").read_text(encoding="utf-8"))
    if summarize([row for row in rows if row["condition"] == "isolated"]) != primary:
        raise ValueError("Resumo primário divergente.")
    annotations, key = [], []
    ordered = sorted(rows, key=lambda row: (row["id"], row["condition"]))
    random.Random(956).shuffle(ordered)
    for number, row in enumerate(ordered, 1):
        aid = f"V2-A{number:03d}"
        annotations.append(
            {
                "annotation_id": aid,
                "question": row["question"],
                "answer": row["answer"],
                "expected_action": row["expected_action"],
                "required_facts": row["required_facts"],
                "reference_answer": row["reference_answer"],
                "conditional_answer": row.get("conditional_answer"),
                "reviewer_id": None,
                "score_0_2": None,
                "correct": None,
                "complete": None,
                "clarified": None,
                "evidence_sufficient": None,
                "unsupported_claims": None,
                "notes": None,
            }
        )
        key.append({"annotation_id": aid, "id": row["id"], "condition": row["condition"]})
    for name, value in (("review_template.json", annotations), ("blinding_key.json", key)):
        target = output / name
        if target.exists() and json.loads(target.read_text(encoding="utf-8")) != value:
            raise ValueError(
                f"Formulário existente modificado: {name}; não sobrescrever anotações."
            )
        save_json(report_dir / name, value)
    receipts = [receipt for row in rows for receipt in row["provider_receipts"]]
    report = {
        "execution_file_hashes_verified": frozen,
        "rows": len(rows),
        "unique_pairs": len(pairs),
        "questions": len(ids),
        "metrics_recomputed_equal": True,
        "summary_recomputed_equal": True,
        "primary_summary_recomputed_equal": True,
        "system_prompt_sha256_verified": expected_hash,
        "row_sha256_at_audit": sha256(output / "rows.jsonl"),
        "execution_row_sha256": manifest["combined_rows_sha256"],
        "editorial_projection_present": (
            output.parents[1] / "publication_projection.json"
        ).exists(),
        "generation_errors": [
            {"id": row["id"], "condition": row["condition"], "error": row["error"]}
            for row in rows
            if row["error"]
        ],
        "generation_receipts": len(receipts),
        "generation_tokens": sum((r.get("usage") or {}).get("total_tokens", 0) for r in receipts),
        "generation_cost_as_reported": sum((r.get("usage") or {}).get("cost", 0) for r in receipts),
        "embedding_receipts": len(manifest["embedding_receipts"]),
        "review_scores_filled": 0,
        "review_forms": len(annotations),
        "blinding_limit": "Condition is hidden in the form, but answer content can reveal scope. Evidence review requires separate access after first-pass scoring.",
    }
    save_json(report_dir / "audit.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--report-dir",
        type=Path,
        required=True,
        help="New or empty directory outside evaluation/ for the report and forms.",
    )
    parser.add_argument(
        "--raw-snapshot",
        type=Path,
        help="Directory with the historical input bytes, which are not in the repository.",
    )
    args = parser.parse_args()
    report = audit(args.output, args.report_dir, args.raw_snapshot)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
