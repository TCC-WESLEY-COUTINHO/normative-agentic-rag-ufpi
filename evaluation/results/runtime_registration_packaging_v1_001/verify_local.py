"""Run declared regression selections, recording actual command/output/status."""

import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
CODE = ROOT / "code"


def write(name, value):
    (OUT / name).write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def main():
    previous = json.loads(
        (OUT.parent / "calculator_tool_routing_v1_001/test_results.json").read_text(
            encoding="utf-8"
        )
    )
    selections = [
        (
            "runtime",
            [
                "tests/rag_baseline/test_integrated_runtime.py",
                "tests/rag_baseline/test_runtime_packaging.py",
            ],
        )
    ]
    selections += [
        (row["selection"], row["command"][3 : row["command"].index("-q")]) for row in previous
    ]
    if "--checks-only" in sys.argv:
        selections = []
    results = []
    env = dict(
        os.environ,
        PYTHONIOENCODING="utf-8",
        ANONYMIZED_TELEMETRY="False",
        LANGCHAIN_TRACING_V2="false",
        LANGSMITH_TRACING="false",
    )
    for name, paths in selections:
        command = [
            sys.executable,
            "-m",
            "pytest",
            *paths,
            "-q",
            "-p",
            "no:cacheprovider",
            "--tb=short",
        ]
        started = datetime.now(UTC).isoformat()
        tick = time.monotonic()
        run = subprocess.run(
            command, cwd=CODE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        (OUT / f"pytest_{name}.txt").write_bytes(run.stdout)
        output = run.stdout.decode("utf-8", errors="replace")
        summaries = [
            line
            for line in output.splitlines()
            if re.search(r"\d+ (?:passed|failed|skipped|error)", line)
        ]
        summary = summaries[-1] if summaries else output[-500:]
        row = dict(
            selection=name,
            command=command,
            cwd=str(CODE),
            timestamp=started,
            seconds=round(time.monotonic() - tick, 3),
            exit_code=run.returncode,
            summary=summary,
        )
        for metric in ["passed", "failed", "skipped", "warnings", "errors"]:
            match = re.search(rf"(\d+) {metric}", summary)
            row[metric] = int(match[1]) if match else 0
        results.append(row)
        write("test_results.json", results)
        print(name, "->", summary, "exit", run.returncode, flush=True)
        if run.returncode:
            raise SystemExit(run.returncode)
    files = [
        "code/src/rag_baseline/integrated_runtime.py",
        "code/src/agents/agents.py",
        "code/src/service/service.py",
        "code/src/schema/schema.py",
        "code/tests/rag_baseline/test_integrated_runtime.py",
        "code/tests/rag_baseline/test_runtime_packaging.py",
        "code/tests/rag_baseline/test_typed_normative_transport.py",
    ]
    files = [str(ROOT / path) for path in files]
    evidence_files = [str(p) for p in OUT.glob("*.py")]
    checks = {}
    for name, command in [
        (
            "ruff_check",
            [
                str(CODE / ".venv/Scripts/ruff.exe"),
                "check",
                "--config",
                str(CODE / "pyproject.toml"),
                *files,
            ],
        ),
        (
            "ruff_format",
            [
                str(CODE / ".venv/Scripts/ruff.exe"),
                "format",
                "--check",
                "--config",
                str(CODE / "pyproject.toml"),
                *files,
            ],
        ),
        (
            "ruff_evidence_check",
            [
                str(CODE / ".venv/Scripts/ruff.exe"),
                "check",
                "--config",
                str(CODE / "pyproject.toml"),
                *evidence_files,
            ],
        ),
        (
            "ruff_evidence_format",
            [
                str(CODE / ".venv/Scripts/ruff.exe"),
                "format",
                "--check",
                "--config",
                str(CODE / "pyproject.toml"),
                *evidence_files,
            ],
        ),
        ("git_diff_check", ["git", "diff", "--check"]),
        ("git_cached_diff_check", ["git", "diff", "--cached", "--check"]),
        ("git_status", ["git", "status", "--short"]),
    ]:
        cwd = CODE if name in {"ruff_check", "ruff_format"} else ROOT
        run = subprocess.run(
            command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        (OUT / f"{name}.txt").write_bytes(run.stdout)
        checks[name] = dict(
            command=command,
            cwd=str(cwd),
            exit_code=run.returncode,
            output=run.stdout.decode("utf-8", errors="replace"),
        )
        write("verification.json", checks)
        print(name, "exit", run.returncode, flush=True)
        if run.returncode:
            raise SystemExit(run.returncode)


if __name__ == "__main__":
    main()
