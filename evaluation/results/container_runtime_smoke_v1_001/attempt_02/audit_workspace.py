"""Logical index snapshots and byte preservation using the existing project algorithm."""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
os.environ["ANONYMIZED_TELEMETRY"] = "False"
sys.path.insert(0, str(ROOT / "code/src"))


def write(name, value):
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def git(*args):
    return (
        subprocess.check_output(
            ["git", "-c", f"safe.directory={ROOT}", *args], cwd=ROOT
        )
        .decode("utf-8")
        .strip()
    )


def snapshot():
    import chromadb
    from chromadb.config import Settings
    from rag_baseline.incremental_index import snapshot_collection

    client = chromadb.PersistentClient(
        path=str(ROOT / "code/.local/chroma"),
        settings=Settings(anonymized_telemetry=False),
    )
    try:
        return snapshot_collection(
            client.get_collection("ufpi_duas_regulacoes_setor", embedding_function=None)
        )
    finally:
        client._system.stop()


if __name__ == "__main__":
    phase = sys.argv[1]
    stamp = datetime.now(timezone.utc).isoformat()
    if phase == "before":
        audit = {
            key: git(*args)
            for key, args in {
                "status_after_branch_and_evidence_directory": ["status", "--short"],
                "branch": ["branch", "--show-current"],
                "head": ["rev-parse", "HEAD"],
                "log": ["log", "-15", "--oneline", "--decorate"],
                "diff": ["diff"],
                "cached_diff": ["diff", "--cached"],
                "stat": ["diff", "--stat"],
            }.items()
        }
        audit.update(
            recorded_at=stamp,
            initial_observation={
                "branch": "feat/runtime-registration-packaging-v1",
                "head": "ccf71406849634b7f7fae3f31b9d9d7217fac831",
                "status": "",
                "diff": "",
                "cached_diff": "",
                "stat": "",
                "source": "Read-only shell audit before branch creation; log matches source HEAD.",
            },
        )
        write("initial_audit.json", audit)
        paths = (
            subprocess.check_output(
                ["git", "-c", f"safe.directory={ROOT}", "ls-files", "-z"], cwd=ROOT
            )
            .decode()
            .split("\0")
        )
        files = {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths if p
        }
        write("preservation_before.json", {"recorded_at": stamp, "files": files})
        index = snapshot()
        write("index_before.json", index)
        print(
            json.dumps(
                {
                    "files": len(files),
                    "index_count": index["count"],
                    "index_sha256": index["sha256"],
                }
            )
        )
    elif phase == "after":
        before = json.loads(
            (OUT / "preservation_before.json").read_text(encoding="utf-8")
        )
        changes = [
            {
                "path": p,
                "before": h,
                "after": hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                if (ROOT / p).is_file()
                else None,
            }
            for p, h in before["files"].items()
            if not (ROOT / p).is_file()
            or hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != h
        ]
        index = snapshot()
        write("index_after.json", index)
        first = json.loads((OUT / "index_before.json").read_text(encoding="utf-8"))
        write(
            "preservation.json",
            {
                "recorded_at": stamp,
                "initial_files": len(before["files"]),
                "unchanged": len(before["files"]) - len(changes),
                "changes": changes,
                "index_identical": first == index,
                "index_count": index["count"],
                "index_sha256": index["sha256"],
            },
        )
        print(
            json.dumps(
                {
                    "changed_files": [c["path"] for c in changes],
                    "index_identical": first == index,
                    "index_count": index["count"],
                    "index_sha256": index["sha256"],
                }
            )
        )
        if first != index:
            raise SystemExit("BLOCKER: index logical content changed")
