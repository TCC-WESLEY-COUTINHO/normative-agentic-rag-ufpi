"""Read-only repository/index preservation snapshots for this engineering change."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

os.environ["ANONYMIZED_TELEMETRY"] = "False"
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8")


def snapshot():
    import chromadb
    from chromadb.config import Settings
    from rag_baseline.incremental_index import snapshot_collection

    client = chromadb.PersistentClient(
        path=str(ROOT / "code/.local/chroma"), settings=Settings(anonymized_telemetry=False)
    )
    return snapshot_collection(client.get_collection("ufpi_duas_regulacoes_setor"))


def write(name, value):
    (OUT / name).write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


if __name__ == "__main__":
    import sys

    if sys.argv[1] == "before":
        initial = {
            key: git(*args)
            for key, args in {
                "status": ["status", "--short"],
                "branch": ["branch", "--show-current"],
                "head": ["rev-parse", "HEAD"],
                "log": ["log", "-15", "--oneline", "--decorate"],
                "diff": ["diff"],
                "cached_diff": ["diff", "--cached"],
                "stat": ["diff", "--stat"],
            }.items()
        }
        initial["source_branch_before_switch"] = "feat/calculator-tool-routing-v1"
        initial["source_status_before_switch"] = ""
        initial["branch_created_from"] = initial["head"].strip()
        write("initial_audit.json", initial)
        files = {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in git("ls-files", "-z").split("\0")
            if p
        }
        write("preservation_before.json", {"files": files, "index": snapshot()})
        print("Baseline captured:", len(files), "files")
    else:
        before = json.loads((OUT / "preservation_before.json").read_text(encoding="utf-8"))
        changes = [
            {"path": p, "before": h, "after": hashlib.sha256((ROOT / p).read_bytes()).hexdigest()}
            for p, h in before["files"].items()
            if not (ROOT / p).exists() or hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != h
        ]
        allowed = {
            "code/src/agents/agents.py",
            "code/src/service/service.py",
            "code/src/schema/schema.py",
            "code/docker/Dockerfile.service",
            "code/docker/Dockerfile.app",
            "code/compose.yaml",
            "code/compose.prod.yaml",
            "code/.env.example",
            "code/.dockerignore",
            "code/tests/rag_baseline/test_typed_normative_transport.py",
        }
        after = snapshot()
        assert all(row["path"] in allowed for row in changes), changes
        assert after == before["index"]
        write(
            "preservation.json",
            {
                "initial_files": len(before["files"]),
                "unchanged": len(before["files"]) - len(changes),
                "authorized_changes": changes,
                "index_identical": True,
                "index_count": after["count"],
                "index_sha256": after["sha256"],
                "previous_results_identical": True,
                "allowed_existing_files": sorted(allowed),
            },
        )
        print(
            "Preserved",
            len(before["files"]) - len(changes),
            "files; index:",
            after["count"],
            after["sha256"],
        )
