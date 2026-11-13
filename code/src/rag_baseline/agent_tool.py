"""Async framework tool adapter. Only the facade owns normative operations."""

from typing import Protocol
from uuid import UUID, uuid4

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from rag_baseline.tool_contracts import (
    NormativeToolAudit,
    NormativeToolResult,
    RetrievalStrategy,
    ToolErrorCode,
    ToolStatus,
)


class NormativeFacade(Protocol):
    async def query(
        self,
        question: str,
        clarification: str | None = None,
        correlation_id: str | UUID | None = None,
    ) -> NormativeToolResult: ...


class NormativeToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: StrictStr = Field(min_length=1, max_length=4000)
    # This intra-turn graph has no parent-owned pending clarification operation.
    # Keep the optional slot explicit, but reject unsolicited continuation text.
    clarification: None = None
    correlation_id: UUID | None = None


def safe_tool_error(correlation_id: UUID, exception_type: str | None = None) -> NormativeToolResult:
    return NormativeToolResult(
        contract_version="1",
        core_version="structured_output_v2",
        status=ToolStatus.ERROR,
        retrieval_strategy=RetrievalStrategy.DENSE_VECTOR,
        correlation_id=correlation_id,
        error_code=ToolErrorCode.INTERNAL_ERROR,
        safe_message="Não foi possível concluir a consulta normativa com segurança.",
        internal_audit=NormativeToolAudit(exception_type=exception_type),
    )


def validated_result(value: NormativeToolResult) -> NormativeToolResult:
    if not isinstance(value, NormativeToolResult):
        raise TypeError("A typed normative result is required.")
    # Revalidate nested mutable fields/model_construct without parsing any message.
    return NormativeToolResult.model_validate(
        {
            **value.model_dump(),
            "internal_audit": value.internal_audit,
        }
    )


def build_normative_tool(facade: NormativeFacade) -> StructuredTool:
    async def query(
        question: str,
        clarification: None = None,
        correlation_id: UUID | None = None,
    ) -> tuple[str, NormativeToolResult]:
        correlation = correlation_id or uuid4()
        try:
            result = validated_result(
                await facade.query(
                    question=question,
                    clarification=clarification,
                    correlation_id=correlation,
                )
            )
            if result.correlation_id != correlation:
                raise ValueError("Normative result correlation mismatch.")
        except Exception as exc:
            # CancelledError is a BaseException and intentionally propagates.
            result = safe_tool_error(correlation, type(exc).__name__)
        return f"normative_rag: {result.status.value}", result

    return StructuredTool.from_function(
        coroutine=query,
        name="normative_rag",
        description="Consulta normativa acadêmica da UFPI utilizando o pipeline normativo controlado.",
        args_schema=NormativeToolInput,
        response_format="content_and_artifact",
    )
