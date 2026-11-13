"""Noninteractive adapter with per-invocation internal retrieval strategies.

Dependencies are trusted application wiring, not query/tool arguments. There is no
tool registration, conversation state or caller-controlled provider configuration.
The existing AgenticRagService owns all normative decisions.
"""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError, field_validator

from rag_baseline.agentic import AgenticRagService
from rag_baseline.models import QueryResult
from rag_baseline.openrouter import OpenRouterError
from rag_baseline.output_contracts import GenerationAudit
from rag_baseline.retrieval_service import RetrievalExecution, StrategyRagService
from rag_baseline.router import NormativeRouter, RouterDecision
from rag_baseline.service import CorpusNotIndexedError, RagService
from rag_baseline.tool_contracts import (
    NormativeToolAudit,
    NormativeToolResult,
    RetrievalStrategy,
    ToolErrorCode,
    ToolStatus,
)
from rag_baseline.versioning import VersionFilter

_SAFE_MESSAGES = {
    ToolErrorCode.INVALID_REQUEST: "A consulta normativa contém dados inválidos.",
    ToolErrorCode.PROVIDER_ERROR: "Não foi possível consultar o provedor normativo.",
    ToolErrorCode.INDEX_UNAVAILABLE: "O índice normativo não está disponível.",
    ToolErrorCode.ROUTER_ERROR: "Não foi possível determinar o domínio da consulta.",
    ToolErrorCode.NO_ELIGIBLE_CONTEXT: "Não há contexto normativo elegível suficiente.",
    ToolErrorCode.CLARIFICATION_UNRESOLVED: "O esclarecimento não resolveu o domínio da consulta.",
    ToolErrorCode.INVALID_CORE_RESULT: "O núcleo não retornou um resultado estruturado válido.",
    ToolErrorCode.INTERNAL_ERROR: "Não foi possível concluir a consulta normativa.",
}
_ABSTENTION_MESSAGES = {
    "chronology_unresolved": (
        "Os documentos disponíveis não permitem afirmar qual regra se aplicava nesse período: "
        "a data de um documento não comprova sua aplicabilidade naquela data. Posso informar "
        "a redação documental de uma norma ou dispositivo que você indicar."
    ),
    "comparison_evidence_missing": (
        "Não encontrei trechos de todas as normas citadas para fazer essa comparação com "
        "segurança. Posso responder sobre cada norma separadamente."
    ),
    "amendment_unresolved": (
        "O dispositivo tem alteração registrada que não pude aplicar com segurança aos trechos "
        "disponíveis, por isso não apresento uma redação."
    ),
}
_DEFAULT_ABSTENTION = (
    "Não encontrei trechos normativos suficientes para responder a essa pergunta com segurança."
)
_CORE_ERRORS = {
    "generation_error": ToolErrorCode.PROVIDER_ERROR,
    "OpenRouterError": ToolErrorCode.PROVIDER_ERROR,
    "CorpusNotIndexedError": ToolErrorCode.INDEX_UNAVAILABLE,
    "router_error": ToolErrorCode.ROUTER_ERROR,
    "invalid_model_decision": ToolErrorCode.ROUTER_ERROR,
}


class _Query(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: StrictStr = Field(min_length=1, max_length=4000)
    clarification: StrictStr | None = Field(default=None, min_length=1, max_length=1000)
    correlation_id: UUID

    @field_validator("question", "clarification")
    @classmethod
    def not_blank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Query text must not be blank.")
        return value


class NormativeRagFacade:
    def __init__(self, service: RagService, router: NormativeRouter, version_filter: VersionFilter):
        # The core constructor builds a noninteractive graph. Pin Router V1 here;
        # accepting an arbitrary compiled graph would permit a different pipeline.
        self._service, self._router, self._version_filter = service, router, version_filter

    async def query(
        self,
        question: str,
        clarification: str | None = None,
        correlation_id: str | UUID | None = None,
    ) -> NormativeToolResult:
        try:
            request = _Query(
                question=question,
                clarification=clarification,
                correlation_id=correlation_id if correlation_id is not None else uuid4(),
            )
        except ValidationError:
            # An invalid operation ID is not reused as a conversation/thread ID.
            try:
                operation_id = UUID(str(correlation_id)) if correlation_id is not None else uuid4()
            except ValueError:
                operation_id = uuid4()
            return self._error(ToolErrorCode.INVALID_REQUEST, operation_id)
        execution = RetrievalExecution()
        try:
            core = AgenticRagService(
                StrategyRagService(self._service, self._version_filter, execution),
                self._router,
                self._version_filter,
                routing_mode="intent_v1",
            )
            result = await core.query(
                request.question,
                clarification=request.clarification,
                use_version_filter=True,
                scope=None,
            )
        except (OpenRouterError, CorpusNotIndexedError, ValueError) as exc:
            code = (
                ToolErrorCode.PROVIDER_ERROR
                if isinstance(exc, OpenRouterError)
                else ToolErrorCode.INDEX_UNAVAILABLE
                if isinstance(exc, CorpusNotIndexedError)
                else ToolErrorCode.INVALID_REQUEST
            )
            return self._with_retrieval(
                self._error(
                    code,
                    request.correlation_id,
                    NormativeToolAudit(exception_type=type(exc).__name__),
                ),
                execution,
            )
        except Exception as exc:
            return self._with_retrieval(
                self._error(
                    ToolErrorCode.INTERNAL_ERROR,
                    request.correlation_id,
                    NormativeToolAudit(exception_type=type(exc).__name__),
                ),
                execution,
            )
        return self._with_retrieval(self._map(result, request.correlation_id), execution)

    @staticmethod
    def _with_retrieval(result, execution):
        audit = execution.audit
        if audit is None and result.status == ToolStatus.CLARIFICATION:
            audit = dict(
                strategy=None,
                parsed_reference=None,
                consistency="router_clarification",
                executed=False,
                filter_applied=None,
                candidate_count=None,
                returned_count=0,
                identity_resolution_method={},
            )
        internal = result.internal_audit or NormativeToolAudit()
        return result.model_copy(
            update={
                "retrieval_strategy": execution.strategy or RetrievalStrategy.DENSE_VECTOR,
                "internal_audit": internal.model_copy(update={"retrieval_audit": audit}, deep=True),
            }
        )

    @staticmethod
    def _base(correlation_id):
        return dict(
            contract_version="1",
            core_version="structured_output_v2",
            correlation_id=correlation_id,
            retrieval_strategy="dense_vector",
        )

    @classmethod
    def _error(cls, code, correlation_id, audit=None):
        return NormativeToolResult(
            **cls._base(correlation_id),
            status=ToolStatus.ERROR,
            error_code=code,
            safe_message=_SAFE_MESSAGES[code],
            internal_audit=audit,
        )

    @classmethod
    def _map(cls, result, correlation_id):
        if not isinstance(result, QueryResult):
            return cls._error(ToolErrorCode.INVALID_CORE_RESULT, correlation_id)
        try:
            audit = NormativeToolAudit(
                response_kind=result.response_kind,
                generation_attempts=result.generation_attempts,
                output_audit=result.output_audit,
            ).model_copy(deep=True)
        except ValidationError:
            return cls._error(
                ToolErrorCode.INVALID_CORE_RESULT,
                correlation_id,
                NormativeToolAudit(exception_type="ValidationError"),
            )
        if result.error:
            return cls._error(
                _CORE_ERRORS.get(result.error, ToolErrorCode.INTERNAL_ERROR), correlation_id, audit
            )
        if result.needs_clarification:
            if (
                result.response_kind != "clarification"
                or result.generation_attempts != 0
                or result.normative_output is not None
                or result.output_audit is not None
            ):
                return cls._error(ToolErrorCode.INVALID_CORE_RESULT, correlation_id, audit)
            if not result.clarification_question:
                return cls._error(ToolErrorCode.CLARIFICATION_UNRESOLVED, correlation_id, audit)
            try:
                return NormativeToolResult(
                    **cls._base(correlation_id),
                    status=ToolStatus.CLARIFICATION,
                    needs_clarification=True,
                    clarification_question=result.clarification_question,
                    domain=result.selected_scope,
                    internal_audit=audit,
                )
            except ValidationError:
                return cls._error(ToolErrorCode.INVALID_CORE_RESULT, correlation_id, audit)
        if result.normative_output is None and result.generation_attempts == 0:
            reason = (result.version_filter or {}).get("insufficient_reason")
            try:
                return NormativeToolResult(
                    **cls._base(correlation_id),
                    status=ToolStatus.ANSWER,
                    answer=_ABSTENTION_MESSAGES.get(reason, _DEFAULT_ABSTENTION),
                    core_status="abstained",
                    domain=result.selected_scope,
                    internal_audit=audit.model_copy(update={"abstention_reason": reason}),
                )
            except ValidationError:
                return cls._error(ToolErrorCode.NO_ELIGIBLE_CONTEXT, correlation_id, audit)
        try:
            route = RouterDecision.model_validate(result.route)
            output, generation = result.normative_output, result.output_audit
            if not (
                result.version_filter
                and result.version_filter.get("enabled") is True
                and route.scope == result.selected_scope
                and not route.needs_clarification
                and output is not None
                and generation is not None
                and generation.guard_version
                == GenerationAudit.model_fields["guard_version"].default
                and generation.final_answer == result.answer
                and generation.guard_action == output.status
                and result.response_kind == "generated"
            ):
                return cls._error(ToolErrorCode.INVALID_CORE_RESULT, correlation_id, audit)
            return NormativeToolResult(
                **cls._base(correlation_id),
                status=ToolStatus.ANSWER,
                answer=result.answer,
                references=output.references,
                temporal_provenance=output.temporal_provenance,
                temporal_status_text=output.temporal_status_text,
                allowed_temporal_facts=output.allowed_temporal_facts,
                core_status=output.status,
                domain=result.selected_scope,
                internal_audit=audit,
            ).model_copy(deep=True)
        except ValidationError:
            return cls._error(ToolErrorCode.INVALID_CORE_RESULT, correlation_id, audit)
