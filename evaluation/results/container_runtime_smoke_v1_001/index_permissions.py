"""Post-smoke access check as the normal WSL developer; performs no write."""

import json
import os
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
index = ROOT / "code/.local/chroma"
rows = []
for path in [index, *sorted(index.rglob("*"))]:
    info = path.stat()
    rows.append(
        {
            "path": str(path.relative_to(index.parent)),
            "uid": info.st_uid,
            "gid": info.st_gid,
            "mode": stat.filemode(info.st_mode),
            "readable": os.access(path, os.R_OK),
            "writable": os.access(path, os.W_OK),
            "bytes": info.st_size,
        }
    )
result = {
    "uid": os.getuid(),
    "gid": os.getgid(),
    "all_readable": all(r["readable"] for r in rows),
    "all_writable": all(r["writable"] for r in rows),
    "files": rows,
    "limitation": "No pre-run physical ownership manifest; this proves current normal-user access only. No chmod/chown/group changes performed.",
}
print(json.dumps(result))
