"""Interchangeable interpreters exposed to LangGraph as LangChain Runnables."""

import asyncio
from abc import ABC, abstractmethod
from time import perf_counter

import httpx
from langchain_core.runnables import Runnable, RunnableConfig, RunnableLambda
from pydantic import ValidationError

from rag_baseline.conversation_interpretation.contracts import (
    InterpretationOutcome,
    TurnContext,
    TurnInterpretation,
    grounding_violations,
)


class InterpreterResponseError(ValueError):
    """The provider answered, but not with a usable typed decision."""


def failure_status(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException | asyncio.TimeoutError | TimeoutError):
        return "timeout"
    if type(exc).__name__ in {"APITimeoutError", "ReadTimeout", "ConnectTimeout"}:
        return "timeout"
    if isinstance(exc, InterpreterResponseError | ValidationError):
        return "invalid_response"
    return "provider_error"


def finalize(
    name: str, candidate: dict | TurnInterpretation, context: TurnContext, **telemetry
) -> InterpretationOutcome:
    """Validate contract and grounding; a model answer is never repaired silently."""
    try:
        interpretation = (
            candidate
            if isinstance(candidate, TurnInterpretation)
            else TurnInterpretation.model_validate(candidate)
        )
    except ValidationError as exc:
        inconsistent = any("Inconsistent interpretation" in str(e.get("msg")) for e in exc.errors())
        return InterpretationOutcome(
            name,
            "inconsistent" if inconsistent else "invalid_response",
            error_type="ValidationError",
            detail=str(exc.errors()[0].get("msg"))[:200],
            **telemetry,
        )
    violations = grounding_violations(interpretation, context.message)
    if violations:
        return InterpretationOutcome(
            name,
            "ungrounded",
            interpretation=interpretation,
            detail=",".join(violations),
            **telemetry,
        )
    return InterpretationOutcome(name, "ok", interpretation=interpretation, **telemetry)


class ConversationInterpreter(ABC):
    """One message in, one typed interpretation out. No state, no side effects."""

    name: str = "interpreter"

    @abstractmethod
    def interpret(
        self, context: TurnContext, config: RunnableConfig | None = None
    ) -> InterpretationOutcome: ...

    @abstractmethod
    async def ainterpret(
        self, context: TurnContext, config: RunnableConfig | None = None
    ) -> InterpretationOutcome: ...

    def describe(self) -> dict:
        """Reproducible configuration of this interpreter (no secrets)."""
        return {"interpreter": self.name}

    def as_runnable(self) -> Runnable:
        def run(context: TurnContext, config: RunnableConfig) -> InterpretationOutcome:
            return self.interpret(TurnContext.model_validate(context), config)

        async def arun(context: TurnContext, config: RunnableConfig) -> InterpretationOutcome:
            return await self.ainterpret(TurnContext.model_validate(context), config)

        return RunnableLambda(run, afunc=arun, name=f"conversation_interpreter.{self.name}")


class _Timer:
    def __enter__(self):
        self.start = perf_counter()
        return self

    def __exit__(self, *exc):
        self.ms = (perf_counter() - self.start) * 1000
        return False
