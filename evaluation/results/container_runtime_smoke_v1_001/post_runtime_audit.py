"""Final logical index and normal-user permission checks, after real runtime mounts."""

import json
import os
from pathlib import Path
from operations import OUT, ROOT, run, write

base = Path(json.loads((OUT / "temporary_workspace.json").read_text())["path"])
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
run(
    "snapshot_after",
    [str(base / "audit-venv/bin/python"), str(OUT / "audit_workspace.py"), "after"],
    check=True,
)
permissions = run(
    "index_permissions_normal_user",
    ["runuser", "-u", "LOCAL_USER", "--", "python3", str(OUT / "index_permissions.py")],
    check=True,
)
values = json.loads(permissions.stdout)
assert values["all_readable"] and values["all_writable"]
write("index_permissions.json", values)
run(
    "final_runtime_containers",
    [
        "docker",
        "ps",
        "-a",
        "--filter",
        "label=normative.smoke=container-runtime-v1",
        "--format",
        "{{.Names}}",
    ],
)
run(
    "final_smoke_networks",
    [
        "docker",
        "network",
        "ls",
        "--filter",
        "label=normative.smoke=container-runtime-v1",
        "--format",
        "{{.Name}}",
    ],
)
for name in ("technical_protocol.json", "compose_protocol.json"):
    import hashlib

    protocol = json.loads((OUT / name).read_text())
    mismatches = [
        path
        for path, digest in protocol["hashes"].items()
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest
    ]
    assert not mismatches, mismatches
write(
    "frozen_protocol_verification.json",
    {
        "runtime_protocol_hashes_preserved": True,
        "compose_protocol_hashes_preserved": True,
    },
)
print(
    json.dumps(
        {
            "index_identical": True,
            "normal_user_readable_writable": True,
            "frozen_protocols_unchanged": True,
        }
    ),
    flush=True,
)
