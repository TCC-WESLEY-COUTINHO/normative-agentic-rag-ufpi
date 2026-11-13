"""Final syntax, artifact consistency, sensitive-format and diff checks."""

import ast
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
RUFF = ROOT / "code/.venv/Scripts/ruff.exe"


def main():
    scripts = list(OUT.glob("*.py")) + [
        ROOT / "code/tests/integration/test_service_container_healthcheck.py"
    ]
    checks = []
    for name, args in [
        ("ruff_check", [str(RUFF), "check", *map(str, scripts)]),
        ("ruff_format", [str(RUFF), "format", "--check", *map(str, scripts)]),
        ("diff_unstaged", ["git", "diff", "--check"]),
        ("diff_staged", ["git", "diff", "--cached", "--check"]),
        (
            "diff_branch",
            [
                "git",
                "diff",
                "--check",
                "ccf71406849634b7f7fae3f31b9d9d7217fac831..HEAD",
            ],
        ),
    ]:
        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
        (OUT / (name + ".log")).write_text(
            result.stdout + result.stderr, encoding="utf-8"
        )
        checks.append(
            {
                "name": name,
                "command": args,
                "exit_code": result.returncode,
                "stdout_file": name + ".log",
            }
        )
    candidates = [
        p
        for p in OUT.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    ]
    sensitive = re.compile(
        r"sk-(?:or-v1-|proj-)[A-Za-z0-9_-]{20,}|eyJhbGci[A-Za-z0-9_-]{30,}"
    )
    matches = []
    for path in candidates:
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            json.loads(text)
        elif path.suffix == ".jsonl":
            for line in text.splitlines():
                if line.strip():
                    json.loads(line)
        elif path.suffix == ".py":
            ast.parse(text, filename=str(path))
        if sensitive.search(text) and path.name != "verify_evidence.py":
            matches.append(str(path.relative_to(ROOT)))
    protocols = {}
    for name in ("technical_protocol.json", "compose_protocol.json"):
        value = json.loads((OUT / name).read_text(encoding="utf-8"))
        protocols[name] = all(
            hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == digest
            for p, digest in value["hashes"].items()
        )
    forbidden = [
        str(p.relative_to(ROOT))
        for p in candidates
        if p.name == ".env" or p.suffix in (".sqlite3", ".db", ".pyc")
    ]
    outcome = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "active_python_scripts_checked": len(scripts),
        "artifact_files_checked": len(candidates),
        "frozen_protocol_hashes": protocols,
        "sensitive_format_matches": matches,
        "forbidden_artifact_files": forbidden,
        "scan_limitations": "Only named API credential/JWT formats and forbidden filenames; actual .env never read/copied. Not a universal cryptographic scan.",
        "archived_sources_not_reformatted": True,
    }
    (OUT / "verification.json").write_text(
        json.dumps(outcome, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "checks": {row["name"]: row["exit_code"] for row in checks},
                "protocols": protocols,
                "sensitive_matches": len(matches),
                "forbidden_files": len(forbidden),
                "artifact_files": len(candidates),
            }
        )
    )
    assert all(row["exit_code"] == 0 for row in checks)
    assert all(protocols.values()) and not matches and not forbidden


if __name__ == "__main__":
    main()
