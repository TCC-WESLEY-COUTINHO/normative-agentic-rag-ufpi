# ruff: noqa: E402 -- import ordering is intentional for resource/network guards.
"""Inspect the actual Linux image; no host source overlay and no index mount."""

import hashlib
import importlib
import json
import sys
from pathlib import Path

import chromadb
from rag_baseline.openrouter import OpenRouterClient


def forbidden(*args, **kwargs):
    raise AssertionError("Resource construction during import")


chromadb.PersistentClient = forbidden
OpenRouterClient.__init__ = forbidden
for name in ("rag_baseline", "service", "agents.agents", "schema"):
    importlib.import_module(name)
assert "agents.tools" not in sys.modules
assert "agents.langgraph_supervisor_agent" not in sys.modules
from rag_baseline.versioning import NormativeRegistry

registry = NormativeRegistry.load()
assets = [
    "/app/code/src/" + p
    for p in ("agents", "core", "memory", "schema", "service", "rag_baseline")
]
assets += [
    "/app/code/src/run_service.py",
    "/app/data/normative_registry.json",
    "/app/evaluation/corpora/graduacao_setor_v2.json",
    "/app/evaluation/corpora/pos_graduacao_setor_v2.json",
    "/app/evaluation/corpora/1056_2026_temporal_v1.json",
]
assert all(Path(p).exists() for p in assets)
forbidden_paths = [
    "/app/.git",
    "/app/code/.git",
    "/app/code/.env",
    "/app/.env",
    "/app/evaluation/results",
    "/app/evaluation/datasets",
    "/app/index",
    "/app/code/.local/chroma",
]
assert not any(Path(p).exists() for p in forbidden_paths)
secret_files = [
    str(p)
    for p in Path("/app").rglob("*")
    if p.is_file()
    and (
        p.name == ".env"
        or p.suffix in (".log", ".pem")
        or p.name in ("id_rsa", "id_ed25519")
    )
]
assert not secret_files
from agents.agents import DEFAULT_AGENT, agents

assert (
    DEFAULT_AGENT == "chatbot_ufpi_v2"
    and agents["chatbot_ufpi_integrated_v1"].experimental
)
print(
    json.dumps(
        {
            "python": sys.version,
            "cwd": str(Path.cwd()),
            "imports": ["rag_baseline", "service", "agents.agents", "schema"],
            "import_resource_construction": 0,
            "asset_completeness": [len(assets), len(assets)],
            "assets": assets,
            "forbidden_paths_present": [],
            "secret_bearing_files_found": secret_files,
            "registry_valid": True,
            "default_agent": DEFAULT_AGENT,
            "integrated_experimental": True,
            "client_expected_in_service_image": False,
        }
    )
)

expected = json.loads(Path("/smoke/preservation_before.json").read_text())["files"]
source_matches = 0
package_names = ("agents", "core", "memory", "schema", "service", "rag_baseline")
for relative, digest in expected.items():
    if (
        any(
            relative.startswith("code/src/" + package + "/")
            for package in package_names
        )
        or relative == "code/src/run_service.py"
        or str(Path("/app") / relative) in assets
    ):
        actual = Path("/app") / relative
        assert (
            actual.is_file()
            and hashlib.sha256(actual.read_bytes()).hexdigest() == digest
        ), relative
        source_matches += 1
assert source_matches > 11
print(json.dumps({"packaged_source_files_identical_to_build_baseline": source_matches}))
