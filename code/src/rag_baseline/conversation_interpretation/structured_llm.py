"""Structured interpretation by a LangChain chat model (classification + extraction).

The model is any `BaseChatModel` supplied by the factory; this module never imports a
provider SDK. `with_structured_output` is used with an explicitly configured method,
because support for `json_schema` is not universal. The model reads one message and
returns the typed interpretation: it never answers the normative question.
"""

import json
from hashlib import sha256
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel, ConfigDict, Field

from rag_baseline.conversation_interpretation.base import (
    ConversationInterpreter,
    InterpreterResponseError,
    _Timer,
    failure_status,
    finalize,
)
from rag_baseline.conversation_interpretation.contracts import (
    InterpretationOutcome,
    TurnContext,
)
from rag_baseline.conversation_interpretation.definitions import QUESTIONS

CONTRACT_VERSION = "structured-llm-v2"  # v2: coherence rules stated (smoke 1)
StructuredMethod = Literal["json_schema", "function_calling", "json_mode"]


class TurnReading(BaseModel):
    """Output schema shown to the model. Lax on purpose: `finalize` validates afterwards,
    so a contradictory answer is recorded as such instead of failing inside parsing."""

    model_config = ConfigDict(extra="forbid")

    intent: Literal["clarification", "level_declaration", "new_question", "mixed", "uncertain"]
    declared_level: Literal["undergraduate", "postgraduate", "both", "none"]
    level_evidence: Literal["explicit", "indirect", "hedged", "none"]
    level_subject: Literal["self", "third_party", "generic", "unknown"]
    references_pending: bool
    has_new_question: bool
    cancels_pending: bool
    extracted_question: str | None = Field(
        description=(
            "Somente quando has_new_question é true: a pergunta nova copiada da mensagem, "
            "com as mesmas palavras, sem acrescentar nada. Caso contrário, null."
        )
    )
    evidence_spans: list[str] = Field(
        description="Trechos copiados literalmente da mensagem que mostram o nível; [] se não houver."
    )


def _criteria(name: str) -> str:
    question = QUESTIONS[name]
    lines = [f"- {name}: {question['instructions']}"]
    lines += [f"    * {label}: {text}" for label, text in question["criteria"].items()]
    return "\n".join(lines)


SYSTEM_PROMPT = (
    "Você interpreta UMA mensagem de um estudante em uma conversa com um assistente de "
    "normas acadêmicas da UFPI. Você não responde à pergunta do estudante e não explica "
    "normas. Apenas classifica a mensagem e, se ela contiver uma pergunta nova, copia essa "
    "pergunta com as palavras da própria mensagem.\n\n"
    "Regras:\n"
    "1. Use somente o que está escrito na mensagem; não deduza fatos sobre o estudante.\n"
    "2. Nível citado sobre outra pessoa (amigo, orientando, irmã) tem level_subject "
    "third_party.\n"
    "3. Pedir para comparar graduação e pós-graduação é declared_level both com "
    "level_subject generic.\n"
    "4. extracted_question e evidence_spans devem ser cópias literais de trechos da "
    "mensagem; nunca acrescente condições, datas, normas ou palavras.\n"
    "5. Na dúvida real, use intent uncertain.\n\n"
    "Coerência obrigatória entre campos (respostas incoerentes são descartadas):\n"
    "- declared_level none se e somente se level_evidence none.\n"
    "- clarification e level_declaration exigem um nível e has_new_question false; se a "
    "mensagem informa o nível E faz outra pergunta, use mixed.\n"
    "- new_question exige has_new_question true.\n"
    "- mixed exige has_new_question true e, além disso, um nível, um cancelamento ou a "
    "resposta ao pedido pendente.\n"
    "- extracted_question só pode ser preenchida quando has_new_question é true.\n\n"
    "Campos:\n" + "\n".join(_criteria(name) for name in QUESTIONS) + "\n"
    "- extracted_question: a pergunta nova copiada da mensagem, ou null.\n"
    "- evidence_spans: trechos literais da mensagem que indicam o nível; [] se nenhum."
)


def render_input(context: TurnContext) -> str:
    state = {
        "pending_question": context.pending_question,
        "assistant_request": context.pending_clarification_question,
        "previous_answered_question": context.last_normative_question,
        "user_message": context.message,
    }
    return json.dumps(state, ensure_ascii=False, indent=1)


def _usage(raw) -> dict:
    if not isinstance(raw, AIMessage):
        return {}
    usage = raw.usage_metadata or {}
    token_usage = (raw.response_metadata or {}).get("token_usage") or {}
    cost = token_usage.get("cost")
    return dict(
        input_tokens=int(usage.get("input_tokens") or token_usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or token_usage.get("completion_tokens") or 0),
        cost_usd=float(cost) if isinstance(cost, int | float) else None,
        model=(raw.response_metadata or {}).get("model_name"),
    )


class StructuredLLMInterpreter(ConversationInterpreter):
    name = "structured_llm"

    def __init__(
        self,
        model=None,
        *,
        method: StructuredMethod = "json_schema",
        model_name: str | None = None,
        structured: Runnable | None = None,
        provider_settings: dict | None = None,
    ):
        """`model` is a BaseChatModel; tests may pass `structured`, a Runnable that
        behaves like `model.with_structured_output(TurnReading, include_raw=True)`."""
        if (model is None) == (structured is None):
            raise ValueError("Provide exactly one of model or structured.")
        self.method, self.model_name = method, model_name
        self.provider_settings = dict(provider_settings or {})
        self._structured = structured or model.with_structured_output(
            TurnReading, method=method, include_raw=True
        )

    def describe(self):
        return {
            "interpreter": self.name,
            "model": self.model_name,
            "method": self.method,
            "contract": CONTRACT_VERSION,
            "system_prompt_sha256": sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
            "provider_settings": self.provider_settings,
        }

    def messages(self, context: TurnContext):
        return [SystemMessage(SYSTEM_PROMPT), HumanMessage(render_input(context))]

    def interpret(self, context, config: RunnableConfig | None = None):
        with _Timer() as timer:
            try:
                data, error = self._structured.invoke(self.messages(context), config), None
            except Exception as exc:
                data, error = None, exc
        return self._outcome(context, data, error, timer.ms)

    async def ainterpret(self, context, config: RunnableConfig | None = None):
        with _Timer() as timer:
            try:
                data, error = await self._structured.ainvoke(self.messages(context), config), None
            except Exception as exc:
                data, error = None, exc
        return self._outcome(context, data, error, timer.ms)

    def _outcome(self, context, data, error, ms) -> InterpretationOutcome:
        base = dict(latency_ms=ms, calls=1, model=self.model_name, method=self.method)
        if error is None:
            if not isinstance(data, dict) or "parsed" not in data:
                error = InterpreterResponseError("Structured output without include_raw shape.")
            else:
                base.update({k: v for k, v in _usage(data.get("raw")).items() if v is not None})
                if data.get("parsing_error") is not None or data.get("parsed") is None:
                    error = InterpreterResponseError(
                        f"Structured output not parsed: {data.get('parsing_error')}"
                    )
        if error is not None:
            return InterpretationOutcome(
                self.name,
                failure_status(error),
                error_type=type(error).__name__,
                detail=str(error)[:200],
                **base,
            )
        parsed = data["parsed"]
        candidate = parsed.model_dump() if isinstance(parsed, BaseModel) else parsed
        if isinstance(candidate, dict) and isinstance(candidate.get("evidence_spans"), list):
            candidate = {**candidate, "evidence_spans": tuple(candidate["evidence_spans"])}
        return finalize(self.name, candidate, context, **base)
