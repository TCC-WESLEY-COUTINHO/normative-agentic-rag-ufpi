"""Explicit user levels persist per conversation, never from normative result domains."""

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from test_conversation_memory_followups import Facade, config, identity, stamp, turn

from rag_baseline import conversation_graph as c
from rag_baseline.agent_graph import build_integrated_graph
from rag_baseline.conversation_contracts import load_conversation_memory
from rag_baseline.scope_gate import ScopeGateResult

AMBIGUOUS = "Quanto tempo tenho para terminar o curso? Dá para pedir mais prazo?"
NEW_QUESTION = "Quais documentos são exigidos para matrícula?"


class FakeScopeGate:
    def __init__(self):
        self.questions = []

    async def classify(self, question):
        self.questions.append(question)
        return ScopeGateResult("IN_SCOPE_NORMATIVE", "classified", 0, 0.0)


class FakeFacade(Facade):
    require_level = False

    async def query(self, **kwargs):
        if self.require_level:
            self.status = "ANSWER" if kwargs["clarification"] else "CLARIFICATION"
        return await super().query(**kwargs)


@pytest.fixture
def setup_graph():
    facade, gate, saver = FakeFacade(), FakeScopeGate(), InMemorySaver()
    graph = build_integrated_graph(
        facade, checkpointer=saver, memory_stamp=stamp(c), scope_gate=gate
    )
    return graph, facade, gate, identity(c)


@pytest.mark.asyncio
async def test_conv10_declaration_is_direct_then_new_question_uses_declared_level(setup_graph):
    graph, facade, gate, who = setup_graph
    declared = await turn(graph, who, "Sou aluno de mestrado.")
    assert declared["normative_result"] is None
    assert declared["turn_audit"].final_source == "direct_response"
    assert declared["messages"][-1].content == (
        "Certo, vou considerar pós-graduação nas próximas perguntas."
    )
    assert not facade.calls and not gate.questions
    memory = declared["conversation_memory"]
    assert memory.declared_level == "pos_graduacao"
    assert memory.declared_level_source == "explicit_declaration"
    assert memory.last_normative_question is None

    await graph.aupdate_state(config(who), {"conversation_memory": memory.model_dump(mode="json")})
    facade.require_level = True
    answered = await turn(graph, who, AMBIGUOUS)
    assert answered["normative_result"].status == "ANSWER"
    assert facade.calls[-1]["question"] == AMBIGUOUS
    assert facade.calls[-1]["clarification"] == "pós-graduação"
    assert answered["turn_audit"].declared_level_used
    assert gate.questions == [AMBIGUOUS]


@pytest.mark.parametrize(
    "declaration,level,canonical",
    [
        ("Faço graduação.", "graduacao", "graduação"),
        ("Mestrado.", "pos_graduacao", "pós-graduação"),
        ("Sou graduanda.", "graduacao", "graduação"),
        ("Sou doutorando.", "pos_graduacao", "pós-graduação"),
        ("Estou cursando a pos-graduacao", "pos_graduacao", "pós-graduação"),
        ("na pós", "pos_graduacao", "pós-graduação"),
    ],
)
@pytest.mark.asyncio
async def test_r1_singular_declarations_also_persist_without_pending(
    setup_graph, declaration, level, canonical
):
    graph, facade, _, who = setup_graph
    state = await turn(graph, who, declaration)
    assert not facade.calls
    assert state["conversation_memory"].declared_level == level
    await turn(graph, who, AMBIGUOUS)
    assert facade.calls[-1]["clarification"] == canonical


@pytest.mark.asyncio
async def test_new_declaration_replaces_previous_level(setup_graph):
    graph, facade, _, who = setup_graph
    await turn(graph, who, "Sou aluno de mestrado.")
    changed = await turn(graph, who, "Sou aluno de graduação.")
    assert changed["conversation_memory"].declared_level == "graduacao"
    assert changed["conversation_memory"].declared_level_source == "explicit_declaration"
    assert not facade.calls
    await turn(graph, who, AMBIGUOUS)
    assert facade.calls[-1]["clarification"] == "graduação"


@pytest.mark.parametrize(
    "question",
    [
        "Como funciona o trancamento na graduação?",
        "Qual a diferença entre graduação e pós-graduação no trancamento?",
        "Como funciona o trancamento em ambas?",
        "Como funciona o trancamento em ambos os níveis?",
        "Como funciona o trancamento nos dois níveis?",
        "Como funciona o trancamento na graduação e na pós?",
        "Como funciona o trancamento na pós?",
    ],
)
@pytest.mark.asyncio
async def test_explicit_or_both_levels_prevent_injection_and_preserve_declaration(
    setup_graph, question
):
    graph, facade, _, who = setup_graph
    await turn(graph, who, "Sou aluno de mestrado.")
    state = await turn(graph, who, question)
    assert facade.calls[-1]["question"] == question
    assert facade.calls[-1]["clarification"] is None
    assert not state["turn_audit"].declared_level_used
    assert state["conversation_memory"].declared_level == "pos_graduacao"
    await turn(graph, who, NEW_QUESTION)
    assert facade.calls[-1]["clarification"] == "pós-graduação"


@pytest.mark.asyncio
async def test_declared_level_is_isolated_by_thread(setup_graph):
    graph, facade, _, who = setup_graph
    await turn(graph, who, "Sou aluno de mestrado.")
    facade.status = "CLARIFICATION"
    other = await turn(graph, identity(c, thread="B"), AMBIGUOUS)
    assert facade.calls[-1]["clarification"] is None
    assert other["normative_result"].status == "CLARIFICATION"
    assert other["conversation_memory"].declared_level is None
    assert not other["turn_audit"].declared_level_used


@pytest.mark.parametrize(
    "reply,level", [("Faço mestrado.", "pos_graduacao"), ("graduação", "graduacao")]
)
@pytest.mark.asyncio
async def test_confirmed_pending_clarification_persists_level(setup_graph, reply, level):
    graph, facade, _, who = setup_graph
    facade.status = "CLARIFICATION"
    first = await turn(graph, who, AMBIGUOUS)
    assert first["normative_result"].status == "CLARIFICATION"
    facade.status = "ANSWER"
    confirmed = await turn(graph, who, reply)
    assert confirmed["turn_audit"].conversation_action == "CONTINUE_CLARIFICATION"
    assert not confirmed["turn_audit"].declared_level_used
    assert facade.calls[-1]["question"] == AMBIGUOUS
    assert facade.calls[-1]["clarification"] == reply
    assert facade.calls[-1]["correlation_id"] == first["normative_result"].correlation_id
    assert confirmed["conversation_memory"].declared_level == level
    assert confirmed["conversation_memory"].declared_level_source == "confirmed_clarification"
    assert confirmed["conversation_memory"].pending_clarification is None
    await turn(graph, who, NEW_QUESTION)
    assert facade.calls[-1]["clarification"] == (
        "graduação" if level == "graduacao" else "pós-graduação"
    )


@pytest.mark.asyncio
async def test_result_domain_never_creates_declared_level(setup_graph):
    graph, facade, _, who = setup_graph
    original_query = facade.query

    async def inferred_postgraduate(**kwargs):
        result = await original_query(**kwargs)
        return result.model_copy(update={"domain": "pos_graduacao"})

    facade.query = inferred_postgraduate
    answered = await turn(graph, who, AMBIGUOUS)
    assert answered["normative_result"].domain == "pos_graduacao"
    assert answered["conversation_memory"].declared_level is None
    assert answered["conversation_memory"].declared_level_source is None
    await turn(graph, who, NEW_QUESTION)
    assert facade.calls[-1]["clarification"] is None


@pytest.mark.asyncio
async def test_persisted_memory_without_new_fields_still_loads_valid(setup_graph):
    graph, facade, _, who = setup_graph
    first = await turn(graph, who, AMBIGUOUS)
    legacy = first["conversation_memory"].model_dump(mode="json")
    legacy.pop("declared_level", None)
    legacy.pop("declared_level_source", None)
    restored, status, reason = load_conversation_memory(legacy, who, stamp(c))
    assert status == "VALID" and reason is None
    assert restored.declared_level is None and restored.declared_level_source is None
    await graph.aupdate_state(config(who), {"conversation_memory": legacy})
    state = await turn(graph, who, NEW_QUESTION)
    assert state["turn_audit"].memory_status == "VALID"
    assert facade.calls[-1]["clarification"] is None


@pytest.mark.parametrize(
    "text",
    [
        "Sou mestrando e quero saber sobre a graduação.",
        "Estou cursando graduação e quero trancar o curso.",
        "Sou graduando? Não sei.",
        "Faço mestrado?",
        "Graduação?",
        "ambas",
    ],
)
@pytest.mark.asyncio
async def test_other_content_does_not_create_declaration(setup_graph, text):
    graph, _, _, who = setup_graph
    state = await turn(graph, who, text)
    assert state["conversation_memory"].declared_level is None


@pytest.mark.parametrize(
    "text,action",
    [
        ("E qual é o prazo?", "CONTINUATION_NORMATIVE_RAG"),
        ("E na pós?", "CONTEXTUAL_NORMATIVE_RAG"),
    ],
)
@pytest.mark.asyncio
async def test_followups_keep_existing_resolution_without_injection(setup_graph, text, action):
    graph, facade, _, who = setup_graph
    await turn(graph, who, "Sou aluno de mestrado.")
    await turn(graph, who, "Como funciona o trancamento na graduação?")
    state = await turn(graph, who, text)
    assert state["turn_audit"].conversation_action == action
    assert not state["turn_audit"].declared_level_used
    assert facade.calls[-1]["clarification"] is None
    assert state["conversation_memory"].declared_level == "pos_graduacao"


@pytest.mark.parametrize(
    "text,action",
    [
        ("Obrigado.", "SAFE_DIRECT"),
        ("Quem é você?", "ABOUT_ASSISTANT"),
        ("Repita.", "GROUNDED_TRANSFORM"),
        ("Quanto é 12 * 3?", "CALCULATOR"),
        ("cancelar", "CLEAR_PENDING"),
    ],
)
@pytest.mark.asyncio
async def test_other_actions_preserve_declared_level_and_do_not_call_facade(
    setup_graph, text, action
):
    graph, facade, _, who = setup_graph
    await turn(graph, who, "Sou aluno de mestrado.")
    await turn(graph, who, "Como funciona o trancamento na graduação?")
    if action == "CLEAR_PENDING":
        facade.status = "CLARIFICATION"
        await turn(graph, who, NEW_QUESTION)
    calls = len(facade.calls)
    state = await turn(graph, who, text)
    assert state["turn_audit"].conversation_action == action
    assert len(facade.calls) == calls
    assert not state["turn_audit"].declared_level_used
    assert state["conversation_memory"].declared_level == "pos_graduacao"
    assert state["conversation_memory"].declared_level_source == "explicit_declaration"
