"""TypeSafe Jev through the OpenRouter Decisions API (alpha).

Jev answers typed questions (choice / noul) with probabilities; it does not produce
free text. This adapter therefore never extracts or rewrites a question. All
API-specific detail stays in this module; the graph only sees the interpreter contract.
"""

import json
from dataclasses import dataclass, field

import httpx
from langchain_core.runnables import RunnableConfig, RunnableLambda

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
    lexical_level_spans,
)
from rag_baseline.conversation_interpretation.definitions import QUESTIONS

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
CONTRACT_VERSION = "jev-questions-v1"


@dataclass(frozen=True)
class JevSettings:
    api_key: str | None
    model: str = "typesafe/jev-1.14"
    url: str = DECISIONS_URL
    timeout_seconds: float = 20.0
    # Pre-registered before any DEV execution; never tuned on the evaluation sample.
    choice_threshold: float = 0.6
    noul_threshold: float = 0.5
    app_name: str | None = None
    provider: dict = field(default_factory=dict)


class JevDecisionInterpreter(ConversationInterpreter):
    name = "jev"

    def __init__(self, settings: JevSettings, *, transport=None, sync_transport=None):
        self.settings = settings
        self._transport = transport
        self._sync_transport = sync_transport
        self._call = RunnableLambda(self._post_sync, afunc=self._post, name="jev_decisions_api")

    def describe(self):
        s = self.settings
        return {
            "interpreter": self.name,
            "provider": "openrouter_decisions_api_alpha",
            "model": s.model,
            "url": s.url,
            "contract": CONTRACT_VERSION,
            "questions_sha256": _sha(json.dumps(QUESTIONS, sort_keys=True, ensure_ascii=False)),
            "choice_threshold": s.choice_threshold,
            "noul_threshold": s.noul_threshold,
            "timeout_seconds": s.timeout_seconds,
            "provider_preferences": s.provider,
        }

    # -- request ---------------------------------------------------------------------------
    def payload(self, context: TurnContext) -> dict:
        state = {
            "pending_question": context.pending_question,
            "assistant_request": context.pending_clarification_question,
            "previous_answered_question": context.last_normative_question,
            "user_message": context.message,
        }
        body = {
            "model": self.settings.model,
            "state": json.dumps(state, ensure_ascii=False),
            "questions": QUESTIONS,
        }
        if self.settings.provider:
            body["provider"] = self.settings.provider
        return body

    def _headers(self):
        if not self.settings.api_key:
            raise InterpreterResponseError("Decisions API key is not configured.")
        headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        if self.settings.app_name:
            headers["X-OpenRouter-Title"] = self.settings.app_name
        return headers

    async def _post(self, body: dict) -> dict:
        async with httpx.AsyncClient(
            timeout=self.settings.timeout_seconds, transport=self._transport
        ) as client:
            response = await client.post(self.settings.url, json=body, headers=self._headers())
        return _decode(response)

    def _post_sync(self, body: dict) -> dict:
        with httpx.Client(
            timeout=self.settings.timeout_seconds, transport=self._sync_transport
        ) as client:
            response = client.post(self.settings.url, json=body, headers=self._headers())
        return _decode(response)

    # -- interpretation -------------------------------------------------------------------
    def interpret(self, context, config: RunnableConfig | None = None):
        with _Timer() as timer:
            try:
                data = self._call.invoke(self.payload(context), config)
            except Exception as exc:
                error = exc
            else:
                error = None
        return self._outcome(context, None if error else data, error, timer.ms)

    async def ainterpret(self, context, config: RunnableConfig | None = None):
        with _Timer() as timer:
            try:
                data = await self._call.ainvoke(self.payload(context), config)
            except Exception as exc:
                error = exc
            else:
                error = None
        return self._outcome(context, None if error else data, error, timer.ms)

    def _outcome(self, context, data, error, ms) -> InterpretationOutcome:
        base = dict(latency_ms=ms, calls=1, model=self.settings.model, method="decisions_api")
        if error is not None:
            return InterpretationOutcome(
                self.name,
                failure_status(error),
                error_type=type(error).__name__,
                detail=str(error)[:200],
                **base,
            )
        try:
            # Any unexpected shape in usage or answers is a malformed response (AUD-07),
            # never an exception that aborts the conversation turn.
            usage = data.get("usage") or {}
            if not isinstance(usage, dict):
                raise InterpreterResponseError("Decisions response with non-object usage.")
            cost = usage.get("cost")
            base.update(
                model=data.get("model") or self.settings.model,
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
                # Billing metadata never invalidates a decision (independent review A6).
                cost_usd=float(cost) if isinstance(cost, int | float) else None,
            )
            candidate, probabilities, adjustments = self.map_answers(context, data.get("answers"))
        except (InterpreterResponseError, TypeError, ValueError, AttributeError) as exc:
            return InterpretationOutcome(
                self.name,
                "invalid_response",
                error_type=type(exc).__name__,
                detail=str(exc)[:200],
                **base,
            )
        outcome = finalize(self.name, candidate, context, **base)
        return InterpretationOutcome(
            **{**outcome.__dict__, "probabilities": probabilities, "adjustments": adjustments}
        )

    def map_answers(self, context, answers):
        if not isinstance(answers, dict):
            raise InterpreterResponseError("Decisions response without answers.")
        s, probabilities, adjustments = self.settings, {}, []

        def choice(name, fallback):
            answer = answers.get(name)
            if not isinstance(answer, dict) or answer.get("type") != "choice":
                raise InterpreterResponseError(f"Missing or refused choice answer: {name}")
            label = answer.get("choice")
            allowed = QUESTIONS[name]["criteria"]
            if label not in allowed:
                raise InterpreterResponseError(f"Unknown label for {name}")
            probs = answer.get("probabilities") or {}
            p = probs.get(label, answer.get("confidence"))
            probabilities[name] = {k: probs.get(k) for k in allowed} | {"_selected": label}
            if p is None or float(p) < s.choice_threshold:
                adjustments.append(f"{name}_below_threshold")
                return fallback
            return label

        def noul(name):
            answer = answers.get(name)
            if not isinstance(answer, dict) or answer.get("type") != "noul":
                raise InterpreterResponseError(f"Missing or refused noul answer: {name}")
            value = answer.get("noul")
            if not isinstance(value, int | float):
                raise InterpreterResponseError(f"Invalid noul value: {name}")
            probabilities[name] = float(value)
            return float(value) >= s.noul_threshold

        intent = choice("intent", "uncertain")
        level = choice("declared_level", "none")
        evidence = choice("level_evidence", "hedged" if level != "none" else "none")
        subject = choice("level_subject", "unknown")
        references, new_question, cancels = (
            noul("references_pending"),
            noul("has_new_question"),
            noul("cancels_pending"),
        )
        # Dependent questions answered independently: keep the level/evidence pair
        # coherent. Intent is never repaired; contradictions surface as 'inconsistent'.
        if level == "none" and evidence != "none":
            adjustments.append("evidence_dropped_without_level")
            evidence = "none"
        if evidence == "none" and level != "none":
            adjustments.append("level_dropped_without_evidence")
            level = "none"
        if not context.has_pending_operation and references:
            adjustments.append("references_pending_without_pending")
            references = False
        spans = lexical_level_spans(context.message, level) if level != "none" else ()
        candidate = dict(
            intent=intent,
            declared_level=level,
            level_evidence=evidence,
            level_subject=subject,
            references_pending=references,
            has_new_question=new_question,
            cancels_pending=cancels,
            extracted_question=None,
            evidence_spans=spans,
        )
        return candidate, probabilities, tuple(adjustments)


def _decode(response: httpx.Response) -> dict:
    if response.is_error:
        raise httpx.HTTPStatusError(
            f"Decisions API returned HTTP {response.status_code}.",
            request=response.request,
            response=response,
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise InterpreterResponseError("Decisions API returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise InterpreterResponseError("Decisions API returned a non-object body.")
    return data


def _sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
