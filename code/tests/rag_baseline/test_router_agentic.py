import json

import httpx
import pytest
from pydantic import ValidationError

from rag_baseline.openrouter import OpenRouterClient
from rag_baseline.router import NormativeRouter, RouterDecision


def client_for(output, requests, status=200):
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            status, json={"choices": [{"message": {"content": json.dumps(output)}}]}
        )

    return OpenRouterClient(
        api_key="test",
        embedding_model="embedding/test",
        llm_model="baseline/model",
        transport=httpx.MockTransport(respond),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question,scope,reason",
    [
        ("Qual a frequência mínima na graduação?", "graduacao", "explicit_graduacao"),
        ("Qual o prazo para qualificação no mestrado?", "pos_graduacao", "explicit_pos"),
        ("Compare o trancamento na graduação e na pós.", "ambas", "cross_norm_comparison"),
        ("Posso cancelar uma disciplina?", None, "ambiguous_academic_level"),
    ],
)
async def test_router_returns_only_validated_scope_from_structured_model(question, scope, reason):
    requests = []
    expected = dict(
        scope=scope,
        needs_clarification=scope is None,
        clarification_question="Graduação ou pós-graduação?" if scope is None else None,
        reason_code=reason,
    )
    result = await NormativeRouter(client_for(expected, requests)).route(question)
    assert result.scope == scope
    assert result.needs_clarification == (scope is None)
    assert result.reason_code == reason
    if scope is None:
        assert "graduação" in result.clarification_question
    else:
        assert result.clarification_question is None
    assert "answer" not in result.model_dump()
    payload = requests[0]
    assert payload["model"] == "baseline/model"
    assert payload["temperature"] == 0
    assert payload["response_format"]["type"] == "json_schema"
    assert json.loads(payload["messages"][1]["content"])["question"] == question
    assert len(requests) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": "direito"},
        {"needs_clarification": True},
        {"answer": "Art. 1º: regra inventada"},
        {"reason_code": "long internal reasoning"},
    ],
)
def test_router_decision_rejects_inconsistent_or_unbounded_output(changes):
    values = dict(
        scope="graduacao",
        needs_clarification=False,
        clarification_question=None,
        reason_code="explicit_graduacao",
    )
    with pytest.raises(ValidationError):
        RouterDecision(**(values | changes))


@pytest.mark.parametrize(
    "scope,reason",
    [
        ("graduacao", "cross_norm_comparison"),
        ("pos_graduacao", "explicit_graduacao"),
        ("ambas", "explicit_pos"),
        (None, "explicit_pos"),
    ],
)
def test_router_rejects_reason_code_incompatible_with_decision(scope, reason):
    with pytest.raises(ValidationError):
        RouterDecision(
            scope=scope,
            needs_clarification=scope is None,
            clarification_question="Qual nível?" if scope is None else None,
            reason_code=reason,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output,status,reason",
    [
        ({"scope": "invalid"}, 200, "invalid_model_decision"),
        ({}, 503, "router_error"),
    ],
)
async def test_router_failure_never_imputes_scope(output, status, reason):
    result = await NormativeRouter(client_for(output, [], status)).route("Posso cancelar?")
    assert result.scope is None
    assert result.needs_clarification
    assert result.reason_code == reason


@pytest.mark.asyncio
async def test_router_model_override_and_clarification_preserve_question():
    requests = []
    output = dict(
        scope="pos_graduacao",
        needs_clarification=False,
        clarification_question=None,
        reason_code="explicit_pos",
    )
    router = NormativeRouter(client_for(output, requests), model="router/override")
    await router.route("Posso cancelar?", clarification="Pós-graduação")
    assert requests[0]["model"] == "router/override"
    assert json.loads(requests[0]["messages"][1]["content"]) == {
        "question": "Posso cancelar?",
        "clarification": "Pós-graduação",
    }


@pytest.mark.asyncio
async def test_router_cannot_pass_model_legal_text_as_clarification():
    output = dict(
        scope=None,
        needs_clarification=True,
        clarification_question="Art. 999: você pode cancelar livremente.",
        reason_code="insufficient_scope_signal",
    )
    result = await NormativeRouter(client_for(output, [])).route("Posso cancelar?")
    assert "999" not in result.clarification_question
    assert "cancelar livremente" not in result.clarification_question
