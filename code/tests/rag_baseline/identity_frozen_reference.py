"""The 28-turn review replay, shared by the frozen capture and regression test."""

import dataclasses
from enum import Enum
from unittest.mock import patch
from uuid import UUID

from langchain_core.messages import BaseMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel
from test_conversation_interpretation import ScriptedInterpreter, level_reply, reading
from test_conversation_memory_followups import Facade, identity, stamp, turn

from rag_baseline.conversation_interpretation.transition_v2 import TransitionPolicyV2
from rag_baseline.scope_gate import ScopeGateResult

SEQUENCE = (
    "Quem é você?", "Qual seu nome?", "Você é o Bisco?", "Como você funciona?",
    "Quem te criou?", "O que você faz?", "Sou da graduação.", "Posso trancar o curso?",
    "Qual seu nome?", "Graduação.", "Repita.", "Qual é o prazo?", "obrigado",
    "Quem é o coordenador do curso?",
)


class RecordingGate:
    def __init__(self):
        self.questions = []

    async def classify(self, question):
        self.questions.append(question)
        return ScopeGateResult("IN_SCOPE_NORMATIVE", "classified", 1, 0)


class Normalizer:
    """Normalize message IDs consistently; preserve every other field and value."""

    def __init__(self):
        self.message_ids = {}

    def __call__(self, value):
        if isinstance(value, BaseModel):
            # Public model_dump also excludes private diagnostics nested inside
            # ToolMessage.artifact. Walk fields recursively to retain that audit.
            data = {key: getattr(value, key) for key in type(value).model_fields}
            data.update(value.model_extra or {})
            if isinstance(value, BaseMessage) and value.id is not None:
                data["id"] = self.message_ids.setdefault(
                    value.id, f"message-{len(self.message_ids) + 1}"
                )
            return self(data)
        if dataclasses.is_dataclass(value):
            return self(dataclasses.asdict(value))
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {key: self(item) for key, item in value.items()}
        if isinstance(value, list | tuple):
            return [self(item) for item in value]
        return value


async def replay(module, build, *, interpreted, identity_enabled=None):
    facade, gate, who = Facade(), RecordingGate(), identity(module)
    interpreter = None
    if interpreted:
        interpreter = ScriptedInterpreter({text: reading() for text in SEQUENCE})
        interpreter.script["Sou da graduação."] = level_reply(intent="level_declaration")
        interpreter.script["Graduação."] = level_reply()
    options = {} if identity_enabled is None else {"assistant_identity": identity_enabled}
    built = build(
        facade, checkpointer=InMemorySaver(), memory_stamp=stamp(module),
        scope_gate=gate, interpreter=interpreter, transition_policy=TransitionPolicyV2(),
        **options,
    )
    normalize, observed = Normalizer(), []
    # Keep correlation relationships (including pending reuse) deterministic, rather
    # than deleting UUID fields or replacing all UUIDs with the same placeholder.
    identifiers = iter(range(1, 1000))
    with patch.object(module, "uuid4", side_effect=lambda: UUID(int=next(identifiers))):
        for text in SEQUENCE:
            facade.status = "CLARIFICATION" if text == "Posso trancar o curso?" else "ANSWER"
            state = await turn(built, who, text)
            observed.append(normalize({
                "question": text,
                "state": state,
                "calls": {
                    "scope_gate": gate.questions,
                    "facade": facade.calls,
                    "interpreter": interpreter.calls if interpreter else [],
                },
            }))
    return observed
