"""Frozen HTTP/container smokes. Real image, real registry/lifespan/core/index/SQLite."""

import hashlib
import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from operations import AGENT, IMAGE, OUT, ROOT, decision, journal, now, run, write

WORK = Path(json.loads((OUT / "temporary_workspace.json").read_text())["path"])
NETWORK = "normative-rag-runtime-smoke-v1-net"
PORT = 18080
BASE = f"http://127.0.0.1:{PORT}"
NATIVE = "normative-rag-runtime-smoke-v1"
CONTROLLED = NATIVE + "-controlled"
RESULTS, MESSAGES, CREATED = [], [], []
FIELDS = ("normative_result", "grounded_followup_result", "calculator_result")
PRIVATE = {
    "conversation_memory",
    "last_normative_result_persistence",
    "compatibility_stamp",
    "storage_key",
    "internal_audit",
    "raw_answer",
    "output_audit",
    "api_key",
}


def keys(value):
    if isinstance(value, dict):
        return set(value) | set().union(*(keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(keys(v) for v in value))
    return set()


def verify(name, success, payload=None, reason=None):
    row = {
        "case": name,
        "status": "PASS" if success else "FAIL",
        "payload": payload,
        "reason": reason,
        "recorded_at": now(),
    }
    RESULTS.append(row)
    write("probe_results.json", RESULTS)
    journal("probe", case=name, status=row["status"])
    print(json.dumps({"case": name, "status": row["status"]}), flush=True)
    return bool(success)


def http(path, payload=None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    request = urllib.request.Request(
        BASE + path, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        response = urllib.request.urlopen(request, timeout=45)
    except urllib.error.HTTPError as error:
        response = error
    raw = response.read().decode()
    return {
        "status": response.status,
        "content_type": response.headers.get("Content-Type"),
        "body": raw,
    }


def body(response):
    return json.loads(response["body"])


def invoke(text, *, user="smoke-A", thread="smoke-X", stream=False):
    path = f"/{AGENT}/" + ("stream" if stream else "invoke")
    response = http(
        path,
        {"message": text, "user_id": user, "thread_id": thread, "stream_tokens": True}
        if stream
        else {"message": text, "user_id": user, "thread_id": thread},
    )
    if stream:
        return response
    if response["status"] == 200:
        MESSAGES.append(body(response))
    return response


def typed(message, expected=None):
    return not (keys(message) & PRIVATE) and [
        f for f in FIELDS if message.get(f) is not None
    ] == ([] if expected is None else [expected])


def sse(name, text, expected, *, thread):
    response = invoke(text, stream=True, thread=thread)
    (OUT / (name + ".sse")).write_text(response["body"])
    try:
        frames = [
            line[6:]
            for line in response["body"].splitlines()
            if line.startswith("data: ")
        ]
        event = json.loads(frames[0])
        message = event["content"]
        MESSAGES.append(message)
        success = (
            response["status"] == 200
            and response["content_type"].startswith("text/event-stream")
            and len(frames) == 2
            and frames[1] == "[DONE]"
            and event["type"] == "message"
            and typed(message, expected)
        )
    except (KeyError, IndexError, ValueError, TypeError):
        message, success = response, False
    verify(name, success, message)
    return message


def create(name, *, kind="native", negative=None, obs_name=None):
    observation = WORK / (obs_name or name)
    observation.mkdir()
    state = WORK / (name + "-sqlite")
    state.mkdir()
    args = [
        "docker",
        "create",
        "--name",
        name,
        "--label",
        "normative.smoke=container-runtime-v1",
        "--network",
        NETWORK,
        "-p",
        f"127.0.0.1:{PORT}:8080",
        "--mount",
        f"type=bind,src={OUT},dst=/smoke,readonly",
        "--mount",
        f"type=bind,src={observation},dst=/observations",
        "--mount",
        f"type=bind,src={state},dst=/app/state",
    ]
    environment = {
        "HOST": "0.0.0.0",
        "PORT": "8080",
        "DATABASE_TYPE": "sqlite",
        "SQLITE_DB_PATH": "/app/state/checkpoints.db",
        "CHROMA_PERSIST_DIR": "/app/index",
        "PYTHONPATH": "/smoke:/app/code/src",
        "PYTHONDONTWRITEBYTECODE": "1",
        "USE_FAKE_MODEL": "true",
        "ANONYMIZED_TELEMETRY": "False",
        "LANGCHAIN_TRACING_V2": "false",
        "LANGSMITH_TRACING": "false",
        "LANGFUSE_TRACING": "false",
    }
    if negative != "missing_provider":
        environment["OPENROUTER_API_KEY"] = "controlled-not-a-real-credential"
    if negative == "missing_index":
        environment["CHROMA_PERSIST_DIR"] = "/missing-index-smoke"
    if negative == "invalid_registry":
        invalid = WORK / "invalid-registry.json"
        invalid.write_text("{}")
        args += [
            "--mount",
            f"type=bind,src={invalid},dst=/invalid-registry.json,readonly",
        ]
        environment["NORMATIVE_REGISTRY_PATH"] = "/invalid-registry.json"
    if negative is None:
        args += [
            "--mount",
            f"type=bind,src={ROOT / 'code/.local/chroma'},dst=/app/index",
        ]
    for key, value in environment.items():
        args += ["-e", f"{key}={value}"]
    args += [IMAGE]
    if kind == "controlled":
        args += ["python", "/smoke/container_entry.py"]
    run("create_" + name, args, check=True)
    CREATED.append((name, observation))
    mounts = json.loads(
        run(
            "mounts_" + name,
            ["docker", "inspect", "--format", "{{json .Mounts}}", name],
            check=True,
        ).stdout
    )
    write("mounts_" + name + ".json", mounts)
    return observation


def start(name, phase):
    run("start_" + phase, ["docker", "start", name], check=True)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            response = http("/health")
            if response["status"] == 200:
                return True
        except (OSError, TimeoutError):
            pass
        state = run_quiet(["docker", "inspect", "--format", "{{.State.Running}}", name])
        if state.strip() != "true":
            break
        time.sleep(1)
    run("startup_failed_" + phase, ["docker", "logs", name])
    return False


def run_quiet(args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def stop(name, observation, phase):
    run("stop_" + phase, ["docker", "stop", "--time", "30", name])
    run("logs_" + phase, ["docker", "logs", name])
    state = json.loads(
        run(
            "state_" + phase,
            ["docker", "inspect", "--format", "{{json .State}}", name],
            check=True,
        ).stdout
    )
    verify(
        "shutdown_" + phase,
        not state["Running"] and state["ExitCode"] == 0 and not state["OOMKilled"],
        state,
    )
    network_file = observation / "network_attempts.jsonl"
    attempts = network_file.read_text().splitlines() if network_file.exists() else []
    loaded = (observation / "guard_loaded.jsonl").exists()
    verify(
        "external_call_avoidance_" + phase,
        loaded and not attempts,
        {
            "guard_loaded": loaded,
            "blocked_attempts": len(attempts),
            "network_internal": False,
        },
    )
    for source in observation.iterdir():
        if source.is_file():
            shutil.copyfile(source, OUT / (phase + "_" + source.name))
    closed = observation / "closed_resources.json"
    if closed.exists():
        values = json.loads(closed.read_text())
        verify("resource_close_" + phase, all(values.values()), values)


def metadata(phase, ready=True, code=None):
    info, health, readiness = (
        http("/info"),
        http("/health"),
        http(f"/agents/{AGENT}/readiness"),
    )
    infos, health_data, checks = body(info), body(health), body(readiness)
    entry = next((item for item in infos.get("agents", []) if item["key"] == AGENT), {})
    verify(
        "health_" + phase,
        health["status"] == 200 and health_data.get("status") == "ok",
        health_data,
    )
    verify(
        "readiness_" + phase,
        readiness["status"] == 200
        and checks.get("ready") == ready
        and checks.get("registered") is True
        and (code is None or checks.get("reason_code") == code),
        checks,
    )
    verify(
        "info_" + phase,
        info["status"] == 200
        and entry.get("experimental") is True
        and entry.get("available") == ready,
        entry,
    )
    verify(
        "default_" + phase,
        infos.get("default_agent") == "chatbot_ufpi_v2",
        {"default_agent": infos.get("default_agent")},
    )


def main():
    assert WORK.is_dir()
    assert not (OUT / "technical_protocol.json").exists(), (
        "Frozen protocol already exists"
    )
    image = json.loads((OUT / "image_metadata.json").read_text())
    index = json.loads((OUT / "index_before.json").read_text())
    files = [
        "code/docker/Dockerfile.service",
        "code/compose.yaml",
        "code/compose.prod.yaml",
        ".dockerignore",
        "data/normative_registry.json",
    ]
    files += [str(p.relative_to(ROOT)).replace("\\", "/") for p in OUT.glob("*.py")]
    registry = json.loads(
        (ROOT / "data/normative_registry.json").read_text(encoding="utf-8")
    )
    protocol = {
        "frozen_at": now(),
        "source_head": run_quiet(
            ["git", "-c", f"safe.directory={ROOT}", "rev-parse", "HEAD"]
        ),
        "image": image,
        "index_before_sha256": index["sha256"],
        "registry_fingerprint": hashlib.sha256(
            json.dumps(
                registry, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        "hashes": {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in files
        },
        "inputs": [
            "Oi",
            "2+2",
            "Adicione 10 dias corridos a 05/11/2026.",
            "Resolução 177/2012, art. 68",
            "Repita.",
        ],
        "identities": {"owner": "smoke-A", "other": "smoke-B", "thread": "smoke-X"},
        "expected": {
            "native": "normal CMD, ready index 507, direct untyped, calculator 4, date 15/11/2026, complete SSE message+DONE",
            "controlled": "existing provider_factory seam, metadata_exact normative ANSWER with references/correlation, follow-up persistence after restart, cross-user isolation",
            "negative": {
                "missing_index": "index_unavailable",
                "invalid_registry": "registry_invalid",
                "missing_provider": "provider_not_configured",
            },
            "network": "no external attempts; dedicated bridge, localhost host bind, test-only Python socket/DNS/HTTP guard",
            "shutdown": "exit 0, no OOM, observed controlled runtime/index/provider/SQLite closed",
        },
        "environment_names": [
            "HOST",
            "PORT",
            "DATABASE_TYPE",
            "SQLITE_DB_PATH",
            "CHROMA_PERSIST_DIR",
            "NORMATIVE_REGISTRY_PATH",
            "PYTHONPATH",
            "PYTHONDONTWRITEBYTECODE",
            "USE_FAKE_MODEL",
            "OPENROUTER_API_KEY",
            "ANONYMIZED_TELEMETRY",
            "LANGCHAIN_TRACING_V2",
            "LANGSMITH_TRACING",
            "LANGFUSE_TRACING",
        ],
    }
    write("technical_protocol.json", protocol)
    decision(
        "provider_isolation",
        "Normal CMD for DIRECT/calculator; separate mounted test entrypoint injects only provider_factory using existing app.state seam for normative cases.",
        "No productive env switch or fake shipped. Normative uses actual 507-record index with metadata_exact; generation controlled, no quality measurement.",
    )
    decision(
        "memory",
        "Dedicated SQLite bind mounts in the recorded temporary WSL workspace.",
        "Never uses the user database; controlled container restart preserves its own mount.",
    )
    decision(
        "network",
        "Dedicated bridge and localhost-only port 18080; Python guard mounted solely for tests.",
        "Allow actual HTTP localhost while preventing/observing runtime egress; build downloads measured separately.",
    )
    run(
        "network_create",
        [
            "docker",
            "network",
            "create",
            "--label",
            "normative.smoke=container-runtime-v1",
            NETWORK,
        ],
        check=True,
    )
    run(
        "network_inspect",
        ["docker", "network", "inspect", "--format", "{{json .Internal}}", NETWORK],
        check=True,
    )
    try:
        image_result = run(
            "image_import_assets",
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--mount",
                f"type=bind,src={OUT},dst=/smoke,readonly",
                "-e",
                "USE_FAKE_MODEL=true",
                "-e",
                "PYTHONPATH=/smoke:/app/code/src",
                "-e",
                "PYTHONDONTWRITEBYTECODE=1",
                IMAGE,
                "python",
                "/smoke/image_probe.py",
            ],
        )
        verify(
            "image_import_assets",
            image_result.returncode == 0,
            json.loads(image_result.stdout.splitlines()[-1])
            if image_result.returncode == 0
            else {"log": "image_import_assets.log"},
        )
        observation = create(NATIVE)
        started = start(NATIVE, "native")
        verify("startup_native", started)
        if started:
            metadata("native")
            for name, text, expected, field, value in [
                ("direct_native", "Oi", None, None, None),
                (
                    "calculator_native",
                    "2+2",
                    "calculator_result",
                    "numeric_result",
                    "4",
                ),
                (
                    "date_native",
                    "Adicione 10 dias corridos a 05/11/2026.",
                    "calculator_result",
                    "date_result",
                    "2026-11-15",
                ),
            ]:
                response = invoke(text)
                message = body(response)
                success = (
                    response["status"] == 200
                    and typed(message, expected)
                    and (
                        field is None
                        or str((message.get(expected) or {}).get(field)) == value
                    )
                )
                verify(name, success, message)
            sse("stream_direct", "Oi", None, thread="stream-direct")
            sse(
                "stream_calculator",
                "2+2",
                "calculator_result",
                thread="stream-calculator",
            )
        stop(NATIVE, observation, "native")
        observed = create(CONTROLLED, kind="controlled")
        started = start(CONTROLLED, "controlled")
        verify("startup_controlled", started)
        first = None
        if started:
            metadata("controlled")
            response = invoke("Resolução 177/2012, art. 68")
            message = body(response)
            result = message.get("normative_result") or {}
            valid = (
                response["status"] == 200
                and typed(message, "normative_result")
                and result.get("status") == "ANSWER"
                and result.get("retrieval_strategy") == "metadata_exact"
                and bool(result.get("references"))
                and bool(result.get("correlation_id"))
                and message.get("content") == result.get("answer")
            )
            verify("normative_controlled", valid, message)
            if valid:
                first = result
                calculated = body(invoke("2+2"))
                verify(
                    "calculator_preserves_authority",
                    typed(calculated, "calculator_result"),
                    calculated,
                )
                repeated = body(invoke("Repita."))
                derived = repeated.get("grounded_followup_result") or {}
                verify(
                    "memory_same_lifespan",
                    typed(repeated, "grounded_followup_result")
                    and derived.get("content") == first["answer"]
                    and derived.get("source_correlation_id") == first["correlation_id"],
                    repeated,
                )
                foreign = body(invoke("Repita.", user="smoke-B"))
                verify(
                    "cross_user_isolation",
                    not foreign.get("grounded_followup_result")
                    and not foreign.get("normative_result"),
                    foreign,
                )
                sse(
                    "stream_normative",
                    "Resolução 177/2012, art. 68",
                    "normative_result",
                    thread="stream-normative",
                )
        stop(CONTROLLED, observed, "controlled_first")
        restarted = start(CONTROLLED, "controlled_restart")
        verify("startup_controlled_restart", restarted)
        if restarted:
            metadata("controlled_restart")
            if first:
                repeated = body(invoke("Repita."))
                derived = repeated.get("grounded_followup_result") or {}
                calls = (
                    json.loads((observed / "controlled_provider.json").read_text())
                    if (observed / "controlled_provider.json").exists()
                    else {"routes": 0, "generations": 0, "embeddings": 0}
                )
                verify(
                    "memory_restart",
                    typed(repeated, "grounded_followup_result")
                    and derived.get("content") == first["answer"]
                    and derived.get("source_correlation_id") == first["correlation_id"]
                    and derived.get("references") == first["references"]
                    and calls["routes"]
                    == calls["generations"]
                    == calls["embeddings"]
                    == 0,
                    {"message": repeated, "provider_calls": calls},
                )
        stop(CONTROLLED, observed, "controlled_restart")
        for negative, code in protocol["expected"]["negative"].items():
            name = NATIVE + "-" + negative.replace("_", "-")
            observation = create(name, negative=negative)
            started = start(name, negative)
            verify("startup_" + negative, started)
            if started:
                metadata(negative, ready=False, code=code)
                for endpoint in ("invoke", "stream"):
                    response = http(f"/{AGENT}/{endpoint}", {"message": "Oi"})
                    verify(
                        negative + "_" + endpoint,
                        response["status"] == 503
                        and not response["content_type"].startswith("text/event-stream")
                        and code in response["body"],
                        response,
                    )
                if negative == "missing_index":
                    checked = run(
                        "missing_index_not_created",
                        [
                            "docker",
                            "exec",
                            name,
                            "python",
                            "-c",
                            'from pathlib import Path; assert not Path("/missing-index-smoke").exists(); print("missing index not created")',
                        ],
                    )
                    verify("missing_index_not_created", checked.returncode == 0)
            stop(name, observation, negative)
        result = run(
            "typed_transport",
            [
                "docker",
                "run",
                "--rm",
                "-i",
                "--network",
                "none",
                "--mount",
                f"type=bind,src={OUT},dst=/smoke,readonly",
                IMAGE,
                "python",
                "/smoke/transport_probe.py",
            ],
            stdin=json.dumps(MESSAGES),
        )
        verify(
            "typed_transport",
            result.returncode == 0,
            json.loads(result.stdout)
            if result.returncode == 0
            else {"log": "typed_transport.log"},
        )
    finally:
        for name, observation in CREATED:
            if (
                run_quiet(["docker", "inspect", "--format", "{{.State.Running}}", name])
                == "true"
            ):
                stop(name, observation, "cleanup_" + name)
            run("remove_" + name, ["docker", "rm", name])
        run("network_remove", ["docker", "network", "rm", NETWORK])
    verify(
        "frozen_hashes_preserved",
        all(
            hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
            for path, digest in protocol["hashes"].items()
        ),
    )
    write("public_messages.json", MESSAGES)
    print(
        json.dumps(
            {
                "passed": sum(r["status"] == "PASS" for r in RESULTS),
                "failed": sum(r["status"] == "FAIL" for r in RESULTS),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
