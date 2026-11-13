"""Reproducible technical audit commands; no secrets or index writes."""

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
os.environ.update(
    PYTHONPATH=os.pathsep.join(
        [str(ROOT / "code/src"), str(ROOT / "code/.venv/Lib/site-packages")]
    ),
    PYTHONIOENCODING="utf-8",
    PYTHONDONTWRITEBYTECODE="1",
    ANONYMIZED_TELEMETRY="False",
    LANGFUSE_TRACING="false",
    LANGCHAIN_TRACING_V2="false",
    LANGSMITH_TRACING="false",
)
sys.path[:0] = [str(ROOT / "code/src"), str(ROOT / "code/.venv/Lib/site-packages")]
sys.stdout.reconfigure(encoding="utf-8")


def write(name, value):
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def event(kind, **data):
    with (OUT / "execution_log.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                dict(timestamp=datetime.now(UTC).isoformat(), event=kind, **data),
                ensure_ascii=False,
            )
            + "\n"
        )


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8").strip()


def hashes():
    names = git(
        "ls-files",
        "code/src",
        "data",
        "evaluation/corpora",
        "code/pyproject.toml",
        "code/uv.lock",
    ).splitlines()
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in names
        if (ROOT / name).is_file()
    }


def index():
    import chromadb
    from chromadb.config import Settings

    from rag_baseline.incremental_index import snapshot_collection

    client = chromadb.PersistentClient(
        path=str(ROOT / "code/.local/chroma"),
        settings=Settings(anonymized_telemetry=False),
    )
    try:
        snapshot = snapshot_collection(
            client.get_collection("ufpi_duas_regulacoes_setor", embedding_function=None)
        )
        return {key: snapshot[key] for key in ["count", "sha256"]}
    finally:
        client._system.stop()


def main():
    mode, *args = sys.argv[1:]
    if mode == "init":
        value = dict(
            initial_head=git("rev-parse", "HEAD"),
            initial_branch=git("branch", "--show-current"),
            initial_status_observed_before_artifact_creation="",
            initial_git_commands={
                command: git(*command.split())
                for command in [
                    "status --short",
                    "branch --show-current",
                    "rev-parse HEAD",
                    "log -15 --oneline --decorate",
                    "diff",
                    "diff --cached",
                ]
            },
            files_before=hashes(),
            index_before=index(),
        )
        assert value["index_before"]["count"] == 507
        write("preservation.json", value)
        write("test_results.json", [])
        event(
            "initial_snapshot",
            initial_head=value["initial_head"],
            initial_branch=value["initial_branch"],
            initial_status="clean; only audit.py created before machine-readable snapshot",
            index=value["index_before"],
        )
        print(
            json.dumps(
                {key: value[key] for key in ["initial_head", "initial_branch", "index_before"]}
            )
        )
    elif mode == "check":
        label, *command = args
        start = time.monotonic()
        process = subprocess.run(
            command,
            cwd=ROOT / "code",
            env=os.environ,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        output = process.stdout.decode("utf-8", errors="replace")
        lines = output.replace("\r", "").splitlines()
        row = dict(
            label=label,
            command=command,
            cwd=str(ROOT / "code"),
            exit_code=process.returncode,
            seconds=round(time.monotonic() - start, 3),
            summary=[
                line
                for line in lines
                if (
                    " in " in line
                    and any(word in line for word in ["passed", "failed", "skipped", "warnings"])
                )
                or line.startswith(("ERROR:", "All checks", "All ", "Would reformat"))
            ],
            failed_tests=[line for line in lines if line.startswith("FAILED ")],
            skipped_tests=[line for line in lines if line.startswith("SKIPPED ")],
        )
        path = OUT / "test_results.json"
        rows = json.loads(path.read_text("utf-8"))
        rows.append(row)
        write("test_results.json", rows)
        event("verification", **row)
        print(output[-14000:])
        sys.exit(process.returncode)
    elif mode == "after":
        value = json.loads((OUT / "preservation.json").read_text("utf-8"))
        value.update(index_after=index(), files_after=hashes())
        value["index_identical"] = value["index_before"] == value["index_after"]
        value["changed_files"] = [
            name
            for name, before in value["files_before"].items()
            if value["files_after"].get(name) != before
        ]
        allowed = {
            "code/src/rag_baseline/agent_graph.py",
            "code/src/rag_baseline/conversation_policy.py",
            "code/src/rag_baseline/conversation_graph.py",
            "code/src/rag_baseline/integrated_runtime.py",
            "code/src/rag_baseline/ui_presentation.py",
            "code/src/streamlit_app.py",
        }
        assert set(value["changed_files"]) <= allowed, value["changed_files"]
        assert value["index_identical"] and value["index_after"]["count"] == 507
        value["protected_files_identical"] = {
            name: True for name in value["files_before"] if name not in allowed
        }
        value["added_production_files"] = sorted(
            set(value["files_after"]) - set(value["files_before"])
        )
        assert set(value["added_production_files"]) <= {"code/src/rag_baseline/scope_gate.py"}
        write("preservation.json", value)
        event(
            "final_snapshot",
            index=value["index_after"],
            index_identical=True,
            changed_files=value["changed_files"],
            protected_files=len(value["protected_files_identical"]),
        )
        print(
            json.dumps(
                dict(
                    index=value["index_after"],
                    changed_files=value["changed_files"],
                    protected_identical=len(value["protected_files_identical"]),
                )
            )
        )
    elif mode == "probes":
        import asyncio

        import streamlit

        sys.path.insert(0, str(ROOT / "code/tests/rag_baseline"))
        from conversation_policy_fixtures import collect_probes

        records = asyncio.run(collect_probes())
        path = OUT / "regression_cases.json"
        data = json.loads(path.read_text("utf-8")) if path.exists() else {}
        data[args[0]] = dict(
            kind="Real integrated graph, facade, RouterV1, retrieval and guard; controlled external provider I/O, no live provider calls",
            streamlit_version=streamlit.__version__,
            action_probes=records,
        )
        write("regression_cases.json", data)
        event(
            "action_probes",
            phase=args[0],
            count=len(records),
            mismatches=sum(row["expected_action"] != row["observed_action"] for row in records),
        )
        print(
            json.dumps(
                [
                    dict(
                        question=row["question"],
                        action=row["observed_action"],
                        router=row["router_calls"],
                        retrieval=row["retrieval_calls"],
                        provider=row["provider_calls"],
                        correlation_changed=row["correlation_changed"],
                    )
                    for row in records
                ],
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
