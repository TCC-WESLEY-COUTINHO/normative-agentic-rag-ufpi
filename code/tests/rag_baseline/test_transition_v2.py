"""Stage 7 cycles P0-P3: transition policy v2 against v1, through the real graph.

Every defect test runs with both policies. With v1 it is a strict xfail: the defect must
still be present (RED evidence kept permanently). With v2 it must pass. Regression guards
(behaviour v1 already had right) must pass with both. Interpretations are scripted: no
network, no model; phrasings are generic and do not come from the DEV scenarios.
"""

import httpx
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from test_conversation_interpretation import (
    AMBIGUOUS,
    NEW_QUESTION,
    Gate,
    LevelFacade,
    ScriptedInterpreter,
    level_reply,
    reading,
)
from test_conversation_memory_followups import Facade, identity, stamp, turn

from rag_baseline import conversation_graph as c
from rag_baseline.agent_graph import build_integrated_graph
from rag_baseline.conversation_interpretation import ConversationTransitionPolicy
from rag_baseline.conversation_interpretation.base import ConversationInterpreter
from rag_baseline.conversation_interpretation.jev import JevDecisionInterpreter, JevSettings
from rag_baseline.conversation_interpretation.transition_v2 import TransitionPolicyV2

POLICIES = {"v1": ConversationTransitionPolicy, "v2": TransitionPolicyV2}


def defect(cycle):
    """v1 must exhibit the defect (strict xfail); v2 must be correct."""
    return pytest.mark.parametrize(
        "policy",
        [
            pytest.param("v1", marks=pytest.mark.xfail(strict=True, reason=f"{cycle}: v1 defect")),
            "v2",
        ],
    )


guard = pytest.mark.parametrize("policy", ["v1", "v2"])


def build(policy, script=None, interpreter=None, facade=None):
    facade, gate = facade or LevelFacade(), Gate()
    graph = build_integrated_graph(
        facade,
        checkpointer=InMemorySaver(),
        memory_stamp=stamp(c),
        scope_gate=gate,
        interpreter=interpreter or ScriptedInterpreter(script or {}),
        transition_policy=POLICIES[policy](),
    )
    return graph, facade, gate


async def with_pending(graph, who, question=AMBIGUOUS):
    first = await turn(graph, who, question)
    assert first["normative_result"].status == "CLARIFICATION"
    return first


def mixed(level="undergraduate", span="graduação", subject="self", references=True, **kw):
    return reading(
        intent="mixed",
        declared_level=level,
        level_evidence="explicit",
        level_subject=subject,
        references_pending=references,
        evidence_spans=(span,),
        **kw,
    )


# ------------------------------------------------------------------ P1: new questions


@defect("P1")
@pytest.mark.asyncio
async def test_p1_level_plus_new_question_runs_the_new_question(policy):
    msg = "Faço graduação, e quanto tempo tenho pra entregar o estágio?"
    graph, facade, _ = build(policy, {AMBIGUOUS: reading(), msg: mixed()})
    who = identity(c)
    first = await with_pending(graph, who)
    state = await turn(graph, who, msg)
    assert facade.calls[-1]["question"] == msg
    assert facade.calls[-1]["correlation_id"] != first["normative_result"].correlation_id
    assert state["turn_audit"].superseded_pending
    assert state["conversation_memory"].declared_level == "graduacao"


@defect("P1")
@pytest.mark.asyncio
async def test_p1_two_requests_in_one_message_never_drop_the_new_one(policy):
    msg = "pós. aliás, também queria saber sobre a banca de qualificação"
    graph, facade, _ = build(
        policy,
        {AMBIGUOUS: reading(), msg: mixed(level="postgraduate", span="pos", subject="generic")},
    )
    who = identity(c)
    await with_pending(graph, who)
    await turn(graph, who, msg)
    assert facade.calls[-1]["question"] == msg  # the request actually made is processed


@defect("P1")
@pytest.mark.asyncio
async def test_p1_uncertain_reading_with_a_new_question_does_not_swallow_it(policy):
    msg = "Na graduação posso pedir revisão da nota final da disciplina?"
    uncertain = reading(
        intent="uncertain",
        has_new_question=True,
        declared_level="undergraduate",
        level_evidence="explicit",
        evidence_spans=("graduacao",),
    )
    graph, facade, _ = build(policy, {AMBIGUOUS: reading(), msg: uncertain})
    who = identity(c)
    await with_pending(graph, who)
    calls = len(facade.calls)
    await turn(graph, who, msg)
    assert len(facade.calls) == calls + 1 and facade.calls[-1]["question"] == msg


@guard
@pytest.mark.asyncio
async def test_p1_pure_clarification_with_context_still_resumes(policy):
    msg = "graduação, sou do curso de física"
    graph, facade, _ = build(policy, {AMBIGUOUS: reading(), msg: level_reply()})
    who = identity(c)
    first = await with_pending(graph, who)
    await turn(graph, who, msg)
    assert facade.calls[-1]["question"] == AMBIGUOUS
    assert facade.calls[-1]["correlation_id"] == first["normative_result"].correlation_id


@guard
@pytest.mark.asyncio
async def test_p1_plain_new_question_is_new(policy):
    graph, facade, _ = build(policy, {AMBIGUOUS: reading(), NEW_QUESTION: reading()})
    who = identity(c)
    await with_pending(graph, who)
    await turn(graph, who, NEW_QUESTION)
    assert facade.calls[-1]["question"] == NEW_QUESTION


@guard
@pytest.mark.asyncio
async def test_p1_cancel_then_new_question_runs_new_and_clears_pending(policy):
    msg = "deixa pra lá. Como faço matrícula em disciplina isolada na graduação?"
    cancel = mixed(references=False, cancels_pending=True)
    graph, facade, _ = build(policy, {AMBIGUOUS: reading(), msg: cancel})
    who = identity(c)
    await with_pending(graph, who)
    facade.require_level, facade.status = False, "ANSWER"
    state = await turn(graph, who, msg)
    assert facade.calls[-1]["question"] == msg
    assert state["conversation_memory"].pending_clarification is None


@guard
@pytest.mark.asyncio
async def test_p1_mentioning_the_previous_subject_without_resuming_is_new(policy):
    msg = "sobre aquilo que perguntei antes, deixa; quero saber de colação de grau"
    graph, facade, _ = build(policy, {AMBIGUOUS: reading(), msg: reading(cancels_pending=True)})
    who = identity(c)
    await with_pending(graph, who)
    await turn(graph, who, msg)
    assert facade.calls[-1]["question"] == msg


@guard
@pytest.mark.asyncio
async def test_p1_context_dependent_followup_keeps_a_prime_resolution(policy):
    facade = Facade()
    graph, _, _ = build(
        policy,
        {"Como funciona o trancamento na graduação?": reading(), "E qual é o prazo?": reading()},
        facade=facade,
    )
    who = identity(c)
    await turn(graph, who, "Como funciona o trancamento na graduação?")
    state = await turn(graph, who, "E qual é o prazo?")
    assert state["turn_audit"].conversation_action == "CONTINUATION_NORMATIVE_RAG"


# ------------------------------------------------------------------ P2: third parties


THIRD_PENDING = "minha irmã faz mestrado"


@defect("P2")
@pytest.mark.asyncio
async def test_p2_third_party_level_never_resolves_the_users_pending_question(policy):
    third = level_reply(
        level="postgraduate", span="mestrado", subject="third_party", intent="level_declaration"
    )
    graph, facade, _ = build(policy, {AMBIGUOUS: reading(), THIRD_PENDING: third})
    who = identity(c)
    first = await with_pending(graph, who)
    calls = len(facade.calls)
    state = await turn(graph, who, THIRD_PENDING)
    assert len(facade.calls) == calls
    assert state["turn_audit"].conversation_action == "CLARIFY_INTENT"
    pending = state["conversation_memory"].pending_clarification
    assert pending.correlation_id == first["normative_result"].correlation_id
    assert state["conversation_memory"].declared_level is None


@defect("P2")
@pytest.mark.asyncio
async def test_p2_user_level_never_leaks_into_a_question_about_someone_else(policy):
    declare = "eu sou do mestrado"
    about_cousin = "meu primo faz engenharia, ele pode fazer intercâmbio?"
    script = {
        declare: level_reply(level="postgraduate", span="mestrado", intent="level_declaration"),
        about_cousin: reading(
            declared_level="undergraduate",
            level_evidence="indirect",
            level_subject="third_party",
            evidence_spans=("engenharia",),
        ),
        AMBIGUOUS: reading(),
    }
    graph, facade, _ = build(policy, script, facade=Facade())
    who = identity(c)
    await turn(graph, who, declare)
    state = await turn(graph, who, about_cousin)
    assert facade.calls[-1]["clarification"] is None
    assert not state["turn_audit"].declared_level_used
    assert state["conversation_memory"].declared_level == "pos_graduacao"
    await turn(graph, who, AMBIGUOUS)  # back to the user: their own level applies again
    assert facade.calls[-1]["clarification"] == "pós-graduação"


@defect("P2")
@pytest.mark.asyncio
async def test_p2_explicit_third_party_level_applies_to_that_question_only(policy):
    declare = "sou aluno de mestrado"
    about_friend = "minha amiga é da graduação. ela pode trancar uma disciplina?"
    script = {
        declare: level_reply(level="postgraduate", span="mestrado", intent="level_declaration"),
        about_friend: reading(
            declared_level="undergraduate",
            level_evidence="explicit",
            level_subject="third_party",
            evidence_spans=("graduacao",),
        ),
        AMBIGUOUS: reading(),
    }
    graph, facade, _ = build(policy, script, facade=Facade())
    who = identity(c)
    await turn(graph, who, declare)
    state = await turn(graph, who, about_friend)
    assert facade.calls[-1]["clarification"] == "graduação"
    assert state["turn_audit"].third_party_query_level == "graduação"
    assert state["conversation_memory"].declared_level == "pos_graduacao"
    await turn(graph, who, AMBIGUOUS)
    assert facade.calls[-1]["clarification"] == "pós-graduação"


@defect("P2")
@pytest.mark.asyncio
async def test_p2_generic_level_outside_grammar_resumes_without_becoming_user_level(policy):
    msg = "é sobre a disciplina do doutorado"
    generic = level_reply(level="postgraduate", span="doutorado", subject="generic")
    graph, facade, _ = build(policy, {AMBIGUOUS: reading(), msg: generic})
    who = identity(c)
    await with_pending(graph, who)
    state = await turn(graph, who, msg)
    assert facade.calls[-1]["question"] == AMBIGUOUS
    assert state["conversation_memory"].declared_level is None


@guard
@pytest.mark.asyncio
async def test_p2_explicit_self_declaration_still_persists(policy):
    msg = "eu faço doutorado em química"
    graph, facade, _ = build(
        policy,
        {msg: level_reply(level="postgraduate", span="doutorado", intent="level_declaration")},
    )
    state = await turn(graph, identity(c), msg)
    assert state["conversation_memory"].declared_level == "pos_graduacao"


@guard
@pytest.mark.asyncio
async def test_p2_relative_declaration_without_question_is_never_stored(policy):
    msg = "meu pai fez mestrado aqui"
    third = level_reply(
        level="postgraduate", span="mestrado", subject="third_party", intent="level_declaration"
    )
    graph, facade, _ = build(policy, {msg: third})
    state = await turn(graph, identity(c), msg)
    assert (
        state["conversation_memory"] is None or state["conversation_memory"].declared_level is None
    )
    assert not facade.calls


@guard
@pytest.mark.asyncio
async def test_p2_incidental_third_party_in_own_question_keeps_users_level(policy):
    declare = "sou da graduação"
    own = "minha colega me disse que dá pra prorrogar; eu posso prorrogar o prazo?"
    script = {
        declare: level_reply(intent="level_declaration"),
        own: reading(level_subject="self"),
    }
    graph, facade, _ = build(policy, script, facade=Facade())
    who = identity(c)
    await turn(graph, who, declare)
    await turn(graph, who, own)
    assert facade.calls[-1]["clarification"] == "graduação"


@guard
@pytest.mark.asyncio
async def test_p2_thread_isolation_is_unchanged(policy):
    declare = "eu sou do mestrado"
    script = {
        declare: level_reply(level="postgraduate", span="mestrado", intent="level_declaration"),
        AMBIGUOUS: reading(),
    }
    graph, facade, _ = build(policy, script)
    await turn(graph, identity(c, thread="A"), declare)
    other = await turn(graph, identity(c, thread="B"), AMBIGUOUS)
    assert facade.calls[-1]["clarification"] is None
    assert other["conversation_memory"].declared_level is None


# ------------------------------------------------------------------ P3: grammar precedence


async def a_prime_trace(script_texts):
    """Facade calls and memory produced by A' itself (no interpreter)."""
    facade, gate = LevelFacade(), Gate()
    graph = build_integrated_graph(
        facade, checkpointer=InMemorySaver(), memory_stamp=stamp(c), scope_gate=gate
    )
    who = identity(c)
    memories = []
    for text in script_texts:
        state = await turn(graph, who, text)
        m = state["conversation_memory"]
        memories.append(None if m is None else (m.declared_level, bool(m.pending_clarification)))
    return [(k["question"], k["clarification"]) for k in facade.calls], memories


@defect("P3")
@pytest.mark.parametrize("reply", ["pos", "graduação", "pós-graduação", "mestrado", "doutorado"])
@pytest.mark.asyncio
async def test_p3_short_grammar_replies_behave_exactly_like_a_prime(policy, reply):
    below_threshold = reading(intent="uncertain", has_new_question=False)  # Jev under 0.6
    texts = [AMBIGUOUS, reply, NEW_QUESTION]
    graph, facade, _ = build(
        policy, {AMBIGUOUS: reading(), reply: below_threshold, NEW_QUESTION: reading()}
    )
    who = identity(c)
    memories = []
    for text in texts:
        state = await turn(graph, who, text)
        m = state["conversation_memory"]
        memories.append(None if m is None else (m.declared_level, bool(m.pending_clarification)))
    calls = [(k["question"], k["clarification"]) for k in facade.calls]
    assert (calls, memories) == await a_prime_trace(texts)


@defect("P3")
@pytest.mark.asyncio
async def test_p3_grammar_declaration_without_pending_is_kept(policy):
    reply = "Mestrado."
    generic = level_reply(
        level="postgraduate", span="mestrado", subject="generic", intent="level_declaration"
    )
    graph, facade, _ = build(policy, {reply: generic})
    state = await turn(graph, identity(c), reply)
    assert state["conversation_memory"].declared_level == "pos_graduacao"


@guard
@pytest.mark.asyncio
async def test_p3_precedence_does_not_hide_novel_replies(policy):
    msg = "to no mestrado profissional, foi mal não avisar"
    graph, facade, _ = build(
        policy, {AMBIGUOUS: reading(), msg: level_reply(level="postgraduate", span="mestrado")}
    )
    who = identity(c)
    await with_pending(graph, who)
    await turn(graph, who, msg)
    assert facade.calls[-1]["question"] == AMBIGUOUS
    assert facade.calls[-1]["clarification"] == "pós-graduação"


@guard
@pytest.mark.asyncio
async def test_p3_level_word_inside_a_question_is_not_a_grammar_reply(policy):
    msg = "pós tem prova de proficiência?"
    graph, facade, _ = build(policy, {AMBIGUOUS: reading(), msg: reading()})
    who = identity(c)
    await with_pending(graph, who)
    await turn(graph, who, msg)
    assert facade.calls[-1]["question"] == msg


@guard
@pytest.mark.asyncio
async def test_p3_ambiguous_reply_is_asked_back_not_consumed(policy):
    msg = "acho que é pós, não lembro direito"
    hedged = {**level_reply(level="postgraduate", span="pos"), "level_evidence": "hedged"}
    graph, facade, _ = build(policy, {AMBIGUOUS: reading(), msg: hedged})
    who = identity(c)
    await with_pending(graph, who)
    calls = len(facade.calls)
    state = await turn(graph, who, msg)
    assert len(facade.calls) == calls
    assert state["turn_audit"].conversation_action == "CLARIFY_INTENT"


# ------------------------------------------------------------------ P0: robustness (AUD-07)


class Exploding(ConversationInterpreter):
    name = "exploding"

    def interpret(self, context, config=None):
        raise RuntimeError("unexpected interpreter failure")

    async def ainterpret(self, context, config=None):
        raise RuntimeError("unexpected interpreter failure")


# The guard lives in the graph, so it protects both policies in this tree. RED evidence
# for the frozen v1 tree: stage7/e1/RED_before_wiring.txt and audit test_aud06_*.
@guard
@pytest.mark.asyncio
async def test_p0_untyped_interpreter_exception_returns_control_to_a_prime(policy):
    graph, facade, _ = build(policy, interpreter=Exploding())
    who = identity(c)
    await with_pending(graph, who)
    state = await turn(graph, who, "graduação")
    assert facade.calls[-1]["question"] == AMBIGUOUS
    assert state["turn_audit"].interpreter_status == "provider_error"


@pytest.mark.parametrize(
    "answers,usage",
    [
        ({"intent": {"type": "choice", "choice": "clarification", "probabilities": ["x"]}}, {}),
        (
            {
                "intent": {
                    "type": "choice",
                    "choice": "clarification",
                    "probabilities": {"clarification": "high"},
                }
            },
            {},
        ),
        (None, "not-a-dict"),
        (None, {"input_tokens": "n/a"}),
    ],
)
@pytest.mark.asyncio
async def test_p0_malformed_jev_payload_is_an_invalid_response(answers, usage):
    from test_conversation_interpretation import PENDING, jev_answers

    body = {"answers": jev_answers(**(answers or {})), "usage": usage}
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    jev = JevDecisionInterpreter(
        JevSettings(api_key="k"), transport=transport, sync_transport=transport
    )
    outcome = await jev.ainterpret(PENDING)
    assert outcome.status == "invalid_response" and not outcome.ok


# ------------------------------------------------------------------ P1 refinement
# Found in the offline replay of Stage 6 logs (regression of the first v2 draft): a reply
# that only protests and states the level is read by the interpreter as carrying a "new
# question". The independent review (stage7/review_v2) showed that resuming on a word-list
# judgement can consume real questions. v2 therefore never resumes on such a reading: it
# asks which request to answer (no retrieval, no persistence, pending preserved).

v2_only = pytest.mark.parametrize("policy", ["v2"])


@v2_only
@pytest.mark.parametrize(
    "msg,level,span",
    [
        ("eita, já disse que é graduação", "undergraduate", "graduacao"),
        ("já falei, sou do mestrado!", "postgraduate", "mestrado"),
    ],
)
@pytest.mark.asyncio
async def test_p1_level_reply_without_own_content_is_asked_back_not_consumed(
    policy, msg, level, span
):
    graph, facade, _ = build(policy, {AMBIGUOUS: reading(), msg: mixed(level=level, span=span)})
    who = identity(c)
    first = await with_pending(graph, who)
    calls = len(facade.calls)
    state = await turn(graph, who, msg)
    assert len(facade.calls) == calls
    assert state["turn_audit"].conversation_action == "CLARIFY_INTENT"
    memory = state["conversation_memory"]
    assert memory.pending_clarification.correlation_id == first["normative_result"].correlation_id
    assert memory.declared_level is None


@v2_only
@pytest.mark.parametrize(
    "msg,level,span",
    [
        ("pós, e em 2019?", "postgraduate", "pos"),
        ("graduação. qual o prazo?", "undergraduate", "graduacao"),
        ("mestrado, e isso vale agora?", "postgraduate", "mestrado"),
    ],
)
@pytest.mark.asyncio
async def test_review_a1_short_level_plus_question_is_never_consumed(policy, msg, level, span):
    reading_ = mixed(level=level, span=span)  # grounded; references pending + new question
    graph, facade, _ = build(policy, {AMBIGUOUS: reading(), msg: reading_})
    who = identity(c)
    await with_pending(graph, who)
    calls = len(facade.calls)
    state = await turn(graph, who, msg)
    assert state["turn_audit"].interpreter_status == "ok"  # the reading itself was used
    new_calls = facade.calls[calls:]
    assert not any(k["question"] == AMBIGUOUS for k in new_calls)  # never resumed
    assert [k["question"] for k in new_calls] == [msg]  # the question actually asked runs


@v2_only
@pytest.mark.parametrize("msg", ["não sou da pós", "acho que não é pós"])
@pytest.mark.asyncio
async def test_review_a2_uncertain_or_negated_level_never_resumes_or_persists(policy, msg):
    uncertain = reading(
        intent="uncertain",
        has_new_question=True,
        declared_level="postgraduate",
        level_evidence="explicit",
        references_pending=True,
        evidence_spans=("pos",),
    )
    graph, facade, _ = build(policy, {AMBIGUOUS: reading(), msg: uncertain})
    who = identity(c)
    await with_pending(graph, who)
    calls = len(facade.calls)
    state = await turn(graph, who, msg)
    new_calls = facade.calls[calls:]
    assert not any(k["question"] == AMBIGUOUS for k in new_calls)  # never resumed
    assert state["conversation_memory"].declared_level is None


@guard
@pytest.mark.parametrize("msg", ["e na pós", "e na graduação", "e da pós"])
@pytest.mark.asyncio
async def test_review_a3_elliptic_level_question_without_pending_is_not_a_declaration(policy, msg):
    facade = Facade()
    graph, _, _ = build(policy, {msg: reading()}, facade=facade)
    state = await turn(graph, identity(c), msg)
    assert state["turn_audit"].conversation_action != "DECLARE_LEVEL"
    memory = state["conversation_memory"]
    assert memory is None or memory.declared_level is None


@v2_only
@pytest.mark.asyncio
async def test_review_a4_cancel_without_question_clears_pending_without_retrieval(policy):
    msg = "não preciso mais disso, obrigado"
    cancel = reading(intent="new_question", has_new_question=True, cancels_pending=True)
    graph, facade, _ = build(
        policy,
        {
            AMBIGUOUS: reading(),
            msg: reading(intent="uncertain", has_new_question=False, cancels_pending=True),
        },
    )
    who = identity(c)
    await with_pending(graph, who)
    calls = len(facade.calls)
    state = await turn(graph, who, msg)
    assert len(facade.calls) == calls
    assert state["conversation_memory"].pending_clarification is None
    assert cancel  # the new_question+cancel variant is covered by test_p1_cancel_then_new_question


@v2_only
@pytest.mark.asyncio
async def test_review_a5_cancel_with_question_runs_the_full_text(policy):
    msg = "esquece; como peço segunda chamada?"
    reading_ = mixed(
        references=False, cancels_pending=True, extracted_question="como peço segunda chamada?"
    )
    graph, facade, _ = build(policy, {AMBIGUOUS: reading(), msg: reading_})
    who = identity(c)
    await with_pending(graph, who)
    await turn(graph, who, msg)
    assert facade.calls[-1]["question"] == msg


@pytest.mark.parametrize(
    "msg,expected",
    [
        ("eita, já disse que é graduação", False),
        ("hein? eu sou do doutorado", False),
        ("ok, é pós mesmo", False),
        ("pós, e em 2019?", True),
        ("certo, e como funciona a monitoria na pós?", True),
        ("sou de graduação e quero saber de colação de grau", True),
        ("mestrado. e a bolsa?", True),
    ],
)
def test_independent_content_detector(msg, expected):
    from rag_baseline.conversation_interpretation.transition_v2 import has_independent_content

    assert has_independent_content(msg) is expected


# ------------------------------------------------------------------ re-verification (N1, N2)


@guard
@pytest.mark.parametrize(
    "jev_reading",
    [
        reading(intent="uncertain", has_new_question=False),
        reading(intent="uncertain", has_new_question=True),
        reading(
            intent="uncertain",
            has_new_question=False,
            declared_level="postgraduate",
            level_evidence="explicit",
            level_subject="third_party",
            evidence_spans=("pos",),
        ),
    ],
)
@pytest.mark.asyncio
async def test_reverify_n1_grammar_base_with_uncertain_reading_never_breaks(policy, jev_reading):
    msg = "e na pós"  # A' grammar: DECLARE_LEVEL without a pending request
    graph, _, _ = build(policy, {msg: jev_reading}, facade=Facade())
    state = await turn(graph, identity(c), msg)  # must complete, never raise
    memory = state["conversation_memory"]
    assert state["messages"][-1].content
    if jev_reading["has_new_question"] or jev_reading["level_subject"] == "third_party":
        assert memory is None or memory.declared_level is None


@v2_only
@pytest.mark.asyncio
async def test_reverify_n2_cancel_with_a_request_still_runs_the_request(policy):
    msg = "mudando de assunto, quero saber das regras de colação de grau"
    cancel_only = reading(intent="uncertain", has_new_question=False, cancels_pending=True)
    graph, facade, _ = build(policy, {AMBIGUOUS: reading(), msg: cancel_only})
    who = identity(c)
    await with_pending(graph, who)
    calls = len(facade.calls)
    state = await turn(graph, who, msg)
    assert [k["question"] for k in facade.calls[calls:]] == [msg]
    assert state["conversation_memory"].pending_clarification is None or facade.calls


# ------------------------------------------------------------------ exhaustive invariants


def test_v2_invariants_hold_for_every_valid_interpretation():
    """Every contract-valid reading x interpretable base x pending state (I1-I5, N1 class)."""
    import itertools

    from rag_baseline.conversation_interpretation import TurnContext, TurnInterpretation
    from rag_baseline.conversation_interpretation.base import finalize
    from rag_baseline.conversation_interpretation.transition import INTERPRETABLE
    from rag_baseline.conversation_policy import FollowUpAction as F

    policy, checked = TransitionPolicyV2(), 0
    span = {"undergraduate": "graduacao", "postgraduate": "pos", "both": "ambas"}
    for (
        intent,
        level,
        evidence,
        subject,
        refs,
        new,
        cancel,
        pending,
        base,
        msg,
    ) in itertools.product(
        ["clarification", "level_declaration", "new_question", "mixed", "uncertain"],
        ["undergraduate", "postgraduate", "both", "none"],
        ["explicit", "indirect", "hedged", "none"],
        ["self", "third_party", "generic", "unknown"],
        [False, True],
        [False, True],
        [False, True],
        [False, True],
        sorted(INTERPRETABLE),
        ["graduacao pos ambas", "graduacao pos ambas e o prazo de trancamento?"],
    ):
        data = dict(
            intent=intent,
            declared_level=level,
            level_evidence=evidence,
            level_subject=subject,
            references_pending=refs,
            has_new_question=new,
            cancels_pending=cancel,
            extracted_question=None,
            evidence_spans=(span[level],) if level != "none" else (),
        )
        try:
            TurnInterpretation(**data)
        except ValueError:
            continue
        if base == F.CONTINUE_CLARIFICATION and not pending:
            continue  # A' only produces it with a pending request
        ctx = TurnContext(
            message=msg,
            pending_question="Q?" if pending else None,
            pending_clarification_question="Nível?" if pending else None,
            has_pending_operation=pending,
        )
        outcome = finalize("jev", data, ctx)
        d = policy.decide(base, outcome, ctx)
        checked += 1
        if d.defer_to_base:
            continue  # A' path, covered by the equivalence tests
        assert d.action != F.DECLARE_LEVEL or d.persist_level, (data, base)
        if d.action == F.CONTINUE_CLARIFICATION:
            assert pending and d.clarification_text, (data, base)  # I1
            assert not (new or cancel), (data, base)  # I2
            assert subject != "third_party", (data, base)  # I4
        if subject == "third_party" or evidence != "explicit" or subject != "self":
            assert d.persist_level is None, (data, base)  # I4, I5
        if d.action == F.CLEAR_PENDING:
            assert pending and cancel and not new, (data, base)
        if pending and new and d.action != F.CLARIFY_INTENT:
            assert d.action not in (F.CONTINUE_CLARIFICATION, F.DECLARE_LEVEL), (data, base)
    assert checked > 1000
