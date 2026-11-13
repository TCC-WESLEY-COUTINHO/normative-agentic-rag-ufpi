"""Operational action boundary; this does not choose a normative domain."""

import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class AgentAction(StrEnum):
    DIRECT = "DIRECT"
    NORMATIVE_RAG = "NORMATIVE_RAG"


@dataclass(frozen=True)
class ActionDecision:
    action: AgentAction
    reason_code: str
    direct_response: str | None = None


_SOCIAL = MappingProxyType(
    {
        "oi": ("safe_greeting", "Olá!"),
        "olá": ("safe_greeting", "Olá!"),
        "bom dia": ("safe_greeting", "Bom dia!"),
        "boa tarde": ("safe_greeting", "Boa tarde!"),
        "boa noite": ("safe_greeting", "Boa noite!"),
        "obrigado": ("safe_thanks", "De nada!"),
        "obrigada": ("safe_thanks", "De nada!"),
        "entendi": ("safe_acknowledgement", "Certo."),
        "até mais": ("safe_farewell", "Até mais!"),
        "tchau": ("safe_farewell", "Até mais!"),
    }
)


class AgentActionPolicy:
    def decide(self, message: str) -> ActionDecision:
        # Only normalize case, Unicode composition and terminal social punctuation.
        # Never match a prefix or strip words, clauses or invisible characters.
        normalized = unicodedata.normalize("NFC", message).strip().casefold()
        normalized = normalized.rstrip(".!?").rstrip()
        if normalized in _SOCIAL:
            reason, response = _SOCIAL[normalized]
            return ActionDecision(AgentAction.DIRECT, reason, response)
        return ActionDecision(AgentAction.NORMATIVE_RAG, "requires_normative_tool")
