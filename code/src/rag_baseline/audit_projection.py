"""Verify the execution snapshots in the repository; read-only and without API calls.

This checks the versioned files only. It does not attest the historical bytes of files
published as scientific projections, whose hashes differ from the run manifests.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from rag_baseline.experiment import ROOT, sha256
from rag_baseline.experiment_v2 import metrics_for, user_prompt
from rag_baseline.models import RetrievedChunk

MANIFEST = "preservation_manifest.json"
BYTE_PRESERVED = "byte_preserved"
PROJECTION = "scientific_projection"
PROJECTION_ONLY_FIELDS = {
    "review",
    "annotation_note",
    "audit_note",
    "interpretive_note",
    "review_score_0_2",
}
SCHEMA = "execution_snapshot_preservation_v2"
NORMALIZATION = "non-scientific metadata normalized"
MANIFEST_KEYS = {"schema", "source_run", "run_manifest", "description", "files", "not_included"}
ENTRY_KEYS = {"relative_path", "sha256", "byte_size", "role", "preservation_kind", "source_run"}


def read_rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def recorded_hashes(run_manifest: dict) -> dict[str, str]:
    recorded = run_manifest.get("file_sha256") or run_manifest.get("files_sha256") or {}
    return {name.replace("\\", "/"): value for name, value in recorded.items()}


def expected_role(name: str) -> str:
    if name.endswith("rows.jsonl"):
        return "run records"
    if name.startswith("evaluation/datasets/"):
        return "candidate dataset"
    if name.startswith(("evaluation/corpora/", "code/scripts/chunks")):
        return "normative corpus"
    if name.startswith("evaluation/protocol"):
        return "evaluation protocol"
    if name.endswith("uv.lock"):
        return "dependency lock"
    return "source module"


def verify_schema(manifest: dict, run: str) -> None:
    if (
        set(manifest) != MANIFEST_KEYS
        or manifest["schema"] != SCHEMA
        or manifest["source_run"] != run
        or manifest["run_manifest"] != f"evaluation/results/{run}/manifest.json"
        or not isinstance(manifest["description"], str)
        or not isinstance(manifest["files"], list)
        or not manifest["files"]
        or not isinstance(manifest["not_included"], list)
    ):
        raise ValueError(f"Manifesto fora do esquema: {run}")
    if not all(isinstance(entry, dict) for entry in manifest["files"] + manifest["not_included"]):
        raise ValueError(f"Entrada que não é objeto no manifesto: {run}")
    for entry in manifest["files"]:
        keys = set(ENTRY_KEYS)
        if entry.get("preservation_kind") == PROJECTION:
            keys.add("normalization")
            if entry.get("normalization") != NORMALIZATION:
                raise ValueError(f"Normalização inválida: {entry.get('relative_path')}")
        name = entry.get("relative_path")
        if (
            set(entry) != keys
            or not isinstance(name, str)
            or entry["source_run"] != run
            or entry["role"] != expected_role(name)
        ):
            raise ValueError(f"Entrada fora do esquema: {name}")
    for entry in manifest["not_included"]:
        if (
            set(entry) != {"relative_path", "role"}
            or not isinstance(entry["relative_path"], str)
            or entry["role"] != expected_role(entry["relative_path"])
        ):
            raise ValueError(f"Item not_included fora do esquema: {run}")


def verify_files(snapshot: Path, manifest: dict, recorded: dict[str, str]) -> dict[str, int]:
    names = [entry["relative_path"] for entry in manifest["files"]]
    if len(names) != len(set(names)):
        raise ValueError("Entrada duplicada no manifesto.")
    listed = set(names)
    present = {
        path.relative_to(snapshot).as_posix() for path in snapshot.rglob("*") if path.is_file()
    }
    if present != listed | {MANIFEST}:
        raise ValueError(
            f"Arquivos divergentes do manifesto: {sorted(present ^ (listed | {MANIFEST}))}"
        )
    for entry in manifest["files"]:
        name, path = entry["relative_path"], snapshot / entry["relative_path"]
        size = entry["byte_size"]
        if sha256(path) != entry["sha256"] or type(size) is not int or path.stat().st_size != size:
            raise ValueError(f"Hash ou tamanho divergente: {name}")
        if entry["preservation_kind"] == BYTE_PRESERVED and recorded.get(name) != entry["sha256"]:
            raise ValueError(f"Arquivo byte_preserved difere do manifesto do run: {name}")
        if entry["preservation_kind"] == PROJECTION and recorded.get(name) == entry["sha256"]:
            raise ValueError(f"Projeção com hash do manifesto do run: {name}")
        if entry["preservation_kind"] not in {BYTE_PRESERVED, PROJECTION}:
            raise ValueError(f"Tipo de preservação desconhecido: {name}")
    not_included = sorted(entry["relative_path"] for entry in manifest["not_included"])
    if not_included != sorted(set(recorded) - listed):
        raise ValueError("Lista not_included difere dos insumos ausentes do snapshot.")
    return dict(Counter(entry["preservation_kind"] for entry in manifest["files"]))


def verify_datasets(snapshot: Path, manifest: dict) -> dict[str, int]:
    counts = {}
    for entry in manifest["files"]:
        if entry["role"] != "candidate dataset" or not entry["relative_path"].endswith(".json"):
            continue
        items = json.loads((snapshot / entry["relative_path"]).read_text(encoding="utf-8"))["items"]
        if len({item["id"] for item in items}) != len(items):
            raise ValueError(f"IDs duplicados: {entry['relative_path']}")
        counts[entry["relative_path"]] = len(items)
    return counts


def verify_rows(run_dir: Path, snapshot: Path, manifest: dict) -> dict | None:
    entries = [entry for entry in manifest["files"] if entry["role"] == "run records"]
    if not entries:
        return None
    rows = read_rows(snapshot / entries[0]["relative_path"])
    published = read_rows(run_dir / "rows.jsonl")
    if len(rows) != len(published):
        raise ValueError("Número de registros difere de rows.jsonl.")
    pairs = Counter((row["id"], row["condition"]) for row in rows)
    if set(pairs.values()) != {1}:
        raise ValueError("Par ausente ou duplicado.")
    fields = sorted(set().union(*rows) - PROJECTION_ONLY_FIELDS)
    for row, other in zip(rows, published, strict=True):
        if any(row.get(field) != other.get(field) for field in fields):
            raise ValueError(f"Campos científicos divergentes: {row['id']} {row['condition']}")
        extra = set(other) - set(fields) - PROJECTION_ONLY_FIELDS
        if any(other[field] is not None for field in extra):
            raise ValueError(f"Campo extra em rows.jsonl: {row['id']} {row['condition']}")
        chunks = [RetrievedChunk(**chunk) for chunk in row["retrieved"]]
        if metrics_for(row, chunks) != row["metrics"]:
            raise ValueError(f"Métrica divergente: {row['id']} {row['condition']}")
        if row["user_prompt"] != user_prompt(row, chunks):
            raise ValueError(f"Prompt divergente: {row['id']} {row['condition']}")
        if row["review_score_0_2"] is not None:
            raise ValueError(f"Escore inesperado: {row['id']} {row['condition']}")
    return {
        "rows": len(rows),
        "pairs": len(pairs),
        "sha256": entries[0]["sha256"],
        "scientific_fields_equal_to_rows_jsonl": len(fields),
        "metrics_recomputed_equal": True,
        "prompts_recomputed_equal": True,
    }


def audit_snapshot(run_dir: Path) -> dict:
    snapshot = run_dir / "execution_snapshot"
    try:
        manifest = json.loads((snapshot / MANIFEST).read_text(encoding="utf-8"))
        verify_schema(manifest, run_dir.name)
        run_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        return {
            "source_run": run_dir.name,
            "files": verify_files(snapshot, manifest, recorded_hashes(run_manifest)),
            "not_included": len(manifest["not_included"]),
            "datasets": verify_datasets(snapshot, manifest),
            "run_records": verify_rows(run_dir, snapshot, manifest),
        }
    except (AttributeError, KeyError, OSError, TypeError) as error:
        raise ValueError(f"Snapshot inválido em {run_dir.name}: {error!r}") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, nargs="?", default=ROOT / "evaluation/results")
    args = parser.parse_args()
    runs = sorted(path.parent for path in args.results.glob("*/execution_snapshot"))
    if not runs:
        raise ValueError("Nenhum execution_snapshot encontrado.")
    print(json.dumps([audit_snapshot(run) for run in runs], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
