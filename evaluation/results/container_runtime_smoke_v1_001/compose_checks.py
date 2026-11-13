"""Validate production statically and run only the dev service with isolated smoke data."""

import json
import subprocess
import time
import urllib.request
from pathlib import Path
from operations import IMAGE, OUT, ROOT, decision, journal, run, write

base = Path(json.loads((OUT / "temporary_workspace.json").read_text())["path"])
work = base / ("compose-" + str(time.time_ns()))
work.mkdir()
for child in ("state", "observations"):
    (work / child).mkdir()
interpolation = work / "interpolation.env"
interpolation.write_text("POSTGRES_PASSWORD=smoke-placeholder-not-a-password\n")
for name in ("compose.yaml", "compose.prod.yaml"):
    run(
        "config_" + name.replace(".", "_"),
        [
            "docker",
            "compose",
            "--env-file",
            str(interpolation),
            "-f",
            str(ROOT / "code" / name),
            "config",
            "--quiet",
            "--no-env-resolution",
        ],
    )
override = work / "override.yaml"
override.write_text(f'''services:
  agent_service:
    image: {IMAGE}
    container_name: normative-rag-compose-runtime-smoke-v1
    env_file: !reset []
    depends_on: !reset {{}}
    ports: !override
      - "127.0.0.1:18081:8080"
    volumes: !override
      - "{ROOT / "code/.local/chroma"}:/app/index"
      - "{work / "state"}:/app/state"
      - "{work / "observations"}:/observations"
      - "{OUT}:/smoke:ro"
    environment: !override
      HOST: 0.0.0.0
      PORT: 8080
      DATABASE_TYPE: sqlite
      SQLITE_DB_PATH: /app/state/checkpoints.db
      CHROMA_PERSIST_DIR: /app/index
      OPENROUTER_API_KEY: controlled-not-a-real-credential
      USE_FAKE_MODEL: 'true'
      ANONYMIZED_TELEMETRY: 'False'
      LANGFUSE_TRACING: 'false'
      LANGCHAIN_TRACING_V2: 'false'
      LANGSMITH_TRACING: 'false'
      PYTHONDONTWRITEBYTECODE: '1'
      PYTHONPATH: /smoke:/app/code/src
''')
args = [
    "docker",
    "compose",
    "--project-name",
    "normative-runtime-smoke-v1",
    "--env-file",
    str(interpolation),
    "-f",
    str(ROOT / "code/compose.yaml"),
    "-f",
    str(override),
]
run("compose_safe_config", args + ["config", "--quiet"])
decision(
    "compose_dev",
    "Run agent_service alone, no deps/build/pull; reset env_file, credentials mount, dependencies and host ports in a temporary override.",
    "Uses the built image, real index, dedicated SQLite and network guard. Production is config-only; no PostgreSQL/Streamlit started.",
)
run(
    "compose_up_service",
    args + ["up", "-d", "--no-deps", "--no-build", "--pull", "never", "agent_service"],
    check=True,
)
try:
    deadline = time.monotonic() + 90
    response = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:18081/health", timeout=2
            ) as server:
                response = json.load(server)
            break
        except OSError:
            time.sleep(1)
    write(
        "compose_service_health.json",
        {"http_health": response, "dependencies_started": [], "workspace": str(work)},
    )
    # Execute the unchanged dev healthcheck command in the actual image/service.
    rendered = subprocess.check_output(
        args + ["config", "--format", "json"], cwd=ROOT, text=True
    )
    command = json.loads(rendered)["services"]["agent_service"]["healthcheck"]["test"]
    assert command[0] == "CMD"
    result = run(
        "compose_dev_healthcheck_command",
        ["docker", "exec", "normative-rag-compose-runtime-smoke-v1", *command[1:]],
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        actual = json.loads(
            subprocess.check_output(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{json .State}}",
                    "normative-rag-compose-runtime-smoke-v1",
                ],
                text=True,
            )
        )
        if actual.get("Health", {}).get("Status") == "healthy":
            break
        time.sleep(1)
    write(
        "compose_docker_health.json",
        {
            "status": actual.get("Health", {}).get("Status"),
            "healthcheck_exit_code": result.returncode,
        },
    )
    journal(
        "compose_dev_healthcheck_result",
        exit_code=result.returncode,
        http_process_healthy=response is not None,
    )
    run(
        "compose_service_state",
        [
            "docker",
            "inspect",
            "--format",
            "{{json .State}}",
            "normative-rag-compose-runtime-smoke-v1",
        ],
    )
finally:
    run("compose_stop", args + ["stop", "--timeout", "30", "agent_service"])
    run("compose_service_logs", args + ["logs", "--no-color", "agent_service"])
    run(
        "compose_service_final_state",
        [
            "docker",
            "inspect",
            "--format",
            "{{json .State}}",
            "normative-rag-compose-runtime-smoke-v1",
        ],
    )
    run("compose_down", args + ["down"])
    attempts = work / "observations/network_attempts.jsonl"
    write(
        "compose_network_observation.json",
        {
            "blocked_external_attempts": len(attempts.read_text().splitlines())
            if attempts.exists()
            else 0,
            "guard_loaded": (work / "observations/guard_loaded.jsonl").exists(),
        },
    )
