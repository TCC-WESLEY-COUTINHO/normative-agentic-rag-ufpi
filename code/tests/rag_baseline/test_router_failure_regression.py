"""Behavior checks on real, explicitly selected Router reproduction runs.

Set ROUTER_REGRESSION_RUN to a directory produced by evaluation/failure_analysis.py.
These checks do not call a provider in the default unit suite.
"""

import hashlib
import json
import os
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator

from rag_baseline.openrouter import OpenRouterClient
from rag_baseline.router import NormativeRouter, RouterDecision

EXPECTED = {
    "TEMP-POS-003": "pos_graduacao",
    "TEMP-POS-004": "pos_graduacao",
    "TEMP-GRAD-005": "graduacao",
    "TEMP-GRAD-001": "graduacao",
    "CONTROL-POS": "pos_graduacao",
    "CONTROL-956": "pos_graduacao",
    "CONTROL-GRAD": "graduacao",
    "CONTROL-RGG": "graduacao",
    "CONTROL-AMBIGUOUS": None,
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question,clarification",
    [
        ("Posso cancelar uma disciplina?", None),
        ("Posso cancelar uma disciplina?", "Não sei se meu curso é graduação ou pós-graduação."),
        ("Na graduação eu podia trancar; no meu curso atual também posso?", None),
    ],
)
async def test_unresolved_level_can_remain_unresolved(question, clarification):
    decision = dict(
        scope=None,
        needs_clarification=True,
        clarification_question="Qual nível?",
        reason_code="ambiguous_academic_level",
    )
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(decision)}}]}
        )

    client = OpenRouterClient(
        api_key="test",
        embedding_model="test",
        llm_model="test",
        transport=httpx.MockTransport(respond),
    )
    result = await NormativeRouter(client).route(question, clarification=clarification)
    schema = requests[0]["response_format"]["json_schema"]["schema"]
    assert Draft202012Validator(schema).is_valid(decision)
    assert result.reason_code == "ambiguous_academic_level"
    assert result.needs_clarification


@pytest.mark.parametrize("case_id,expected", EXPECTED.items())
def test_real_router_respects_explicit_level_and_preserves_ambiguity(case_id, expected):
    selected = os.environ.get("ROUTER_REGRESSION_RUN")
    if not selected:
        pytest.skip("Select a real reproduction run with ROUTER_REGRESSION_RUN")
    run = Path(selected)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    raw_rows = (run / "rows.jsonl").read_bytes()
    assert manifest["status"] == "completed"
    assert hashlib.sha256(raw_rows).hexdigest() == manifest["artifact_sha256"]["rows.jsonl"]
    rows = [json.loads(line) for line in raw_rows.decode("utf-8").splitlines()]
    subset = [r for r in rows if r["case_id"] == case_id]
    assert len(subset) >= (10 if case_id.startswith("TEMP-") else 1)
    for row in subset:
        call = row["calls"][0]
        assert call["request"]["temperature"] == 0
        assert row["validation_error"] is None
        parsed = RouterDecision.model_validate_json(call["raw_content"])
        assert parsed.scope == expected, f"{case_id}, repetition {row['run']}: {parsed}"
        assert row["router_output"]["scope"] == expected
        assert row["router_output"]["needs_clarification"] == (expected is None)
