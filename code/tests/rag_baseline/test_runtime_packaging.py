"""Declared container layout and portable runtime assets, without Docker/network."""

import json
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ASSETS = [
    "data/normative_registry.json",
    "evaluation/corpora/graduacao_setor_v2.json",
    "evaluation/corpora/pos_graduacao_setor_v2.json",
    "evaluation/corpora/1056_2026_temporal_v1.json",
]
PACKAGES = ["agents", "core", "memory", "schema", "service", "rag_baseline"]


@pytest.mark.parametrize("package", PACKAGES)
def test_service_dockerfile_copies_each_required_package(package):
    dockerfile = (ROOT / "code/docker/Dockerfile.service").read_text(encoding="utf-8")
    assert f"COPY code/src/{package}/ ./src/{package}/" in dockerfile


@pytest.mark.parametrize("asset", ASSETS)
def test_service_dockerfile_copies_exact_registry_dependencies(asset):
    dockerfile = (ROOT / "code/docker/Dockerfile.service").read_text(encoding="utf-8")
    assert f"COPY {asset} /app/{asset}" in dockerfile
    assert (ROOT / asset).is_file()
    assert "evaluation/results" not in dockerfile and "evaluation/datasets" not in dockerfile


def test_compose_uses_root_context_and_persistent_index_mount():
    for filename in ["compose.yaml", "compose.prod.yaml"]:
        text = (ROOT / "code" / filename).read_text(encoding="utf-8")
        assert "dockerfile: code/docker/Dockerfile.service" in text
        assert "CHROMA_PERSIST_DIR: /app/index" in text
        assert "./.local/chroma:/app/index" in text


def test_packaging_does_not_change_python_default_or_langgraph_entrypoint():
    dockerfile = (ROOT / "code/docker/Dockerfile.service").read_text(encoding="utf-8")
    assert "python:3.12.3-slim" in dockerfile
    assert "D:\\" not in dockerfile and "C:\\" not in dockerfile
    config = json.loads((ROOT / "code/langgraph.json").read_text(encoding="utf-8"))
    assert config["python_version"] == "3.12"
    assert config["graphs"] == {
        "research_assistant": "./src/agents/research_assistant.py:research_assistant"
    }


def test_simulated_container_layout_imports_registry_and_validates_all_assets(tmp_path):
    layout = tmp_path / "app"
    for package in PACKAGES:
        shutil.copytree(
            ROOT / "code/src" / package,
            layout / "code/src" / package,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    for asset in ASSETS:
        target = layout / asset
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / asset, target)
    env = dict(
        os.environ,
        PYTHONPATH=str(layout / "code/src") + os.pathsep + sysconfig.get_path("purelib"),
        PYTHONIOENCODING="utf-8",
    )
    script = """
from pathlib import Path
from rag_baseline.versioning import NormativeRegistry, REGISTRY_PATH
from agents.agents import agents, DEFAULT_AGENT
from service import app
assert REGISTRY_PATH.is_file()
assert len(NormativeRegistry.load().norms) == 4
assert "chatbot_ufpi_integrated_v1" in agents
assert DEFAULT_AGENT == "chatbot_ufpi_v2"
assert any(r.path == "/agents/{agent_id}/readiness" for r in app.routes)
print("portable import and assets passed")
"""
    run = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert run.returncode == 0, run.stdout.decode(errors="replace")
    assert b"portable import and assets passed" in run.stdout


def test_client_image_includes_shared_contracts_without_modifying_ui():
    text = (ROOT / "code/docker/Dockerfile.app").read_text(encoding="utf-8")
    assert "COPY src/rag_baseline/ ./src/rag_baseline/" in text
    assert 'PYTHONPATH="/app/code/src"' in text
