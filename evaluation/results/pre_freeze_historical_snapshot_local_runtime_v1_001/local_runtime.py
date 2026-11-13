"""Rebuild/check only the existing local API/UI, preserving runtime configuration.

The running environment is passed privately to Docker compose, never printed/saved.
"""

import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
WSL = ["wsl", "-d", "Ubuntu-24.04", "-u", "root", "--"]
WSL_ROOT = "."
sys.stdout.reconfigure(encoding="utf-8")


def inspect(name):
    return json.loads(subprocess.check_output([*WSL, "docker", "inspect", name]))[0]


def event(kind, **data):
    with (OUT / "execution_log.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(dict(timestamp=datetime.now(UTC).isoformat(), event=kind, **data)) + "\n"
        )


def main():
    mode = sys.argv[1]
    if mode in ["build", "up"]:
        services, previous = {}, {}
        for kind in ["agent_service", "streamlit_app"]:
            old = inspect("ufpi-tcc-local-" + kind + "-1")
            previous[kind] = old
            config, health = old["Config"], old["Config"]["Healthcheck"]
            port = 8080 if kind == "agent_service" else 8501
            services[kind] = dict(
                image=config["Image"],
                build=dict(
                    context=WSL_ROOT + ("" if kind == "agent_service" else "/code"),
                    dockerfile="code/docker/Dockerfile.service"
                    if kind == "agent_service"
                    else "docker/Dockerfile.app",
                ),
                environment=dict(item.split("=", 1) for item in config["Env"]),
                volumes=[
                    dict(
                        type=mount["Type"],
                        source=mount["Source"] if mount["Type"] == "bind" else mount["Name"],
                        target=mount["Destination"],
                    )
                    for mount in old["Mounts"]
                ],
                ports=[dict(target=port, published=str(port), host_ip="127.0.0.1")],
                healthcheck=dict(
                    test=health["Test"],
                    interval=str(health["Interval"]) + "ns",
                    timeout=str(health["Timeout"]) + "ns",
                    retries=health["Retries"],
                ),
            )
        spec = dict(services=services, volumes={"ufpi-tcc-local_tcc_sqlite": {"external": True}})
        command = [
            *WSL,
            "docker",
            "compose",
            "-p",
            "ufpi-tcc-local",
            "-f",
            "-",
            *(
                ["build", "agent_service", "streamlit_app"]
                if mode == "build"
                else [
                    "up",
                    "-d",
                    "--no-deps",
                    "--no-build",
                    "--pull",
                    "never",
                    "agent_service",
                    "streamlit_app",
                ]
            ),
        ]
        process = subprocess.run(
            command,
            input=json.dumps(spec).encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        event("local_container_" + mode, command=command, exit_code=process.returncode)
        print(process.stdout.decode("utf-8", errors="replace")[-2000:])
        if process.returncode:
            sys.exit(process.returncode)
        if mode == "up":
            for kind, old in previous.items():
                current = inspect("ufpi-tcc-local-" + kind + "-1")
                assert set(current["Config"]["Env"]) == set(old["Config"]["Env"])
                assert current["Mounts"] == old["Mounts"]
            event(
                "local_config_preserved",
                environment_identical=True,
                mounts_identical=True,
                loopback_ports=[8080, 8501],
            )
    elif mode == "health":
        import httpx

        for attempt in range(80):
            try:
                health = httpx.get("http://127.0.0.1:8080/health", timeout=2).json()
                if health.get("integrated_agent", {}).get("ready"):
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("Local API not ready")
        row = dict(
            health=health,
            readiness=httpx.get(
                "http://127.0.0.1:8080/agents/chatbot_ufpi_integrated_v1/readiness"
            ).json(),
            ui_health=httpx.get("http://127.0.0.1:8501/_stcore/health").text,
            containers={
                kind: inspect("ufpi-tcc-local-" + kind + "-1")["State"]
                .get("Health", {})
                .get("Status")
                for kind in ["agent_service", "streamlit_app"]
            },
        )
        event("local_health", **row)
        print(json.dumps(row))
    elif mode == "integrity":
        results = {}
        runtime = {}
        for kind in ["agent_service", "streamlit_app"]:
            code = (
                "import json,hashlib,pathlib; root=pathlib.Path('/app'); "
                "print(json.dumps({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() "
                "for p in (root/'code/src').rglob('*.py')}))"
            )
            actual = json.loads(
                subprocess.check_output(
                    [*WSL, "docker", "exec", "ufpi-tcc-local-" + kind + "-1", "python", "-c", code]
                )
            )
            assert all(
                value == hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name, value in actual.items()
            )
            results[kind] = actual
            current = inspect("ufpi-tcc-local-" + kind + "-1")
            runtime[kind] = dict(
                container_id=current["Id"],
                image_id=current["Image"],
                image_name=current["Config"]["Image"],
                health=current["State"].get("Health", {}).get("Status"),
            )
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
        row = dict(
            checkout_head=head,
            identical=True,
            hashes=results,
            containers=runtime,
            api_url="http://127.0.0.1:8080",
            ui_url="http://localhost:8501",
        )
        (OUT / "runtime_integrity.json").write_text(
            json.dumps(row, indent=2) + "\n", encoding="utf-8"
        )
        event(
            "installed_source_integrity",
            identical=True,
            files={kind: len(values) for kind, values in results.items()},
            checkout_head=head,
        )
        print(
            json.dumps(
                dict(
                    identical=True,
                    containers=runtime,
                    files={kind: len(values) for kind, values in results.items()},
                )
            )
        )


if __name__ == "__main__":
    main()
