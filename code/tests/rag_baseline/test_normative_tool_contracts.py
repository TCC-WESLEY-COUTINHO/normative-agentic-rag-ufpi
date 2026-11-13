"""Transport invariants: official output, public privacy and durable continuation."""

import importlib
import json
from uuid import UUID

import pytest
from normative_facade_fixtures import CORRELATION, FINAL, answer_data, audit_data
from pydantic import ValidationError


@pytest.fixture
def contracts():
    name = "rag_baseline.tool_contracts"
    if importlib.util.find_spec(name) is None:

        class Missing:
            def __getattr__(self, _):
                pytest.fail("NormativeToolResult is not implemented")

        return Missing()
    return importlib.import_module(name)


def state_data(status):
    data = answer_data()
    if status != "ANSWER":
        data.update(
            status=status,
            answer=None,
            references=[],
            temporal_provenance=None,
            temporal_status_text=None,
            allowed_temporal_facts=None,
            core_status=None,
            domain=None,
        )
    if status == "CLARIFICATION":
        data.update(needs_clarification=True, clarification_question="Graduação ou pós?")
    if status == "ERROR":
        data.update(error_code="provider_error", safe_message="Serviço indisponível.")
    return data


@pytest.mark.parametrize("status", ["ANSWER", "CLARIFICATION", "ERROR"])
def test_public_roundtrip_preserves_operation_state(contracts, status):
    result = contracts.NormativeToolResult.model_validate(state_data(status))
    restored = contracts.NormativeToolResult.model_validate_json(result.model_dump_json())
    assert restored == result
    assert restored.status.value == status
    assert restored.correlation_id == UUID(CORRELATION)
    if status == "ANSWER":
        assert restored.answer == FINAL
        assert restored.references[0].display_text == "Resolução 177/2012, art. 68"
        assert restored.temporal_provenance.evidence_states[0].temporal_role == "historical"
    elif status == "CLARIFICATION":
        assert restored.clarification_question == "Graduação ou pós?"
        assert restored.needs_clarification
    else:
        assert restored.answer is None and restored.error_code.value == "provider_error"


@pytest.mark.parametrize("status", ["ANSWER", "CLARIFICATION", "ERROR"])
def test_persistence_roundtrip_keeps_internal_audit(contracts, status):
    data = state_data(status)
    data["internal_audit"] = audit_data()
    result = contracts.NormativeToolResult.model_validate(data)
    restored = contracts.NormativeToolResult.from_persistence(
        json.loads(json.dumps(result.to_persistence()))
    )
    assert restored == result
    assert restored.internal_audit.output_audit.raw_answer == "UNSAFE RAW"
    assert restored.internal_audit.generation_attempts == 1


def test_public_dump_cannot_opt_in_internal_audit(contracts):
    result = contracts.NormativeToolResult(**answer_data(), internal_audit=audit_data())
    assert "internal_audit" not in result.model_dump()
    assert result.model_dump(include={"internal_audit"}) == {}
    assert "UNSAFE RAW" not in result.model_dump_json()
    assert "internal_audit" in result.to_persistence()


@pytest.mark.parametrize("field", ["contract_version", "core_version", "correlation_id"])
def test_missing_identity_is_not_silently_defaulted(contracts, field):
    data = answer_data()
    del data[field]
    with pytest.raises(ValidationError):
        contracts.NormativeToolResult.model_validate(data)


@pytest.mark.parametrize(
    "update",
    [
        {"contract_version": "2"},
        {"core_version": "structured_output_v1"},
        {"status": "SUCCESS"},
        {"domain": "grad"},
        {"correlation_id": "thread-1"},
        {"raw_answer": "not public"},
        {"answer": " "},
        {"references": []},
        {"temporal_provenance": None},
        {"core_status": None},
        {"needs_clarification": True},
        {"clarification_question": "Which?"},
        {"error_code": "provider_error"},
    ],
)
def test_invalid_answer_contract_fails_explicitly(contracts, update):
    with pytest.raises(ValidationError):
        contracts.NormativeToolResult.model_validate({**answer_data(), **update})


@pytest.mark.parametrize(
    "status,update",
    [
        ("CLARIFICATION", {"answer": FINAL}),
        ("CLARIFICATION", {"clarification_question": None}),
        ("CLARIFICATION", {"needs_clarification": False}),
        ("ERROR", {"answer": FINAL}),
        ("ERROR", {"error_code": None}),
        ("ERROR", {"safe_message": " "}),
    ],
)
def test_non_answer_cannot_masquerade_as_normative_answer(contracts, status, update):
    with pytest.raises(ValidationError):
        contracts.NormativeToolResult.model_validate({**state_data(status), **update})


def test_message_text_cannot_fabricate_temporal_provenance(contracts):
    with pytest.raises(ValidationError):
        contracts.NormativeToolResult(**{**answer_data(), "temporal_provenance": FINAL})


@pytest.mark.parametrize("mutation", ["version", "extra", "missing_result"])
def test_invalid_persistence_record_fails_explicitly(contracts, mutation):
    payload = contracts.NormativeToolResult(**answer_data()).to_persistence()
    if mutation == "version":
        payload["persistence_version"] = "2"
    elif mutation == "extra":
        payload["conversation_history"] = ["not normative authority"]
    else:
        del payload["result"]
    with pytest.raises(ValidationError):
        contracts.NormativeToolResult.from_persistence(payload)


@pytest.mark.parametrize("location", ["requested_time_context", "relation_source"])
def test_internal_prompt_key_is_not_part_of_public_provenance(contracts, location):
    data = answer_data()
    if location == "requested_time_context":
        data["temporal_provenance"][location]["prompt"] = "private prompt"
    else:
        data["temporal_provenance"]["evidence_states"][0][location] = {"prompt": "private prompt"}
    with pytest.raises(ValidationError):
        contracts.NormativeToolResult.model_validate(data)


@pytest.mark.parametrize("status", ["ANSWER", "CLARIFICATION", "ERROR"])
def test_checkpoint_serializer_uses_explicit_private_envelope(contracts, status):
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    result = contracts.NormativeToolResult(**state_data(status), internal_audit=audit_data())
    serializer = JsonPlusSerializer()
    restored = contracts.NormativeToolResult.from_persistence(
        serializer.loads_typed(serializer.dumps_typed(result.to_persistence()))
    )
    assert restored == result
    assert "UNSAFE RAW" not in restored.model_dump_json()
    assert restored.internal_audit.output_audit.raw_answer == "UNSAFE RAW"
