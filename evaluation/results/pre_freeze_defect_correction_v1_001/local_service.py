"""Test-only local Uvicorn entrypoint using the existing runtime provider seam."""

import json
import os
import socket
from pathlib import Path

OUT = Path(os.environ["TCC_SMOKE_OUT"])
STATE = Path(os.environ["TCC_SMOKE_STATE"])
ATTEMPTS = []
connect = socket.socket.connect
getaddrinfo = socket.getaddrinfo


def denied(host):
    ATTEMPTS.append(str(host))
    (OUT / ("external_attempts_" + os.environ["PORT"] + ".json")).write_text(
        json.dumps(ATTEMPTS), encoding="utf-8"
    )
    raise AssertionError("External network disabled in local UI smoke")


def local_connect(self, address):
    if isinstance(address, tuple) and str(address[0]) not in {
        "127.0.0.1",
        "::1",
        "localhost",
    }:
        denied(address[0])
    return connect(self, address)


def local_lookup(host, *args, **kwargs):
    if host and str(host) not in {"127.0.0.1", "::1", "localhost", "0.0.0.0"}:
        denied(host)
    return getaddrinfo(host, *args, **kwargs)


socket.socket.connect = local_connect
socket.getaddrinfo = local_lookup
(OUT / ("external_attempts_" + os.environ["PORT"] + ".json")).write_text(
    "[]", encoding="utf-8"
)
import dotenv  # noqa: E402

# Isolate discovery of real checkout credentials in this test-only process.
dotenv.find_dotenv = lambda *args, **kwargs: ""
import service.service as service  # noqa: E402 -- install network guard before runtime import

AGENT = "chatbot_ufpi_integrated_v1"


class ControlledProvider:
    llm_model = "qwen/qwen3-30b-a3b-instruct-2507"

    def __init__(self):
        self.counts = dict(routes=0, embeddings=0, generations=0, closed=False)
        self.routing = []
        self.vector = json.loads((STATE / "sample_vector.json").read_text())
        self.save()

    def save(self):
        (OUT / "provider_observations.json").write_text(
            json.dumps({**self.counts, "routing": self.routing}), encoding="utf-8"
        )

    async def structured_chat(self, **kwargs):
        payload = json.loads(kwargs["user_prompt"])
        self.routing.append(payload)
        self.counts["routes"] += 1
        self.save()
        question = payload["question"].lower()
        clarification = payload.get("clarification", "").lower()
        ambiguous = question == "posso cancelar uma disciplina?" and not clarification
        scope = (
            None
            if ambiguous
            else (
                "pos_graduacao"
                if "pós" in question or "pós" in clarification
                else "graduacao"
            )
        )
        return json.dumps(
            dict(
                scope=scope,
                needs_clarification=ambiguous,
                clarification_question="Graduação ou pós-graduação?"
                if ambiguous
                else None,
                reason_code="ambiguous_academic_level"
                if ambiguous
                else (
                    "explicit_pos" if scope == "pos_graduacao" else "explicit_graduacao"
                ),
            )
        )

    async def embed(self, texts):
        self.counts["embeddings"] += 1
        self.save()
        # Fixed existing vector exercises real dense retrieval, not embedding quality.
        return [self.vector for _ in texts]

    async def chat(self, **kwargs):
        self.counts["generations"] += 1
        self.save()
        return "Conteúdo controlado."

    async def aclose(self):
        self.counts["closed"] = True
        self.save()


from rag_baseline.integrated_runtime import IntegratedRuntimeSettings  # noqa: E402
from rag_baseline.profiles import apply_profile  # noqa: E402

controlled_settings = apply_profile(
    IntegratedRuntimeSettings(_env_file=None), "duas-regulacoes"
)
options = {"settings": controlled_settings}
if os.environ.get("TCC_SMOKE_NO_PROVIDER") != "1":
    provider = ControlledProvider()
    options["provider_factory"] = lambda _: provider
service.app.state.agent_runtime_options = {AGENT: options}

if __name__ == "__main__":
    import threading
    import time
    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config(
            service.app,
            host="127.0.0.1",
            port=int(os.environ["PORT"]),
            log_level="info",
        )
    )

    def stop_when_requested():
        while not (STATE / ("stop-" + os.environ["PORT"])).exists():
            time.sleep(0.1)
        server.should_exit = True

    threading.Thread(target=stop_when_requested, daemon=True).start()
    server.run()
