"""Portable input locations for the paired experimental runner."""

import runpy
from pathlib import Path


def test_adaptive_rag_input_locations_can_be_configured(monkeypatch, tmp_path):
    env_file = tmp_path / "credentials.env"
    index_dir = tmp_path / "index"
    monkeypatch.setenv("ADAPTIVE_RAG_ENV_FILE", str(env_file))
    monkeypatch.setenv("ADAPTIVE_RAG_INDEX_DIR", str(index_dir))

    runner = runpy.run_module("evaluation.adaptive_rag.run")

    assert runner["CREDENTIALS_ENV"] == env_file
    assert runner["INDEX_COPY"] == index_dir


def test_adaptive_rag_default_input_locations_are_repository_relative(monkeypatch):
    monkeypatch.delenv("ADAPTIVE_RAG_ENV_FILE", raising=False)
    monkeypatch.delenv("ADAPTIVE_RAG_INDEX_DIR", raising=False)

    runner = runpy.run_module("evaluation.adaptive_rag.run")
    root = Path(__file__).resolve().parents[3]

    assert runner["CREDENTIALS_ENV"] == root / "code/.env"
    assert runner["INDEX_COPY"] == root / ".local/adaptive-rag-env/chroma_copy"
