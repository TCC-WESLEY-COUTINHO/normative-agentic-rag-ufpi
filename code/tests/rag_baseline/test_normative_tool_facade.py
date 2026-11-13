"""A facade call cannot select a fragment of the normative pipeline."""

import importlib
import inspect
from uuid import UUID

import pytest
from normative_facade_fixtures import CORRELATION, FINAL, core_answer

from rag_baseline.agentic import AgenticRagService
from rag_baseline.models import QueryResult
from rag_baseline.openrouter import OpenRouterError
from rag_baseline.router import NormativeRouter
from rag_baseline.service import CorpusNotIndexedError, RagService
from rag_baseline.versioning import NormativeRegistry, VersionFilter


@pytest.fixture
def module():
    name = "rag_baseline.tool_facade"
    if importlib.util.find_spec(name) is None:

        class Missing:
            def __getattr__(self, _):
                pytest.fail("NormativeRagFacade is not implemented")

        return Missing()
    return importlib.import_module(name)


def fake_core(monkeypatch, module, result=None, error=None):
    calls = []

    class Core:
        def __init__(self, service, router, version_filter, *, routing_mode):
            assert routing_mode == "intent_v1"

        async def query(self, question, *, clarification, use_version_filter, scope):
            calls.append((question, clarification, use_version_filter, scope))
            if error:
                raise error
            return result if result is not None else core_answer()

    monkeypatch.setattr(module, "AgenticRagService", Core)
    return module.NormativeRagFacade(object(), object(), object()), calls


@pytest.mark.asyncio
async def test_delegates_automatic_filtered_query_and_preserves_official_result(
    module, monkeypatch
):
    core = core_answer()
    facade, calls = fake_core(monkeypatch, module, core)
    result = await facade.query(
        "Pergunta original", clarification="Graduação", correlation_id=CORRELATION
    )
    assert calls == [("Pergunta original", "Graduação", True, None)]
    assert result.status.value == "ANSWER" and result.answer == FINAL
    assert result.domain == "graduacao" and result.retrieval_strategy.value == "dense_vector"
    assert result.references[0].model_dump() == core.normative_output.references[0].model_dump()
    assert result.references[0].model_dump() != core.references[0].model_dump()
    assert result.temporal_provenance.model_dump() == core.normative_output.temporal_provenance
    assert result.correlation_id == UUID(CORRELATION)
    assert result.core_status == "accepted"
    assert "FULL CHUNK EVIDENCE" not in result.model_dump_json()
    assert "UNSAFE RAW" not in result.model_dump_json()
    assert result.internal_audit.output_audit.raw_answer == "UNSAFE RAW"


@pytest.mark.asyncio
async def test_result_does_not_alias_mutable_core_provenance(module, monkeypatch):
    core = core_answer()
    facade, _ = fake_core(monkeypatch, module, core)
    result = await facade.query("Pergunta")
    core.normative_output.temporal_provenance["known_relations"].append({"invented": True})
    core.output_audit.guard_violations.clear()
    assert result.temporal_provenance.known_relations == []


@pytest.mark.asyncio
async def test_creates_distinct_operation_ids_without_thread_state(module, monkeypatch):
    facade, _ = fake_core(monkeypatch, module)
    first, second = await facade.query("A"), await facade.query("B")
    assert isinstance(first.correlation_id, UUID)
    assert first.correlation_id != second.correlation_id


@pytest.mark.parametrize(
    "flag",
    [
        "version_filter",
        "use_version_filter",
        "manual_scope",
        "scope",
        "sector",
        "top_k",
        "model",
        "temperature",
        "retrieval_backend",
        "skip_grounding",
        "skip_guard",
        "raw_retrieval",
        "raw_search",
    ],
)
@pytest.mark.asyncio
async def test_bypass_arguments_rejected_by_real_signature(module, monkeypatch, flag):
    facade, calls = fake_core(monkeypatch, module)
    assert set(inspect.signature(facade.query).parameters) == {
        "question",
        "clarification",
        "correlation_id",
    }
    with pytest.raises(TypeError):
        await facade.query("Pergunta", **{flag: False})
    assert calls == []


@pytest.mark.asyncio
async def test_clarification_returns_to_parent_without_answer_or_interrupt(module, monkeypatch):
    core = QueryResult(
        answer="Graduação ou pós?",
        references=[],
        llm_model="fake",
        embedding_model="fake",
        needs_clarification=True,
        clarification_question="Graduação ou pós?",
        response_kind="clarification",
        generation_attempts=0,
        selected_scope=None,
    )
    facade, _ = fake_core(monkeypatch, module, core)
    result = await facade.query("Posso cancelar?", correlation_id=CORRELATION)
    assert result.status.value == "CLARIFICATION" and result.answer is None
    assert result.needs_clarification and result.clarification_question == "Graduação ou pós?"
    assert result.references == [] and result.temporal_provenance is None
    assert result.correlation_id == UUID(CORRELATION)
    assert result.internal_audit.generation_attempts == 0


@pytest.mark.parametrize(
    "error,code",
    [
        (OpenRouterError("SECRET provider body"), "provider_error"),
        (CorpusNotIndexedError("SECRET path"), "index_unavailable"),
        (ValueError("SECRET input"), "invalid_request"),
        (RuntimeError("SECRET traceback"), "internal_error"),
    ],
)
@pytest.mark.asyncio
async def test_exception_mapping_never_exposes_exception_text(module, monkeypatch, error, code):
    facade, _ = fake_core(monkeypatch, module, error=error)
    result = await facade.query("Pergunta")
    assert result.status.value == "ERROR" and result.answer is None
    assert result.error_code.value == code
    assert "SECRET" not in result.model_dump_json()
    assert "SECRET" not in str(result.to_persistence())
    assert result.internal_audit.exception_type == type(error).__name__


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("no_structured", "invalid_core_result"),
        ("no_audit", "invalid_core_result"),
        ("v1_audit", "invalid_core_result"),
        ("unfiltered", "invalid_core_result"),
        ("manual", "invalid_core_result"),
        ("mismatched_domain", "invalid_core_result"),
        ("raw_in_final", "invalid_core_result"),
        ("bad_provenance", "invalid_core_result"),
        ("generation_error", "provider_error"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_or_failed_core_result_is_not_normative_answer(
    module, monkeypatch, mutation, code
):
    core = core_answer()
    if mutation == "no_structured":
        core.normative_output = None
    elif mutation == "no_audit":
        core.output_audit = None
    elif mutation == "v1_audit":
        core.output_audit = core.output_audit.model_copy(update={"guard_version": "1"})
    elif mutation == "unfiltered":
        core.version_filter = {"enabled": False}
    elif mutation == "manual":
        core.route = None
    elif mutation == "mismatched_domain":
        core.selected_scope = "pos_graduacao"
    elif mutation == "raw_in_final":
        core.answer = "UNSAFE RAW"
    elif mutation == "bad_provenance":
        core.normative_output.temporal_provenance["prompt"] = "SECRET"
    else:
        core.error = "generation_error"
    facade, _ = fake_core(monkeypatch, module, core)
    result = await facade.query("Pergunta")
    assert result.status.value == "ERROR" and result.answer is None
    assert result.error_code.value == code
    assert result.references == []


@pytest.mark.parametrize(
    "question", ["", "  ", "x" * 4001], ids=["empty", "whitespace", "too_long"]
)
@pytest.mark.asyncio
async def test_invalid_input_does_not_invoke_core(module, monkeypatch, question):
    facade, calls = fake_core(monkeypatch, module)
    result = await facade.query(question)
    assert result.status.value == "ERROR" and result.error_code.value == "invalid_request"
    assert calls == []


class Provider:
    llm_model = "fake"

    def __init__(self, scope="graduacao", body="Conteúdo controlado."):
        self.scope, self.body = scope, body
        self.routes, self.prompts, self.embeddings = [], [], []

    async def structured_chat(self, **payload):
        import json

        self.routes.append(json.loads(payload["user_prompt"]))
        return json.dumps(
            dict(
                scope=self.scope,
                needs_clarification=self.scope is None,
                clarification_question="Graduação ou pós?" if self.scope is None else None,
                reason_code={
                    None: "insufficient_scope_signal",
                    "graduacao": "explicit_graduacao",
                    "pos_graduacao": "explicit_pos",
                    "ambas": "cross_norm_comparison",
                }[self.scope],
            )
        )

    async def embed(self, texts):
        self.embeddings.extend(texts)
        return [[0.0]]

    async def chat(self, **payload):
        self.prompts.append(payload)
        return self.body


def real_dependencies(scope="graduacao", body="Conteúdo controlado."):
    from rag_baseline.corpus import load_corpus
    from rag_baseline.models import RetrievedChunk
    from rag_baseline.versioning import REGISTRY_PATH

    original = next(
        c
        for c in load_corpus(
            REGISTRY_PATH.parent.parent / "evaluation/corpora/graduacao_setor_v2.json",
            id_prefix="ufpi-177-2012",
        )
        if c.article_number == "68"
    )

    class Store:
        def count(self):
            return 1

        def query(self, embedding, top_k, *, sector=None, excluded_sources=None):
            assert sector == "graduacao" and top_k == 5
            return [RetrievedChunk(**original.model_dump(), distance=0.1, rank=1)]

    provider = Provider(scope, body)
    service = RagService(
        openrouter=provider, vector_store=Store(), top_k=5, embedding_model="fake", llm_model="fake"
    )
    return service, NormativeRouter(provider), VersionFilter(NormativeRegistry.load()), provider


@pytest.mark.asyncio
async def test_real_pipeline_equivalence_and_structured_grounding(module):
    service, router, vf, provider = real_dependencies()
    question = "Como era o art. 68 na graduação antes da alteração?"
    direct = await AgenticRagService(service, router, vf).query(question)
    result = await module.NormativeRagFacade(service, router, vf).query(question)
    assert result.status.value == "ANSWER" and result.answer == direct.answer
    assert [r.model_dump() for r in result.references] == [
        r.model_dump() for r in direct.normative_output.references
    ]
    assert result.temporal_provenance.model_dump() == direct.normative_output.temporal_provenance
    assert provider.routes == []  # Both calls declare graduação explicitly.
    assert len(provider.embeddings) == 2
    assert all("[TEMPORAL GROUNDING]" in p["user_prompt"] for p in provider.prompts)
    assert result.internal_audit.output_audit.guard_version == "5"


@pytest.mark.asyncio
async def test_real_pipeline_clarification_has_no_retrieval_generation_or_interrupt(module):
    service, router, vf, provider = real_dependencies(scope=None)
    result = await module.NormativeRagFacade(service, router, vf).query("Posso cancelar?")
    assert result.status.value == "CLARIFICATION"
    assert provider.embeddings == provider.prompts == []


@pytest.mark.asyncio
async def test_v2_fallback_remains_authoritative_answer_with_separate_core_status(module):
    service, router, vf, provider = real_dependencies(body="Resolução 9999/2099, art. 9999.")
    result = await module.NormativeRagFacade(service, router, vf).query(
        "Art. 68 na graduação antes da alteração?"
    )
    assert result.status.value == "ANSWER" and result.core_status == "fallback"
    assert "9999/2099" not in result.answer and len(provider.prompts) == 2
    assert "9999/2099" in result.internal_audit.output_audit.raw_answer


@pytest.mark.asyncio
async def test_provider_subclass_keeps_provider_error_category(module, monkeypatch):
    class TemporaryProviderError(OpenRouterError):
        pass

    facade, _ = fake_core(monkeypatch, module, error=TemporaryProviderError("private response"))
    result = await facade.query("Pergunta")
    assert result.error_code.value == "provider_error"


@pytest.mark.asyncio
async def test_inconsistent_generated_result_is_not_clarification(module, monkeypatch):
    core = core_answer()
    core.needs_clarification = True
    core.clarification_question = "Graduação ou pós?"
    core.selected_scope = None
    facade, _ = fake_core(monkeypatch, module, core)
    result = await facade.query("Pergunta")
    assert result.status.value == "ERROR"
    assert result.error_code.value == "invalid_core_result"


@pytest.mark.asyncio
async def test_cancellation_is_not_converted_to_error_response(module, monkeypatch):
    import asyncio

    facade, _ = fake_core(monkeypatch, module, error=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await facade.query("Pergunta")


@pytest.mark.asyncio
async def test_malformed_internal_audit_returns_structured_error(module, monkeypatch):
    core = core_answer()
    core.generation_attempts = -1
    facade, _ = fake_core(monkeypatch, module, core)
    result = await facade.query("Pergunta")
    assert result.status.value == "ERROR" and result.answer is None
    assert result.error_code.value == "invalid_core_result"
