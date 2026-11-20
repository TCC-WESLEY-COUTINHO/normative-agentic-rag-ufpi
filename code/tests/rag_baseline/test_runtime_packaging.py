"""Portable runtime imports and assets, without Docker/network."""

import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ASSETS = [
    "data/normative_registry.json",
    "evaluation/corpora/graduacao_setor_v2.json",
    "evaluation/corpora/pos_graduacao_setor_v2.json",
    "evaluation/corpora/1056_2026_temporal_v1.json",
]
PACKAGES = ["agents", "core", "memory", "schema", "service", "rag_baseline"]


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
