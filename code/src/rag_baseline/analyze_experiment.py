"""Read-only, offline per-norm supplement; preserves the frozen pilot artifacts."""

import argparse
import json
from pathlib import Path

from rag_baseline.experiment import paired_summary


def per_norm_summary(rows):
    # Validate pairs before grouping: a crossed norm must not create two samples.
    paired_summary(rows)
    result = {}
    for norm in sorted({r["norm_id"] for r in rows}):
        summary = paired_summary([r for r in rows if r["norm_id"] == norm])
        result[norm] = {
            key: summary[key]
            for key in (
                "n_pairs",
                "delta_recall_at_5",
                "bootstrap_95_ci",
                "bootstrap_samples",
                "bootstrap_seed",
            )
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rows", type=Path)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.rows.read_text(encoding="utf-8").splitlines()]
    rows.sort(key=lambda r: (r["id"], r["condition"]))
    print(json.dumps(per_norm_summary(rows), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
