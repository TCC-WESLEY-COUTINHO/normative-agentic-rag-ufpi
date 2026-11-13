"""Preserve response bytes and single amendment application across the real boundaries."""

import io
import json
import re
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from rich.console import Console

from rag_baseline.api import create_app
from rag_baseline.demo import _run_query
from rag_baseline.models import RetrievedChunk
from rag_baseline.openrouter import OpenRouterClient
from rag_baseline.service import RagService
from rag_baseline.versioning import NormativeRegistry, VersionFilter

ROOT = Path(__file__).resolve().parents[3]


def original_case():
    path = ROOT / "evaluation/results/temporal_grad_D_001/rows.jsonl"
    return json.loads(path.read_text(encoding="utf-8").splitlines()[0])


def test_real_amendment_context_contains_one_application_per_target():
    original = original_case()
    candidates = [RetrievedChunk(**c) for c in original["pre_filter_references"]]
    kept, audit = VersionFilter(NormativeRegistry.load()).apply(candidates)
    assert len({c.id for c in kept}) == len(kept)
    assert len(audit.amended_references) == 1
    applied = audit.amended_references[0]
    assert applied.norm_id == "ufpi-177-2012"
    assert applied.final_reference.content.count(applied.amendment.effective_text) == 1
    assert applied.final_reference.content.count("[REDAÇÃO APLICÁVEL:") == 1
    assert applied.original_reference.content.count(applied.amendment.previous_text) == 1
    assert [c.model_dump() for c in candidates] == original["pre_filter_references"]
    for chunk in kept:
        if chunk.id != applied.final_reference.id:
            assert chunk.content == next(c.content for c in candidates if c.id == chunk.id)


@pytest.mark.asyncio
async def test_observed_model_repetition_is_not_added_by_service_api_or_terminal():
    original = original_case()
    captured = ROOT / "evaluation/results/failure_analysis_v1/f4_original/rows.jsonl"
    first = json.loads(captured.read_text(encoding="utf-8").splitlines()[0])
    raw = first["calls"][0]["raw_content"]
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": raw}}]})

    remote = OpenRouterClient(
        api_key="test",
        embedding_model="test",
        llm_model="test",
        transport=httpx.MockTransport(respond),
    )
    service = RagService(
        openrouter=remote, vector_store=None, top_k=5, embedding_model="test", llm_model="test"
    )
    chunks = [RetrievedChunk(**c) for c in original["final_references"]]
    result = await service.generate(original["question"], chunks)
    assert result.answer == raw
    assert len(requests) == 1
    assert requests[0]["messages"][1]["content"].count("--- TRECHO ") == len(chunks)

    class ObservedResult:
        async def query(self, question, **kwargs):
            return result

    rendered, saved = io.StringIO(), io.StringIO()
    with TestClient(create_app(service=ObservedResult())) as client:
        response = client.post("/query", json={"question": original["question"]})
        assert response.status_code == 200
        assert response.json()["answer"] == raw
        assert _run_query(
            Console(file=rendered, width=120, color_system=None),
            client,
            original["question"],
            verbose=False,
            sector="graduacao",
            output=saved,
        )
    assert json.loads(saved.getvalue())["answer"] == raw
    phrase = "independentemente de seu vínculo com a ufpi"
    raw_count = " ".join(re.findall(r"\w+", raw.casefold())).count(phrase)
    assert raw_count == 2
    assert " ".join(re.findall(r"\w+", rendered.getvalue().casefold())).count(phrase) == raw_count
