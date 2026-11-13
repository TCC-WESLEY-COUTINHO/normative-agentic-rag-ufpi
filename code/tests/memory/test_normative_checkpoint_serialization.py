"""The installed serializer must preserve the explicit private persistence envelope."""

from uuid import uuid4

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from rag_baseline.tool_contracts import NormativeToolResult


def sample():
    return NormativeToolResult(
        contract_version="1",
        core_version="structured_output_v2",
        status="ERROR",
        retrieval_strategy="dense_vector",
        correlation_id=uuid4(),
        error_code="provider_error",
        safe_message="Falha segura.",
        internal_audit={"exception_type": "ControlledPrivateDiagnostic"},
    )


def test_default_serializer_excludes_audit_from_direct_result():
    original, serializer = sample(), JsonPlusSerializer()
    restored = serializer.loads_typed(serializer.dumps_typed(original))
    assert restored.model_dump() == original.model_dump()
    assert restored.internal_audit is None


def test_explicit_persistence_envelope_survives_installed_serializer():
    original, serializer = sample(), JsonPlusSerializer()
    envelope = serializer.loads_typed(serializer.dumps_typed(original.to_persistence()))
    restored = NormativeToolResult.from_persistence(envelope)
    assert restored.internal_audit == original.internal_audit
    assert restored.correlation_id == original.correlation_id
