"""Real Uvicorn service with existing test injection seam and lifecycle observers only."""

import json
import runpy
from contextlib import asynccontextmanager
from pathlib import Path

import service.service as service
from agents.agents import agents
from chromadb.api.shared_system_client import SharedSystemClient

OBS = Path("/observations")
AGENT = "chatbot_ufpi_integrated_v1"


class ControlledProvider:
    llm_model = "qwen/qwen3-30b-a3b-instruct-2507"

    def __init__(self):
        self.routes = self.generations = self.embeddings = 0
        self.closed = False

    async def structured_chat(self, **kwargs):
        question = json.loads(kwargs["user_prompt"])["question"]
        if question != "Resolução 177/2012, art. 68":
            raise AssertionError(
                "Unexpected normative input in frozen operational smoke"
            )
        self.routes += 1
        self.save()
        return json.dumps(
            {
                "scope": "graduacao",
                "needs_clarification": False,
                "clarification_question": None,
                "reason_code": "explicit_graduacao",
            }
        )

    async def chat(self, **kwargs):
        self.generations += 1
        self.save()
        return "Conteúdo controlado."

    async def embed(self, texts):
        self.embeddings += 1
        self.save()
        raise AssertionError("Frozen metadata_exact case must not require embedding")

    async def aclose(self):
        self.closed = True
        self.save()

    def save(self):
        (OBS / "controlled_provider.json").write_text(
            json.dumps(
                {
                    "routes": self.routes,
                    "generations": self.generations,
                    "embeddings": self.embeddings,
                    "closed": self.closed,
                }
            )
            + "\n"
        )


provider = ControlledProvider()
provider.save()
service.app.state.agent_runtime_options = {
    AGENT: {"provider_factory": lambda _: provider}
}
original = service.app.router.lifespan_context


@asynccontextmanager
async def observed(app):
    runtime = None
    saver = None
    async with original(app):
        runtime = agents[AGENT].runtime
        if runtime:
            saver = runtime.graph.checkpointer
            (OBS / "startup_resources.json").write_text(
                json.dumps(
                    {
                        "runtime_assembled": True,
                        "index_owned": runtime.index.owned,
                        "checks": runtime.readiness(),
                        "corpus_fingerprint": runtime.memory_stamp.corpus_fingerprint,
                        "registry_fingerprint": runtime.memory_stamp.registry_fingerprint,
                        "provider_calls": provider.routes
                        + provider.generations
                        + provider.embeddings,
                    }
                )
                + "\n"
            )
        yield
    if runtime:
        (OBS / "closed_resources.json").write_text(
            json.dumps(
                {
                    "runtime_closed": runtime.closed,
                    "index_closed": runtime.index.closed,
                    "index_cache_removed": runtime.index.key
                    not in SharedSystemClient._identifier_to_system,
                    "provider_closed": provider.closed,
                    "sqlite_connection_closed": getattr(
                        saver.conn, "_connection", "not_available"
                    )
                    is None,
                }
            )
            + "\n"
        )


service.app.router.lifespan_context = observed
runpy.run_path("/app/code/src/run_service.py", run_name="__main__")
