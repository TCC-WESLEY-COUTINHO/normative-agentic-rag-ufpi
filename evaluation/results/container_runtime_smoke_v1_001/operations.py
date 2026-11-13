"""WSL-only operational commands, sanitized evidence and immediate execution journal."""

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
IMAGE = "normative-agentic-rag-ufpi:runtime-smoke"
AGENT = "chatbot_ufpi_integrated_v1"


def now():
    return datetime.now(timezone.utc).isoformat()


def write(name, value):
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def journal(kind, **data):
    with (OUT / "execution_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {"recorded_at": now(), "event": kind, **data}, ensure_ascii=False
            )
            + "\n"
        )


def decision(subject, choice, reason):
    with (OUT / "decision_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "recorded_at": now(),
                    "subject": subject,
                    "choice": choice,
                    "reason": reason,
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def run(name, args, *, timeout=1800, check=False, stdin=None):
    start = time.monotonic()
    began = now()
    result = subprocess.run(
        args,
        cwd=ROOT,
        input=stdin,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    (OUT / (name + ".log")).write_text(result.stdout, encoding="utf-8")
    safe = [
        a.split("=", 1)[0] + "=<configured>"
        if "=" in a
        and any(
            k in a.split("=", 1)[0].upper()
            for k in ("KEY", "PASSWORD", "SECRET", "TOKEN", "DSN")
        )
        else a
        for a in args
    ]
    journal(
        name,
        command=safe,
        started_at=began,
        exit_code=result.returncode,
        duration_seconds=round(time.monotonic() - start, 3),
        stdout_file=name + ".log",
    )
    print(
        json.dumps(
            {
                "event": name,
                "exit_code": result.returncode,
                "duration_seconds": round(time.monotonic() - start, 3),
            }
        ),
        flush=True,
    )
    if check and result.returncode:
        print(result.stdout[-7000:], flush=True)
        raise RuntimeError(name)
    return result


def build():
    assert (OUT / "index_before.json").is_file(), "Snapshot before build is required"
    snapshot = json.loads((OUT / "index_before.json").read_text())
    assert snapshot["count"] == 507
    decision(
        "build",
        "Normal cached build from the existing checkout, root context and prepared Dockerfile.service.",
        "Compose points context .. from code/ and code/docker/Dockerfile.service; no source copy or --no-cache.",
    )
    decision(
        "docker_access",
        "Run Docker as WSL root; no user/group/socket modifications.",
        "Default Linux user receives socket permission denied and sudo -n requires a password; root daemon info succeeds.",
    )
    for name, cmd in [
        ("wsl_kernel", ["uname", "-a"]),
        ("wsl_distribution", ["cat", "/etc/os-release"]),
        ("wsl_python", ["python3", "--version"]),
        ("wsl_identity", ["id"]),
        ("wsl_groups", ["groups"]),
        ("wsl_disk", ["df", "-h"]),
        ("wsl_memory", ["free", "-h"]),
        ("docker_version", ["docker", "version"]),
        ("docker_info", ["docker", "info"]),
        ("docker_compose_version", ["docker", "compose", "version"]),
        ("docker_context", ["docker", "context", "ls"]),
        ("docker_socket", ["stat", "-c", "%U:%G %a", "/var/run/docker.sock"]),
        ("default_user_docker", ["runuser", "-u", "LOCAL_USER", "--", "docker", "info"]),
        (
            "default_user_sudo",
            ["runuser", "-u", "LOCAL_USER", "--", "sudo", "-n", "docker", "info"],
        ),
        ("repository_realpath", ["realpath", str(ROOT)]),
        (
            "repository_git_root",
            ["git", "-c", f"safe.directory={ROOT}", "rev-parse", "--show-toplevel"],
        ),
        ("preexisting_containers", ["docker", "ps", "-a", "--format", "{{.Names}}"]),
        ("preexisting_images", ["docker", "image", "ls"]),
    ]:
        run(name, cmd)
    audit = {}
    for path in [
        ".dockerignore",
        "code/.dockerignore",
        "code/docker/Dockerfile.service",
        "code/docker/Dockerfile.app",
        "code/compose.yaml",
        "code/compose.prod.yaml",
        "code/src/run_service.py",
    ]:
        raw = (ROOT / path).read_bytes()
        audit[path] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "crlf_count": raw.count(b"\r\n"),
            "lf_count": raw.count(b"\n"),
            "shebang": raw.startswith(b"#!"),
        }
    write(
        "packaging_before.json",
        {
            "files": audit,
            "root": str(ROOT),
            "index_path": str(ROOT / "code/.local/chroma"),
            "build_context": ".",
            "dockerfile": "code/docker/Dockerfile.service",
            "tag": IMAGE,
        },
    )
    before = now()
    started = time.monotonic()
    args = [
        "docker",
        "build",
        "--progress=plain",
        "-f",
        "code/docker/Dockerfile.service",
        "-t",
        IMAGE,
        ".",
    ]
    with (OUT / "build_01.log").open("w") as log:
        result = subprocess.run(args, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    elapsed = round(time.monotonic() - started, 3)
    value = {
        "command": args,
        "started_at": before,
        "exit_code": result.returncode,
        "duration_seconds": elapsed,
        "network": "Package/image downloads allowed during build; excluded from runtime call metrics.",
    }
    write("build_result.json", value)
    journal("build_01", **value, stdout_file="build_01.log")
    print(json.dumps(value), flush=True)
    if result.returncode:
        print((OUT / "build_01.log").read_text()[-10000:])
        raise SystemExit(result.returncode)
    inspected = json.loads(
        run("image_metadata", ["docker", "image", "inspect", IMAGE], check=True).stdout
    )[0]
    write(
        "image_metadata.json",
        {
            "id": inspected["Id"],
            "tags": inspected["RepoTags"],
            "size_bytes": inspected["Size"],
            "os": inspected["Os"],
            "architecture": inspected["Architecture"],
            "working_dir": inspected["Config"]["WorkingDir"],
            "cmd": inspected["Config"]["Cmd"],
            "environment_names": [
                v.split("=", 1)[0] for v in inspected["Config"]["Env"]
            ],
        },
    )


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build()
