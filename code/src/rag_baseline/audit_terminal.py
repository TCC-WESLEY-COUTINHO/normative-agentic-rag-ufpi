"""Offline audit of the explicitly selected terminal scopes; no content grading."""

import argparse
import json
import statistics
from pathlib import Path

from rag_baseline.audit_cli import save_outside_input
from rag_baseline.experiment import sha256
from rag_baseline.experiment_v2 import load_v2, metrics_for
from rag_baseline.models import RetrievedChunk

RUNS = (
    ("pos_pos.jsonl", "pos_graduacao", "pos_graduacao"),
    ("grad_grad.jsonl", "graduacao", "graduacao"),
    ("pos_ambos.jsonl", "pos_graduacao", "ambos"),
    ("grad_ambos.jsonl", "graduacao", "ambos"),
)


def audit(directory: Path, output_dir: Path | None = None):
    items, corpora = load_v2()
    chunks_by_source_article = {
        (c.source, c.article_number): c for chunks in corpora.values() for c in chunks
    }
    groups, measurements = {}, []
    for filename, group, scope in RUNS:
        path = directory / filename
        rows = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
        gold = [q for q in items if q["sector"] == group]
        if [r["question"] for r in rows] != [q["question"] for q in gold]:
            raise ValueError(f"Perguntas ausentes, duplicadas ou fora de ordem: {filename}")
        group_metrics = []
        for row, q in zip(rows, gold, strict=True):
            if row["sector"] != scope:
                raise ValueError(f"O escopo registrado difere da condição: {filename}")
            chunks = []
            for rank, ref in enumerate(row.get("references", []), start=1):
                chunk = chunks_by_source_article[(ref["source"], ref["article_number"])]
                if ref.get("sector") != chunk.sector or ref["content"] != chunk.content:
                    raise ValueError("Referência divergente do corpus congelado.")
                if scope != "ambos" and ref["sector"] != scope:
                    raise ValueError("Referência fora do escopo explicitamente selecionado.")
                if ref["rank"] != rank:
                    raise ValueError("Ranking de referências fora de ordem.")
                chunks.append(
                    RetrievedChunk(**chunk.model_dump(), rank=rank, distance=ref["distance"])
                )
            if len(chunks) > 5 or len({c.id for c in chunks}) != len(chunks):
                raise ValueError("Referências duplicadas ou acima do top-k fixado em cinco.")
            metrics = None if row["error"] else metrics_for(q, chunks)
            if metrics is not None:
                group_metrics.append(metrics)
            measurements.append(
                {
                    "id": q["id"],
                    "dataset_sector": group,
                    "retrieval_scope": scope,
                    "expected_action": q["expected_action"],
                    "metrics": metrics,
                    "error": row["error"],
                    "review_score_0_2": None,
                }
            )
        average = {}
        if group_metrics:
            for key in group_metrics[0]:
                values = [m[key] for m in group_metrics if m[key] is not None]
                average[key] = statistics.mean(values) if values else None
        groups[filename] = {
            "dataset_sector": group,
            "retrieval_scope": scope,
            "n": len(rows),
            "answerable_n": sum(q["expected_action"] == "answer" for q in gold),
            "clarification_expected_n": sum(q["expected_action"] == "clarify" for q in gold),
            "errors": sum(row["error"] is not None for row in rows),
            "metrics_observed_n": len(group_metrics),
            "metrics": average or None,
            "output_sha256": sha256(path),
        }
    summary = {
        "kind": "explicit_scope_terminal_exploration",
        "n": len(measurements),
        "errors": sum(r["error"] is not None for r in measurements),
        "groups": groups,
        "review_scores": None,
        "interpretation": "Escopo manual afeta somente recuperação. Erros de geração não "
        "revelam o Recall não retornado pela API; a qualidade da resposta exige avaliação 0/1/2.",
    }
    save_outside_input(
        directory, output_dir, {"summary.json": summary, "row_metrics.json": measurements}
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
