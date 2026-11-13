"""Frozen local UI protocol: actual HTTP/SSE client, real runtime, controlled provider."""

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
CODE = ROOT / "code"
AGENT = "chatbot_ufpi_integrated_v1"
PRIVATE = (
    "internal_audit",
    "storage_key",
    "memory envelope",
    "raw generation",
    "embedding",
    "correlation_id",
    "contract_version",
    "core_version",
    "guard_status",
    "dense_vector",
    "metadata_exact",
)
CASES = [
    ("greeting", "Oi", "direct"),
    ("metadata_exact", "Resolução 177/2012, art. 68", "normative"),
    ("conceptual_dense", "Na graduação, como funciona o estágio?", "normative"),
    ("clarification", "Posso cancelar uma disciplina?", "clarification"),
    ("clarification_continuation", "Graduação.", "normative"),
    ("calculator", "2+2", "calculator"),
    ("calculator_date", "Adicione 10 dias corridos a 05/11/2026.", "calculator"),
    ("grounded_repeat", "Repita", "grounded"),
    ("grounded_summary", "Resuma", "grounded"),
    ("domain_switch", "E na pós?", "normative"),
    ("new_conversation", "Repita", "direct"),
    ("service_unavailable", "Oi", "unavailable"),
]


def now():
    return datetime.now(timezone.utc).isoformat()


def write(name, value):
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def event(kind, **kwargs):
    with (OUT / "execution_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(dict(timestamp=now(), event=kind, **kwargs), ensure_ascii=False)
            + "\n"
        )


def freeze():
    paths = [
        "code/src/streamlit_app.py",
        "code/src/client/client.py",
        "evaluation/results/tcc_ui_integration_v1_001/local_service.py",
        "evaluation/results/tcc_ui_integration_v1_001/local_smoke.py",
    ]
    protocol = dict(
        timestamp=now(),
        cases=CASES,
        hashes={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
        provider="controlled; existing fixed vector; no embedding quality claim",
        network="loopback HTTP/SSE; socket/DNS guard in backend; not universal packet capture",
    )
    path = OUT / "ui_protocol.json"
    if path.exists():
        assert (
            json.loads(path.read_text(encoding="utf-8"))["hashes"] == protocol["hashes"]
        ), "Frozen protocol changed"
    else:
        write("ui_protocol.json", protocol)
    event("protocol_frozen", cases=len(CASES), hashes=protocol["hashes"])


def wait_url(url, process):
    import httpx

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Local process exited before health")
        try:
            response = httpx.get(url, timeout=1)
            if response.status_code == 200:
                return response
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise TimeoutError("Local startup timeout")


def main():
    import httpx
    from streamlit.testing.v1 import AppTest
    from client.client import AgentClient
    from schema import ChatMessage

    freeze()
    workspace = Path(tempfile.mkdtemp(prefix="tcc-ui-smoke-"))
    write(
        "temporary_workspace.json",
        dict(
            path=str(workspace),
            purpose="isolated SQLite/vector seed; no real credentials",
            created_at=now(),
        ),
    )
    env = dict(os.environ)
    for key in (
        "AUTH_SECRET",
        "OPENROUTER_API_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGCHAIN_API_KEY",
        "LANGSMITH_API_KEY",
    ):
        env.pop(key, None)
    env.update(
        USE_FAKE_MODEL="true",
        OPENAI_API_KEY="sk-controlled-placeholder",
        OPENROUTER_API_KEY="controlled-placeholder",
        DATABASE_TYPE="sqlite",
        SQLITE_DB_PATH=str(workspace / "checkpoints.db"),
        CHROMA_PERSIST_DIR=str(CODE / ".local/chroma"),
        ANONYMIZED_TELEMETRY="False",
        LANGFUSE_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        LANGSMITH_TRACING="false",
        HOST="127.0.0.1",
        PORT="18081",
        TCC_SMOKE_OUT=str(OUT),
        TCC_SMOKE_STATE=str(workspace),
        PYTHONDONTWRITEBYTECODE="1",
        NO_PROXY="localhost,127.0.0.1",
    )
    snapshot = subprocess.run(
        [
            sys.executable,
            str(OUT / "index_snapshot.py"),
            "before",
            str(workspace / "sample_vector.json"),
        ],
        env=env,
        cwd=workspace,
        capture_output=True,
    )
    (OUT / "index_before.log").write_bytes(snapshot.stdout + snapshot.stderr)
    assert snapshot.returncode == 0
    processes = []
    logs = []
    calls = []
    rows = []
    exitcodes = []
    original = AgentClient.astream

    async def observed(client, **kwargs):
        row = dict(
            timestamp=now(), agent=client.agent, base_url=client.base_url, **kwargs
        )
        calls.append(row)
        async for message in original(client, **kwargs):
            yield message

    AgentClient.astream = observed
    old_cwd = Path.cwd()
    old_env = dict(os.environ)
    try:
        os.chdir(workspace)
        os.environ.update(env)
        os.environ.pop("AUTH_SECRET", None)

        def launch(command, process_env, log):
            handle = (OUT / log).open("wb")
            logs.append(handle)
            proc = subprocess.Popen(
                command,
                cwd=workspace,
                env=process_env,
                stdout=handle,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW,
            )
            processes.append(proc)
            return proc

        backend = launch(
            [sys.executable, str(OUT / "local_service.py")], env, "local_service.log"
        )
        wait_url("http://127.0.0.1:18081/health", backend)
        info = httpx.get("http://127.0.0.1:18081/info").json()
        ready = httpx.get(f"http://127.0.0.1:18081/agents/{AGENT}/readiness").json()
        write("service_info.json", info)
        write("service_readiness.json", ready)
        assert info["default_agent"] == "chatbot_ufpi_v2" and ready["ready"]
        os.environ["AGENT_URL"] = "http://127.0.0.1:18081"
        ui_env = dict(env, AGENT_URL=os.environ["AGENT_URL"])
        ui = launch(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(CODE / "src/streamlit_app.py"),
                "--server.address=127.0.0.1",
                "--server.port=18501",
                "--server.headless=true",
                "--browser.gatherUsageStats=false",
            ],
            ui_env,
            "local_streamlit.log",
        )
        response = wait_url("http://127.0.0.1:18501/_stcore/health", ui)
        write(
            "streamlit_http.json",
            dict(
                status=response.status_code,
                body=response.text,
                address="127.0.0.1:18501",
                browser_session_driven_by="AppTest with actual AgentClient HTTP/SSE",
            ),
        )
        at = AppTest.from_file(str(CODE / "src/streamlit_app.py")).run(timeout=30)
        assert not at.exception
        user, thread = at.session_state.user_id, at.session_state.thread_id
        authority = None
        for name, prompt, kind in CASES:
            row = dict(timestamp=now(), case=name, prompt=prompt, expected=kind)
            if name == "new_conversation":
                at.sidebar.button[0].click().run(timeout=30)
                assert (
                    at.session_state.user_id == user
                    and at.session_state.thread_id != thread
                    and at.session_state.messages == []
                )
            if name == "service_unavailable":
                negative_env = dict(
                    env,
                    PORT="18082",
                    SQLITE_DB_PATH=str(workspace / "negative.db"),
                    TCC_SMOKE_NO_PROVIDER="1",
                )
                negative_env.pop("OPENROUTER_API_KEY", None)
                negative = launch(
                    [sys.executable, str(OUT / "local_service.py")],
                    negative_env,
                    "local_unavailable.log",
                )
                wait_url("http://127.0.0.1:18082/health", negative)
                write(
                    "unavailable_readiness.json",
                    httpx.get(
                        f"http://127.0.0.1:18082/agents/{AGENT}/readiness"
                    ).json(),
                )
                os.environ["AGENT_URL"] = "http://127.0.0.1:18082"
                at = AppTest.from_file(str(CODE / "src/streamlit_app.py")).run(
                    timeout=30
                )
            before = len(at.session_state.messages)
            at.chat_input[0].set_value(prompt).run(timeout=30)
            assert not at.exception
            visible = "\n".join(
                str(x.value)
                for category in (at.markdown, at.caption, at.error, at.warning, at.text)
                for x in category
            )
            assert not any(key in visible for key in PRIVATE)
            assert "[DONE]" not in visible and not at.selectbox and not at.radio
            row.update(
                request=calls[-1], visible=visible, private_leaks=0, legacy_fallback=0
            )
            assert calls[-1]["agent"] == AGENT
            if kind == "unavailable":
                assert len(at.session_state.messages) == before + 1
                assert "temporariamente indisponível" in visible
            else:
                assert len(at.session_state.messages) == before + 2
                message = at.session_state.messages[-1]
                assert isinstance(message, ChatMessage)
                row["message"] = message.model_dump(mode="json")
                result = message.normative_result or message.grounded_followup_result
                refs = result.references if result else []
                expected_refs = {tuple(r.model_dump().items()) for r in refs}
                last = at.chat_message[-1]
                shown = [
                    x.value for expander in last.expander for x in expander.markdown
                ]
                assert len(shown) == len(expected_refs)
                for ref in refs:
                    assert ref.display_text in "\n".join(shown)
                row.update(
                    expected_references=len(expected_refs), shown_references=len(shown)
                )
                if kind == "normative":
                    assert (
                        message.normative_result
                        and message.normative_result.status == "ANSWER"
                    )
                    if name == "metadata_exact":
                        assert (
                            message.normative_result.retrieval_strategy
                            == "metadata_exact"
                        )
                    if name == "conceptual_dense":
                        assert (
                            message.normative_result.retrieval_strategy
                            == "dense_vector"
                        )
                    if name == "clarification_continuation":
                        authority = message.normative_result
                    if name == "domain_switch":
                        assert message.normative_result.domain == "pos_graduacao"
                elif kind == "clarification":
                    assert (
                        message.normative_result.status == "CLARIFICATION"
                        and not last.expander
                    )
                elif kind == "calculator":
                    assert message.calculator_result and not last.expander
                    assert message.content == (
                        "4" if name == "calculator" else "15/11/2026"
                    )
                elif kind == "grounded":
                    assert message.grounded_followup_result
                    assert (
                        message.grounded_followup_result.references
                        == authority.references
                    )
                    assert (
                        message.grounded_followup_result.source_correlation_id
                        == authority.correlation_id
                    )
                else:
                    assert (
                        message.normative_result is None
                        and message.calculator_result is None
                        and message.grounded_followup_result is None
                    )
                retained = message.model_dump(mode="json")
                at.run(timeout=30)
                assert at.session_state.messages[-1].model_dump(mode="json") == retained
                if name not in {"new_conversation", "service_unavailable"}:
                    assert (
                        at.session_state.thread_id == thread
                        and at.session_state.user_id == user
                    )
            row["passed"] = True
            rows.append(row)
            with (OUT / "ui_probe_rows.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            event("ui_probe", case=name, passed=True)
        write("ui_requests.json", calls)
        write(
            "ui_smoke_summary.json",
            dict(
                timestamp=now(),
                passed=len(rows),
                total=len(CASES),
                requests=len(calls),
                typed_messages=sum("message" in r for r in rows),
                expected_references=sum(r.get("expected_references", 0) for r in rows),
                shown_references=sum(r.get("shown_references", 0) for r in rows),
            ),
        )
    except Exception as error:
        event("ui_smoke_failure", error_type=type(error).__name__, message=str(error))
        write("ui_requests.json", calls)
        raise
    finally:
        AgentClient.astream = original
        os.chdir(old_cwd)
        os.environ.clear()
        os.environ.update(old_env)
        for proc in reversed(processes):
            try:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
                proc.wait(timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                proc.terminate()
                proc.wait(timeout=15)
            exitcodes.append(dict(pid=proc.pid, exit_code=proc.returncode))
        for handle in logs:
            handle.close()
        write("local_process_shutdown.json", exitcodes)
        after = subprocess.run(
            [sys.executable, str(OUT / "index_snapshot.py"), "after"],
            env=env,
            cwd=workspace,
            capture_output=True,
        )
        (OUT / "index_after.log").write_bytes(after.stdout + after.stderr)
        if after.returncode == 0:
            assert json.loads(
                (OUT / "index_before.json").read_text(encoding="utf-8")
            ) == json.loads((OUT / "index_after.json").read_text(encoding="utf-8"))
            event("index_preservation", count=507, identical=True)
        assert workspace.resolve().parent == Path(
            tempfile.gettempdir()
        ).resolve() and workspace.name.startswith("tcc-ui-smoke-")
        shutil.rmtree(workspace)
        event("temporary_workspace_removed", path=str(workspace))
    print(json.dumps(dict(passed=len(rows), total=len(CASES))))


if __name__ == "__main__":
    main()
