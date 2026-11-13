"""Natural level-only replies resume pending operations without replacing their question."""

import unicodedata

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from test_conversation_memory_followups import Facade, identity, stamp, turn

from rag_baseline import conversation_graph as c
from rag_baseline.agent_graph import build_integrated_graph
from rag_baseline.conversation_policy import ConversationFollowUpPolicy, FollowUpAction
from rag_baseline.scope_gate import ScopeGateResult

LEVELS = ["graduação", "pós-graduação", "pós", "mestrado", "doutorado", "stricto sensu"]
DECLARATIONS = [
    "",
    "Sou aluno de ",
    "Sou aluna da ",
    "Sou estudante do ",
    "Sou da ",
    "Faço ",
    "Estou na ",
    "Estou no ",
    "É sobre a ",
    "É na ",
    "É da ",
    "Curso ",
]
ADDITIONAL_DECLARATIONS = [
    "Sou mestrando",
    "Sou mestranda",
    "Sou doutorando",
    "Sou doutoranda",
    "Sou graduando",
    "Sou graduanda",
    "Estou cursando graduação",
    "Estou cursando o mestrado",
    "Estou cursando a pós-graduação",
]
COUNTEREXAMPLES = [
    "Sou da graduação, mas quero saber sobre o mestrado.",
    "Estou na graduação. Qual é o prazo para colação de grau?",
    "Esqueça a pergunta anterior, quero saber sobre o IRA.",
    "Agora quero perguntar sobre a pós-graduação.",
    "Não sei qual norma se aplica.",
    "Sou aluno de graduação, mas não sei.",
    "Faço mestrado e doutorado.",
    "Graduação ou pós-graduação.",
    "Sou aluno de graduação e quero cancelar.",
    "Não sou aluno de graduação.",
    "Talvez seja na graduação.",
    "Faço mestrado?",
    "É na graduação?",
    "Estou na graduação. Não sei qual norma se aplica.",
    "Sou aluno de graduação. Cancele.",
    "Sou mestrando e quero saber sobre a graduação.",
    "Estou cursando graduação e quero trancar o curso.",
    "Sou graduando? Não sei.",
]


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("declaration", DECLARATIONS)
@pytest.mark.parametrize("ending", ["", "."])
@pytest.mark.parametrize("unaccented", [False, True])
@pytest.mark.parametrize("pending", [False, True])
def test_level_only_declaration_requires_pending(level, declaration, ending, unaccented, pending):
    text = declaration + level + ending
    if unaccented:
        text = "".join(
            char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
        )
    action = ConversationFollowUpPolicy().decide(text, pending=pending).action
    if pending:
        assert action == FollowUpAction.CONTINUE_CLARIFICATION
    else:
        assert action != FollowUpAction.CONTINUE_CLARIFICATION


@pytest.mark.parametrize("text", COUNTEREXAMPLES)
@pytest.mark.parametrize("pending", [False, True])
def test_other_content_cannot_resume_pending_operation(text, pending):
    assert (
        ConversationFollowUpPolicy().decide(text, pending=pending).action
        != FollowUpAction.CONTINUE_CLARIFICATION
    )


@pytest.mark.parametrize("text", ADDITIONAL_DECLARATIONS)
@pytest.mark.parametrize("ending", ["", ".", "?"])
@pytest.mark.parametrize("unaccented", [False, True])
@pytest.mark.parametrize("pending", [False, True])
def test_student_or_cursando_declaration_requires_pending(text, ending, unaccented, pending):
    text += ending
    if unaccented:
        text = "".join(
            char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
        )
    action = ConversationFollowUpPolicy().decide(text, pending=pending).action
    if pending and ending != "?":
        assert action == FollowUpAction.CONTINUE_CLARIFICATION
    else:
        assert action != FollowUpAction.CONTINUE_CLARIFICATION


@pytest.mark.parametrize(
    "text",
    [
        "graduação",
        "na graduação",
        "pós",
        "na pós",
        "pós-graduação",
        "ambas",
        "ambos",
        "os dois",
        "as duas",
        "  NA   PÓS?!  ",
    ],
)
def test_legacy_clarifications_keep_working(text):
    assert (
        ConversationFollowUpPolicy().decide(text, pending=True).action
        == FollowUpAction.CONTINUE_CLARIFICATION
    )


class FakeScopeGate:
    def __init__(self):
        self.questions = []

    async def classify(self, question):
        self.questions.append(question)
        return ScopeGateResult("IN_SCOPE_NORMATIVE", "classified", 0, 0.0)


@pytest.mark.parametrize(
    "reply, resumes",
    [
        ("Sou aluno de graduação.", True),
        ("Sou aluno de mestrado.", True),
        ("Faço mestrado.", True),
        ("Mestrado.", True),
        ("Doutorado.", True),
        ("É sobre a graduação.", True),
        ("É na graduação.", True),
        ("Estou na graduação.", True),
        *((text + ".", True) for text in ADDITIONAL_DECLARATIONS),
        ("Sou mestrando e quero saber sobre a graduação.", False),
        ("Estou cursando graduação e quero trancar o curso.", False),
        ("Sou graduando? Não sei.", False),
        ("Estou na graduação. Qual é o prazo para colação de grau?", False),
    ],
)
@pytest.mark.asyncio
async def test_graph_preserves_original_question_only_for_level_reply(reply, resumes):
    facade, gate = Facade(), FakeScopeGate()
    graph = build_integrated_graph(
        facade, checkpointer=InMemorySaver(), memory_stamp=stamp(c), scope_gate=gate
    )
    who = identity(c)
    original = "Posso cancelar uma disciplina?"
    facade.status = "CLARIFICATION"
    first = await turn(graph, who, original)
    assert first["normative_result"].status == "CLARIFICATION"
    pending = first["conversation_memory"].pending_clarification
    assert pending.original_question == original
    assert len(facade.calls) == 1

    facade.status = "ANSWER"
    second = await turn(graph, who, reply)
    assert second["normative_result"].status == "ANSWER"
    assert len(facade.calls) == 2
    call = facade.calls[-1]
    assert call["question"] == (original if resumes else reply)
    assert call["clarification"] == (reply if resumes else None)
    assert (call["correlation_id"] == pending.correlation_id) is resumes
    assert second["turn_audit"].conversation_action == (
        "CONTINUE_CLARIFICATION" if resumes else "NORMATIVE_RAG"
    )
    memory = second["conversation_memory"]
    assert memory.pending_clarification is None
    assert memory.last_normative_question == (original if resumes else reply)
    assert gate.questions == [original, original if resumes else reply]
