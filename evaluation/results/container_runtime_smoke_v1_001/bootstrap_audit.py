"""Temporary WSL audit dependencies; never installs into the project or system Python."""

import json
import os
import subprocess
import tempfile
import time
import urllib.request
import venv
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
work = Path(tempfile.mkdtemp(prefix="normative-runtime-smoke-", dir="/var/tmp"))
(OUT / "temporary_workspace.json").write_text(
    json.dumps(
        {
            "path": str(work),
            "purpose": "isolated snapshot dependencies and smoke SQLite volumes",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        indent=2,
    )
    + "\n"
)
env = {
    "PATH": os.environ["PATH"],
    "HOME": str(work),
    "LANG": "C.UTF-8",
    "ANONYMIZED_TELEMETRY": "False",
    "PYTHONDONTWRITEBYTECODE": "1",
}
venv.EnvBuilder(with_pip=False).create(work / "audit-venv")
python = str(work / "audit-venv/bin/python")
with urllib.request.urlopen(
    "https://bootstrap.pypa.io/pip/pip.pyz", timeout=60
) as response:
    (work / "pip.pyz").write_bytes(response.read())
started = time.monotonic()
with (OUT / "snapshot_dependency_setup_02.log").open("w") as log:
    result = subprocess.run(
        [
            python,
            str(work / "pip.pyz"),
            "--isolated",
            "install",
            "chromadb==1.0.15",
            "pydantic==2.10.6",
            "pydantic-settings==2.6.1",
            "httpx==0.27.2",
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
    )
print(
    json.dumps(
        {
            "temporary_audit_setup_exit": result.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "workspace": str(work),
        }
    ),
    flush=True,
)
if result.returncode:
    raise SystemExit(result.returncode)
result = subprocess.run(
    [python, str(OUT / "audit_workspace.py"), "before"],
    cwd=ROOT,
    env=env,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)
(OUT / "snapshot_before_02.log").write_text(result.stdout)
print(result.stdout, flush=True)
if result.returncode:
    raise SystemExit(result.returncode)
subprocess.run([python, str(OUT / "operations.py"), "build"], cwd=ROOT, check=True)
