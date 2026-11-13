"""Capture reproducible local engineering checks without reading .env secrets."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
CODE = ROOT / "code"
sys.stdout.reconfigure(encoding="utf-8")
label, *args = sys.argv[1:]
env = dict(
    os.environ,
    PYTHONPATH=os.pathsep.join(
        [str(CODE / "src"), str(CODE / ".venv/Lib/site-packages")]
    ),
    PYTHONDONTWRITEBYTECODE="1",
    ANONYMIZED_TELEMETRY="False",
    LANGFUSE_TRACING="false",
    LANGCHAIN_TRACING_V2="false",
    LANGSMITH_TRACING="false",
)
env.pop("AUTH_SECRET", None)
env.pop("USE_FAKE_MODEL", None)
command = [sys.executable, "-m", *args]
start = time.monotonic()
timestamp = datetime.now(timezone.utc).isoformat()
p = subprocess.run(
    command, cwd=CODE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
)
(OUT / (label + ".log")).write_bytes(p.stdout)
row = dict(
    timestamp=timestamp,
    event="check",
    label=label,
    command=command,
    cwd=str(CODE),
    exit_code=p.returncode,
    seconds=round(time.monotonic() - start, 3),
    summary=p.stdout.decode("utf-8", errors="replace").splitlines()[-1:],
)
with (OUT / "execution_log.jsonl").open("a", encoding="utf-8") as f:
    f.write(json.dumps(row) + "\n")
print(json.dumps(row))
print(p.stdout.decode("utf-8", errors="replace")[-12000:])
sys.exit(p.returncode)
