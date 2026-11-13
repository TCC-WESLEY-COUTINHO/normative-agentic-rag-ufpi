"""Pre-freeze regressions from manual defects; controlled external provider only."""

import json
from uuid import uuid4

import pytest
import test_normative_output as output_cases
import test_retrieval_strategies as retrieval_cases
from langgraph.checkpoint.memory import InMemorySaver

from rag_baseline.agent_graph import build_integrated_graph
from rag_baseline.conversation_contracts import (
    ConversationIdentity,
    NormativeMemoryCompatibilityStamp,
)
from rag_baseline.normative_output import compose_answer
from rag_baseline.router import NormativeRouter
from rag_baseline.routing_normalization import routing_question
from rag_baseline.service import RagService
from rag_baseline.tool_facade import NormativeRagFacade
from schema import ChatMessage

registry = retrieval_cases.registry
runtime = retrieval_cases.runtime
POST = [
    ("como entrar na pós?", "como entrar na pós-graduação?"),
    ("como entrar na pós-graduação?", "como entrar na pós-graduação?"),
    ("como faço para entrar na pós?", "como faço para entrar na pós-graduação?"),
    ("como funciona o ingresso na pós?", "como funciona o ingresso na pós-graduação?"),
    ("quais os requisitos da pós?", "quais os requisitos da pós-graduação?"),
    ("como concorrer para a pós?", "como concorrer para a pós-graduação?"),
    ("como entrar pela pós?", "como entrar pela pós-graduação?"),
]
GRAD = ["como entrar na graduação?", "como faço para entrar na graduação?"]
AMBIGUOUS = ["como entrar?", "como funciona o ingresso?", "quais são os requisitos para ingresso?"]
COUNTER = [
    "qual era a regra pós-alteração?",
    "como ficou após a alteração?",
    "regra pós-2025",
    "qual era a regra na pós-alteração?",
    "regra da pós-2025",
]
BIBLIOGRAPHIES = [
    "Fontes:\n- Resolução 956/2025, art. 62",
    "Referências:\n1. Resolução 956/2025, art. 62",
    "Sources:\n- Resolução 956/2025, art. 62",
    "## Fontes normativas\n- Resolução 956/2025, art. 62",
    "**Referências:**\n1) Resolução 956/2025, art. 62",
    "Fontes:\n• Resolução 956/2025, art. 62",
    "Fontes consultadas:\n- Resolução 956/2025, art. 62",
    "Fontes oficiais:\n- Resolução 956/2025, art. 62",
    "Bibliografia:\n- Resolução 956/2025, art. 62",
    "Fontes:\n- Resolução 956/2025,\n  art. 62",
]


class ScopeProvider(retrieval_cases.Provider):
    """Replay the observed abbreviation miss; decisions for canonical forms are fixed."""

    def __init__(self):
        super().__init__()
        self.decisions = []
        self.scopes = {normalized: "pos_graduacao" for _, normalized in POST}
        self.scopes.update({text: "graduacao" for text in GRAD})
        self.scopes["Qual a média para aprovação na graduação?"] = "graduacao"
        self.scopes["na graduação e na pós-graduação"] = "ambas"

    async def structured_chat(self, **payload):
        data = json.loads(payload["user_prompt"])
        self.routes.append(data)
        scope = self.scopes.get(data["question"])
        if scope is None and data.get("clarification") == "graduação":
            scope = "graduacao"
        decision = dict(
            scope=scope,
            needs_clarification=scope is None,
            clarification_question="Graduação ou pós?" if scope is None else None,
            reason_code={
                None: "insufficient_scope_signal",
                "graduacao": "explicit_graduacao",
                "pos_graduacao": "explicit_pos",
                "ambas": "cross_norm_comparison",
            }[scope],
        )
        self.decisions.append(decision)
        return json.dumps(decision)


@pytest.fixture
def integrated(runtime):
    service, _, version_filter, _, chunks = runtime
    provider = ScopeProvider()
    service.openrouter = provider
    facade = NormativeRagFacade(service, NormativeRouter(provider), version_filter)
    stamp = NormativeMemoryCompatibilityStamp(
        memory_version="1",
        contract_version="1",
        core_version="structured_output_v2",
        corpus_fingerprint="a" * 64,
        registry_fingerprint="b" * 64,
    )
    graph = build_integrated_graph(facade, checkpointer=InMemorySaver(), memory_stamp=stamp)
    who = ConversationIdentity(
        user_id=str(uuid4()), agent_id="chatbot_ufpi_integrated_v1", thread_id=str(uuid4())
    )

    async def turn(text):
        return await graph.ainvoke(
            {"messages": [("human", text)], "conversation_identity": who},
            {"configurable": {"thread_id": who.storage_key()}},
        )

    yield turn, provider, chunks
    service.vector_store.client._system.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("original,expected_router_input", POST)
async def test_explicit_post_reaches_terminal_post_without_domain_pending(
    integrated, original, expected_router_input
):
    turn, provider, _ = integrated
    state = await turn(original)
    result = state["normative_result"]
    assert result.status == "ANSWER"
    assert result.domain == "pos_graduacao"
    assert state["conversation_memory"].pending_clarification is None
    assert state["conversation_memory"].last_normative_question == original
    assert routing_question(original) == expected_router_input
    assert provider.routes == []
    assert result.retrieval_strategy == "dense_vector"
    assert {e.source_norm for e in result.temporal_provenance.evidence_states} == {"ufpi-956-2025"}
    assert state["turn_audit"].conversation_action == "NORMATIVE_RAG"


@pytest.mark.asyncio
@pytest.mark.parametrize("question", GRAD)
async def test_explicit_grad_is_preserved(integrated, question):
    turn, provider, _ = integrated
    state = await turn(question)
    assert state["normative_result"].domain == "graduacao"
    assert state["normative_result"].status == "ANSWER"
    assert provider.routes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("question", AMBIGUOUS)
async def test_ambiguous_ingress_still_requires_domain(integrated, question):
    turn, provider, _ = integrated
    state = await turn(question)
    assert state["normative_result"].status == "CLARIFICATION"
    assert state["conversation_memory"].pending_clarification is not None
    assert provider.routes[-1]["question"] == question
    assert provider.embeddings == []


@pytest.mark.asyncio
@pytest.mark.parametrize("question", COUNTER)
async def test_temporal_post_cues_are_not_expanded_to_postgraduate(integrated, question):
    turn, provider, _ = integrated
    state = await turn(question)
    assert state["normative_result"].status == "CLARIFICATION"
    assert provider.routes[-1]["question"] == question
    assert provider.embeddings == []


@pytest.mark.asyncio
async def test_conflicting_explicit_domains_retain_both(integrated):
    turn, provider, _ = integrated
    state = await turn("na graduação e na pós")
    assert provider.routes[-1]["question"] == "na graduação e na pós-graduação"
    assert state["normative_result"].domain == "ambas"


@pytest.mark.asyncio
async def test_explicit_post_after_grad_does_not_reuse_grad_or_create_pending(integrated):
    turn, provider, _ = integrated
    first = await turn("Qual a média para aprovação na graduação?")
    second = await turn("como entrar na pós?")
    assert first["normative_result"].domain == "graduacao"
    assert second["normative_result"].status == "ANSWER"
    assert second["normative_result"].domain == "pos_graduacao"
    assert second["normative_result"].correlation_id != first["normative_result"].correlation_id
    assert second["conversation_memory"].pending_clarification is None
    assert second["conversation_memory"].last_normative_question == "como entrar na pós?"
    assert provider.routes == []


def test_composer_does_not_append_a_second_bibliography():
    grounding, refs, _ = output_cases.output_parts()
    body = "De acordo com o art. 62 da Resolução 956/2025, o texto estabelece essa regra."
    answer = compose_answer("Contexto selecionado.", body, refs)
    assert answer == "Contexto selecionado.\n\n" + body
    assert refs and grounding.evidence_states


@pytest.mark.parametrize("bibliography", BIBLIOGRAPHIES)
def test_guard_rejects_only_an_unambiguous_terminal_bibliography(bibliography):
    raw = "Conteúdo substantivo.\n\n" + bibliography
    assert "terminal_bibliography" in output_cases.codes(raw)
    assert raw == "Conteúdo substantivo.\n\n" + bibliography
    violations = output_cases.guard(raw)
    assert all(raw[v.start : v.end] == v.excerpt for v in violations)


@pytest.mark.parametrize(
    "body",
    [
        "Segundo as fontes, o texto descreve as condições.",
        "A fonte normativa define os requisitos.",
        "De acordo com o art. 62 da Resolução 956/2025, essa é a regra.",
        "Fontes de financiamento:\n- Bolsas institucionais.",
        "Fontes:\nO texto discute o conceito de fontes jurídicas.",
        "Fontes:\n- Resolução 956/2025, art. 62\n\nA discussão continua em prosa.",
    ],
)
def test_guard_preserves_legitimate_mentions_and_nonterminal_prose(body):
    assert "terminal_bibliography" not in output_cases.codes(body)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "second,expected_action",
    [
        ("Conteúdo substantivo.", "regenerated"),
        ("Conteúdo substantivo.\n\nFontes:\n- Resolução 956/2025, art. 53", "fallback"),
    ],
)
async def test_bibliography_retries_once_then_preserves_existing_fallback(second, expected_action):
    item, chunks, grounding = output_cases.case("H_citation")
    first = "Conteúdo substantivo.\n\nFontes:\n- Resolução 956/2025, art. 53"
    remote = output_cases.SequenceClient([first, second])
    result = await RagService(
        openrouter=remote, vector_store=None, top_k=5, embedding_model="test", llm_model="test"
    ).generate(item["question"], chunks, temporal_grounding=grounding)
    assert result.generation_attempts == 2
    assert len(remote.calls) == 2
    assert result.output_audit.guard_action == expected_action
    assert result.output_audit.raw_answer == first
    assert "Fontes:" not in result.answer
    assert result.normative_output.references
    if expected_action == "fallback":
        assert "Não foi possível formular" in result.answer


@pytest.mark.asyncio
async def test_references_are_final_context_not_model_attribution_and_include_exact_text(
    integrated,
):
    turn, _, chunks = integrated
    state = await turn("como entrar na pós-graduação?")
    result = state["normative_result"]
    assert result.status == "ANSWER" and len(result.references) == 2
    assert "art." not in result.internal_audit.output_audit.raw_answer
    for reference in result.references:
        chunk = next(c for c in chunks if c.id == reference.chunk_id)
        assert getattr(reference, "evidence_text", None) == chunk.content
    message = ChatMessage(type="ai", content=result.answer, normative_result=result)
    restored = ChatMessage.model_validate_json(message.model_dump_json())
    assert restored.normative_result.references == result.references
    assert "internal_audit" not in message.model_dump_json()


@pytest.mark.asyncio
async def test_grounded_repeat_inherits_exact_evidence_across_checkpoint_and_sse(integrated):
    from client import AgentClient
    from service.normative_transport import project_integrated_state

    turn, _, _ = integrated
    original = (await turn("como entrar na pós-graduação?"))["normative_result"]
    repeated = await turn("Repita")
    derived = repeated["grounded_followup_result"]
    assert derived.references == original.references
    assert all(reference.evidence_text for reference in derived.references)
    message = project_integrated_state(repeated)
    client = AgentClient(get_info=False)
    restored = client._parse_stream_line(
        "data: " + json.dumps({"type": "message", "content": message.model_dump(mode="json")})
    )
    assert restored.grounded_followup_result.references == original.references
    assert "internal_audit" not in restored.model_dump_json()


def test_router_prompt_classifies_explicit_post_without_requiring_subtype():
    """Contract regression from real model asking lato/stricto before choosing post."""
    from rag_baseline.router import ROUTER_PROMPT, RouterDecision

    lines = ROUTER_PROMPT.splitlines()
    example = "question: Como entrar na pós-graduação?"
    assert example in lines, "Missing explicit postgraduate-level policy example"
    answer = lines[lines.index(example) + 1]
    assert answer.startswith("JSON: ")
    decision = RouterDecision.model_validate_json(answer.removeprefix("JSON: "))
    assert decision.scope == "pos_graduacao"
    assert not decision.needs_clarification
    assert "sem exigir distinção entre lato sensu e stricto sensu" in ROUTER_PROMPT
