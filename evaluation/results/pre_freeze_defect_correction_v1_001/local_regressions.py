"""Four pre-freeze regressions on current 507-record corpus, real HTTP/UI, controlled provider."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from streamlit.testing.v1 import AppTest

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
CODE = ROOT / "code"
CASES = [
    ("explicit_post_clean", "como entrar na pós?", "pos_graduacao"),
    ("explicit_grad", "qual a média para passar na graduação?", "graduacao"),
    ("explicit_post_after_grad", "como entrar na pós?", "pos_graduacao"),
    (
        "multiple_references",
        "como funciona o ingresso na pós-graduação?",
        "pos_graduacao",
    ),
]


def main():
    workspace = Path(tempfile.mkdtemp(prefix="pre-freeze-local-"))
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join(
            [str(CODE / "src"), str(CODE / ".venv/Lib/site-packages")]
        ),
        TCC_SMOKE_OUT=str(OUT),
        TCC_SMOKE_STATE=str(workspace),
        PORT="18081",
        HOST="127.0.0.1",
        DATABASE_TYPE="sqlite",
        SQLITE_DB_PATH=str(workspace / "checkpoints.db"),
        OPENROUTER_API_KEY="controlled-placeholder",
        ANONYMIZED_TELEMETRY="False",
        LANGFUSE_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        LANGSMITH_TRACING="false",
        CHROMA_PERSIST_DIR=str(CODE / ".local/chroma"),
        PYTHONDONTWRITEBYTECODE="1",
        AGENT_URL="http://127.0.0.1:18081",
    )
    env.pop("AUTH_SECRET", None)
    snapshot = subprocess.run(
        [
            sys.executable,
            str(OUT / "index_snapshot.py"),
            "before",
            str(workspace / "sample_vector.json"),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert snapshot.returncode == 0
    before = json.loads((OUT / "index_before.json").read_text(encoding="utf-8"))
    hashes = {r["id"]: r["document_sha256"] for r in before["records"]}
    logfile = (OUT / "local_controlled_service.log").open("wb")
    process = subprocess.Popen(
        [sys.executable, str(OUT / "local_service.py")],
        cwd=workspace,
        env=env,
        stdout=logfile,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    old_cwd = Path.cwd()
    old_env = dict(os.environ)
    rows = []
    try:
        deadline = time.monotonic() + 60
        while True:
            if process.poll() is not None:
                raise RuntimeError("Controlled service startup failed")
            try:
                ready = httpx.get(
                    env["AGENT_URL"] + "/agents/chatbot_ufpi_integrated_v1/readiness",
                    timeout=1,
                )
                if ready.status_code == 200 and ready.json()["ready"]:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                raise TimeoutError("Controlled readiness timeout")
            time.sleep(0.2)
        os.chdir(workspace)
        os.environ.update(env)
        os.environ.pop("AUTH_SECRET", None)
        app = AppTest.from_file(str(CODE / "src/streamlit_app.py")).run(timeout=30)
        for name, question, domain in CASES:
            app.chat_input[0].set_value(question).run(timeout=30)
            assert not app.exception and not app.error
            message = app.session_state.messages[-1]
            result = message.normative_result
            assert result and result.status == "ANSWER" and result.domain == domain
            assert app.session_state.agent_client.agent == "chatbot_ufpi_integrated_v1"
            last = app.chat_message[-1]
            assert (
                len(last.expander) == 1
                and last.expander[0].label == "Trechos normativos recuperados"
            )
            assert (
                "Fontes:" not in message.content
                and "Referências:" not in message.content
                and "Sources:" not in message.content
            )
            refs = {tuple(r.model_dump().items()): r for r in result.references}
            assert len(last.expander[0].text) == len(refs)
            for reference, shown in zip(
                refs.values(), last.expander[0].text, strict=True
            ):
                assert reference.evidence_text is not None
                assert shown.value == reference.evidence_text.strip()
                assert (
                    hashlib.sha256(reference.evidence_text.encode()).hexdigest()
                    == hashes[reference.chunk_id]
                )
            if domain == "pos_graduacao":
                assert {
                    e.source_norm for e in result.temporal_provenance.evidence_states
                } == {"ufpi-956-2025"}
            row = dict(
                case=name,
                kind="pre-freeze regression case; not independent scientific test",
                question=question,
                agent_id=app.session_state.agent_client.agent,
                status=result.status.value,
                domain=result.domain,
                strategy=result.retrieval_strategy.value,
                norm_ids=sorted(
                    {e.source_norm for e in result.temporal_provenance.evidence_states}
                ),
                eligible_ids=[
                    e.chunk_id for e in result.temporal_provenance.evidence_states
                ],
                typed_references=len(refs),
                details_rendered=len(last.expander[0].text),
                duplicate_sections=0,
                content_to_reference_parsing=0,
                legacy_fallback=0,
                message=message.model_dump(mode="json"),
                passed=True,
            )
            rows.append(row)
            (OUT / "local_regression_rows.json").write_text(
                json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        print(
            json.dumps(
                {
                    "passed": len(rows),
                    "total": len(CASES),
                    "references": sum(r["typed_references"] for r in rows),
                    "details": sum(r["details_rendered"] for r in rows),
                    "duplicate_sections": 0,
                }
            )
        )
    finally:
        os.chdir(old_cwd)
        os.environ.clear()
        os.environ.update(old_env)
        (workspace / "stop-18081").touch()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=15)
        logfile.close()
        assert workspace.resolve().parent == Path(
            tempfile.gettempdir()
        ).resolve() and workspace.name.startswith("pre-freeze-local-")
        shutil.rmtree(workspace)
        (OUT / "local_shutdown.json").write_text(
            json.dumps(
                {"exit_code": process.returncode, "temporary_workspace_removed": True}
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
