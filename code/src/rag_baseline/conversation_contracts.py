"""Private conversation authority and explicitly derived public presentation."""

import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from rag_baseline.grounding import TemporalGroundingContext
from rag_baseline.output_contracts import NormativeReference
from rag_baseline.router import Scope
from rag_baseline.tool_contracts import NormativeToolResult
from rag_baseline.versioning import REGISTRY_PATH


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConversationIdentity(_Contract):
    user_id: StrictStr = Field(min_length=1)
    agent_id: StrictStr = Field(min_length=1)
    thread_id: StrictStr = Field(min_length=1)

    def storage_key(self) -> str:
        canonical = json.dumps(
            ["conversation_identity_v1", self.user_id, self.agent_id, self.thread_id],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class NormativeMemoryCompatibilityStamp(_Contract):
    memory_version: StrictStr = "1"
    core_version: StrictStr
    contract_version: StrictStr
    corpus_fingerprint: StrictStr = Field(pattern=r"^[a-f0-9]{64}$")
    registry_fingerprint: StrictStr = Field(pattern=r"^[a-f0-9]{64}$")


def build_memory_stamp(
    vector_store, registry_path=REGISTRY_PATH
) -> NormativeMemoryCompatibilityStamp:
    """Dependency creation only: read index once, never generate embeddings."""
    from rag_baseline.incremental_index import snapshot_collection

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    canonical = json.dumps(registry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return NormativeMemoryCompatibilityStamp(
        core_version="structured_output_v2",
        contract_version="1",
        corpus_fingerprint=snapshot_collection(vector_store.collection)["sha256"],
        registry_fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )


class PendingClarification(_Contract):
    original_question: StrictStr = Field(min_length=1)
    clarification_question: StrictStr = Field(min_length=1)
    correlation_id: UUID
    compatibility_stamp: NormativeMemoryCompatibilityStamp


class ConversationNormativeMemory(_Contract):
    memory_version: StrictStr = "1"
    conversation_identity: ConversationIdentity
    last_normative_question: StrictStr | None = None
    last_normative_result_persistence: dict | None = None
    last_normative_correlation_id: UUID | None = None
    pending_clarification: PendingClarification | None = None
    declared_level: Literal["graduacao", "pos_graduacao"] | None = None
    declared_level_source: Literal["explicit_declaration", "confirmed_clarification"] | None = None
    compatibility_stamp: NormativeMemoryCompatibilityStamp

    @model_validator(mode="after")
    def coherent_last_result(self):
        if (self.declared_level is None) != (self.declared_level_source is None):
            raise ValueError("Declared level requires its user declaration source.")
        if self.last_normative_result_persistence is not None:
            result = NormativeToolResult.from_persistence(self.last_normative_result_persistence)
            if result.status != "ANSWER" or not self.last_normative_question:
                raise ValueError("Only a completed normative answer can be reused.")
            if result.correlation_id != self.last_normative_correlation_id:
                raise ValueError("Stored normative correlation mismatch.")
        elif (
            self.last_normative_question is not None
            or self.last_normative_correlation_id is not None
        ):
            raise ValueError("Stored question requires its normative result.")
        return self

    def restore_result(self) -> NormativeToolResult | None:
        if self.last_normative_result_persistence is None:
            return None
        return NormativeToolResult.from_persistence(self.last_normative_result_persistence)


class GroundedFollowUpResult(_Contract):
    contract_version: Literal["1"] = "1"
    kind: Literal["REPEAT", "REPHRASE", "SUMMARY"]
    content: StrictStr = Field(min_length=1)
    source_correlation_id: UUID
    source_core_version: Literal["structured_output_v2"]
    source_contract_version: Literal["1"]
    references: list[NormativeReference]
    temporal_provenance: TemporalGroundingContext
    domain: Scope
    guard_status: Literal["ACCEPTED", "FALLBACK_TO_SOURCE"]


def load_conversation_memory(value, identity, current):
    """Revalidate serializer/model_construct output; never repair invalid authority."""
    if value is None:
        return None, "ABSENT", None
    try:
        data = value.model_dump() if isinstance(value, ConversationNormativeMemory) else value
        memory = ConversationNormativeMemory.model_validate(data)
        if memory.conversation_identity != identity:
            return None, "INVALID", "identity_mismatch"
    except (TypeError, ValueError):
        return None, "INVALID", "memory_invalid"
    differences = []
    if memory.memory_version != current.memory_version or memory.memory_version != "1":
        differences.append("memory_version")
    for field in NormativeMemoryCompatibilityStamp.model_fields:
        if getattr(memory.compatibility_stamp, field) != getattr(current, field):
            differences.append(field)
    if memory.pending_clarification and memory.pending_clarification.compatibility_stamp != current:
        differences.append("pending_compatibility")
    if differences:
        return memory, "STALE", ",".join(sorted(set(differences)))
    return memory, "VALID", None
