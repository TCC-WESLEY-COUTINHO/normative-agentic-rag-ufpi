"""E1 for the experimental conversation interpreters: no network, fakes only.

Contracts, provider adapters, deterministic transitions and the LangGraph integration.
A scripted interpreter stands in for any model: the graph must behave the same for any
implementation of the contract, and must never trust it beyond the policy invariants.
"""

import ast
import json
from pathlib import Path

import httpx
import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver
from test_conversation_memory_followups import Facade, identity, stamp, turn

from rag_baseline import conversation_graph as c
from rag_baseline.agent_graph import build_integrated_graph
from rag_baseline.conversation_interpretation import (
    ConversationTransitionPolicy,
    InterpreterConfig,
    TurnContext,
    TurnInterpretation,
    build_conversation_interpreter,
)
from rag_baseline.conversation_interpretation.base import ConversationInterpreter, finalize
from rag_baseline.conversation_interpretation.contracts import (
    InterpretationOutcome,
    grounding_violations,
    lexical_level_spans,
)
from rag_baseline.conversation_interpretation.hybrid import HybridInterpreter
from rag_baseline.conversation_interpretation.jev import JevDecisionInterpreter, JevSettings
from rag_baseline.conversation_interpretation.rules import RuleBasedInterpreter
from rag_baseline.conversation_interpretation.structured_llm import (
    SYSTEM_PROMPT,
    StructuredLLMInterpreter,
    TurnReading,
)
from rag_baseline.conversation_policy import FollowUpAction
from rag_baseline.scope_gate import ScopeGateResult

SRC = Path(__file__).resolve().parents[2] / "src" / "rag_baseline"
AMBIGUOUS = "Quanto tempo tenho para terminar o curso? Dá para pedir mais prazo?"
NEW_QUESTION = "Quais documentos são exigidos para matrícula?"


def reading(**changes):
    base = dict(
        intent="new_question",
        declared_level="none",
        level_evidence="none",
        level_subject="unknown",
        references_pending=False,
        has_new_question=True,
        cancels_pending=False,
        extracted_question=None,
        evidence_spans=(),
    )
    return {**base, **changes}


def level_reply(level="undergraduate", span="graduação", subject="self", intent="clarification"):
    return reading(
        intent=intent,
        declared_level=level,
        level_evidence="explicit",
        level_subject=subject,
        references_pending=intent == "clarification",
        has_new_question=False,
        evidence_spans=(span,),
    )


class ScriptedInterpreter(ConversationInterpreter):
    """Returns a fixed reading per message; records every call."""

    name = "scripted"

    def __init__(self, script, status="ok"):
        self.script, self.status, self.calls = script, status, []

    def interpret(self, context, config=None):
        self.calls.append(context)
        if self.status != "ok":
            return InterpretationOutcome(self.name, self.status, error_type="Fake", calls=1)
        return finalize(self.name, self.script[context.message], context, calls=1)

    async def ainterpret(self, context, config=None):
        return self.interpret(context, config)


class Gate:
    def __init__(self):
        self.questions = []

    async def classify(self, question):
        self.questions.append(question)
        return ScopeGateResult("IN_SCOPE_NORMATIVE", "classified", 0, 0.0)


class LevelFacade(Facade):
    """Asks for the level until a clarification arrives (like the real core)."""

    require_level = True

    async def query(self, **kwargs):
        if self.require_level:
            self.status = "ANSWER" if kwargs["clarification"] else "CLARIFICATION"
        return await super().query(**kwargs)


def graph_with(interpreter, facade=None):
    facade, gate = facade or LevelFacade(), Gate()
    graph = build_integrated_graph(
        facade,
        checkpointer=InMemorySaver(),
        memory_stamp=stamp(c),
        scope_gate=gate,
        interpreter=interpreter,
    )
    return graph, facade, gate


# --------------------------------------------------------------------------- contracts


@pytest.mark.parametrize(
    "changes,problem",
    [
        (dict(intent="clarification", has_new_question=False), "clarification_without_level"),
        (dict(intent="new_question", has_new_question=False), "new_question_without_question"),
        (dict(intent="mixed"), "mixed_without_two_intents"),
        (dict(declared_level="postgraduate"), "level_without_evidence_kind"),
        (
            dict(intent="uncertain", has_new_question=False, extracted_question="x"),
            "extracted_question_without_question",
        ),
    ],
)
def test_contradictory_interpretations_are_rejected_not_repaired(changes, problem):
    context = TurnContext(message="graduação")
    outcome = finalize("m", reading(**changes), context)
    assert outcome.status == "inconsistent" and problem in outcome.detail
    assert outcome.interpretation is None


def test_extracted_question_and_spans_must_come_from_the_message():
    message = "graduacao. e o jubilamento?"
    added = TurnInterpretation(
        **reading(intent="new_question", extracted_question="Como funciona o jubilamento em 2024?")
    )
    assert "extracted_question_adds_words" in grounding_violations(added, message)
    copied = TurnInterpretation(**reading(extracted_question="e o jubilamento?"))
    assert grounding_violations(copied, message) == []
    span = TurnInterpretation(**level_reply(span="mestrado"))
    assert "evidence_span_not_in_message" in grounding_violations(span, message)
    outcome = finalize(
        "m", reading(extracted_question="qual o prazo do mestrado?"), TurnContext(message=message)
    )
    assert outcome.status == "ungrounded" and not outcome.ok


def test_turn_context_requires_coherent_pending_state():
    with pytest.raises(ValueError):
        TurnContext(message="x", has_pending_operation=True)
    with pytest.raises(ValueError):
        TurnContext(message="x", pending_question="q")
    with pytest.raises(ValueError):
        TurnContext(message="x", pending_clarification_question="Graduação ou pós?")


def test_lexical_level_spans_locate_levels_only():
    assert lexical_level_spans("Pos graduação, doutorado em educação", "postgraduate") == (
        "pos graduacao",
        "doutorado",
    )
    assert lexical_level_spans("faço licenciatura em física", "undergraduate") == ("licenciatura",)
    assert lexical_level_spans("as duas, quero comparar", "both") == ("as duas",)
    assert lexical_level_spans("estou no quinto período", "undergraduate") == ()


# --------------------------------------------------------------------------- Jev adapter


def jev_answers(**overrides):
    answers = {
        "intent": {
            "type": "choice",
            "choice": "clarification",
            "confidence": 0.9,
            "probabilities": {"clarification": 0.9, "new_question": 0.1},
        },
        "declared_level": {
            "type": "choice",
            "choice": "undergraduate",
            "confidence": 0.95,
            "probabilities": {"undergraduate": 0.95},
        },
        "level_evidence": {
            "type": "choice",
            "choice": "explicit",
            "confidence": 0.9,
            "probabilities": {"explicit": 0.9},
        },
        "level_subject": {
            "type": "choice",
            "choice": "self",
            "confidence": 0.8,
            "probabilities": {"self": 0.8},
        },
        "references_pending": {"type": "noul", "noul": 0.93},
        "has_new_question": {"type": "noul", "noul": 0.04},
        "cancels_pending": {"type": "noul", "noul": 0.02},
    }
    answers.update(overrides)
    return answers


def jev_with(handler):
    seen = []

    def wrapped(request):
        seen.append(request)
        return handler(request)

    transport = httpx.MockTransport(wrapped)
    interpreter = JevDecisionInterpreter(
        JevSettings(api_key="test-key"), transport=transport, sync_transport=transport
    )
    return interpreter, seen


PENDING = TurnContext(
    message="graduação, curso de engenharia civil",
    pending_question=AMBIGUOUS,
    pending_clarification_question="Graduação ou pós?",
    has_pending_operation=True,
)


@pytest.mark.asyncio
async def test_jev_request_shape_and_typed_mapping():
    body = {
        "model": "typesafe/jev-1.14",
        "answers": jev_answers(),
        "usage": {"input_tokens": 700, "output_tokens": 0, "cost": 0.00003},
    }
    interpreter, seen = jev_with(lambda r: httpx.Response(200, json=body))
    outcome = await interpreter.ainterpret(PENDING)
    sent = json.loads(seen[0].content)
    assert seen[0].url == "https://openrouter.ai/api/alpha/decisions"
    assert seen[0].headers["Authorization"] == "Bearer test-key"
    assert set(sent) == {"model", "state", "questions"}
    assert json.loads(sent["state"])["user_message"] == PENDING.message
    assert {q["type"] for q in sent["questions"].values()} == {"choice", "noul"}
    assert outcome.ok and outcome.status == "ok"
    i = outcome.interpretation
    assert (i.intent, i.declared_level, i.level_subject) == (
        "clarification",
        "undergraduate",
        "self",
    )
    assert i.extracted_question is None  # Jev never writes free text
    assert i.evidence_spans == ("graduacao",)
    assert outcome.cost_usd == 0.00003 and outcome.input_tokens == 700
    assert outcome.method == "decisions_api" and outcome.probabilities["references_pending"] == 0.93
    sync = interpreter.interpret(PENDING)
    assert sync.interpretation == i


@pytest.mark.asyncio
async def test_jev_low_confidence_intent_becomes_uncertain_and_is_recorded():
    answers = jev_answers(
        intent={
            "type": "choice",
            "choice": "clarification",
            "confidence": 0.41,
            "probabilities": {"clarification": 0.41},
        }
    )
    interpreter, _ = jev_with(lambda r: httpx.Response(200, json={"answers": answers}))
    outcome = await interpreter.ainterpret(PENDING)
    assert outcome.ok and outcome.interpretation.intent == "uncertain"
    assert "intent_below_threshold" in outcome.adjustments


@pytest.mark.parametrize(
    "response,status",
    [
        (httpx.Response(500, json={"error": {"code": 500}}), "provider_error"),
        (httpx.Response(200, content=b"not json"), "invalid_response"),
        (
            httpx.Response(200, json={"answers": jev_answers(intent={"type": "refusal"})}),
            "invalid_response",
        ),
        (
            httpx.Response(
                200,
                json={
                    "answers": jev_answers(
                        intent={"type": "choice", "choice": "invented", "confidence": 1.0}
                    )
                },
            ),
            "invalid_response",
        ),
        (
            httpx.Response(
                200,
                json={
                    "answers": jev_answers(
                        intent={"type": "choice", "choice": "new_question", "confidence": 0.9}
                    )
                },
            ),
            "inconsistent",
        ),
    ],
)
@pytest.mark.asyncio
async def test_jev_failures_are_typed_never_guessed(response, status):
    interpreter, _ = jev_with(lambda r: response)
    outcome = await interpreter.ainterpret(PENDING)
    assert outcome.status == status and not outcome.ok


@pytest.mark.asyncio
async def test_jev_timeout_is_recorded_as_timeout():
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    interpreter, _ = jev_with(slow)
    assert (await interpreter.ainterpret(PENDING)).status == "timeout"


@pytest.mark.asyncio
async def test_jev_without_pending_never_claims_to_answer_one():
    interpreter, _ = jev_with(
        lambda r: httpx.Response(
            200,
            json={
                "answers": jev_answers(
                    intent={"type": "choice", "choice": "level_declaration", "confidence": 0.9}
                )
            },
        )
    )
    outcome = await interpreter.ainterpret(TurnContext(message="sou da graduação"))
    assert outcome.interpretation.references_pending is False
    assert "references_pending_without_pending" in outcome.adjustments


def test_jev_is_a_runnable_not_a_chat_model():
    from langchain_core.language_models import BaseChatModel

    interpreter, _ = jev_with(lambda r: httpx.Response(500))
    assert not isinstance(interpreter, BaseChatModel)
    assert interpreter.as_runnable().name == "conversation_interpreter.jev"


# --------------------------------------------------------------------------- structured LLM


def structured_returning(parsed=None, error=None, raise_exc=None):
    raw = AIMessage(
        content="",
        usage_metadata={"input_tokens": 900, "output_tokens": 60, "total_tokens": 960},
        response_metadata={"token_usage": {"cost": 0.0001}, "model_name": "fake/model"},
    )

    def run(messages):
        run.calls.append(messages)
        if raise_exc:
            raise raise_exc
        return {"raw": raw, "parsed": parsed, "parsing_error": error}

    run.calls = []
    return RunnableLambda(run), run


MIXED = TurnContext(
    message="graduacao. e o jubilamento?",
    pending_question=AMBIGUOUS,
    pending_clarification_question="Graduação ou pós?",
    has_pending_operation=True,
)


@pytest.mark.asyncio
async def test_structured_llm_classifies_and_extracts_in_one_call():
    parsed = TurnReading(
        **{
            **reading(
                intent="mixed",
                declared_level="undergraduate",
                level_evidence="explicit",
                level_subject="unknown",
                references_pending=True,
                extracted_question="e o jubilamento?",
            ),
            "evidence_spans": ["graduacao"],
        }
    )
    runnable, run = structured_returning(parsed)
    interpreter = StructuredLLMInterpreter(
        structured=runnable, method="json_schema", model_name="m"
    )
    outcome = await interpreter.ainterpret(MIXED)
    assert outcome.ok and len(run.calls) == 1
    assert outcome.interpretation.extracted_question == "e o jubilamento?"
    assert (outcome.input_tokens, outcome.output_tokens, outcome.cost_usd) == (900, 60, 0.0001)
    system, human = run.calls[0]
    assert system.content == SYSTEM_PROMPT and "jubilamento" in human.content
    assert interpreter.interpret(MIXED).interpretation == outcome.interpretation


@pytest.mark.parametrize(
    "kwargs,status",
    [
        (dict(error=ValueError("bad json")), "invalid_response"),
        (dict(parsed=None), "invalid_response"),
        (dict(raise_exc=RuntimeError("502")), "provider_error"),
        (dict(raise_exc=TimeoutError()), "timeout"),
        (
            dict(
                parsed=TurnReading(
                    **{**reading(extracted_question="qual o prazo em 2024?"), "evidence_spans": []}
                )
            ),
            "ungrounded",
        ),
    ],
)
@pytest.mark.asyncio
async def test_structured_llm_failures_are_typed(kwargs, status):
    runnable, _ = structured_returning(**kwargs)
    outcome = await StructuredLLMInterpreter(structured=runnable).ainterpret(MIXED)
    assert outcome.status == status and not outcome.ok


@pytest.mark.parametrize("method", ["json_schema", "function_calling", "json_mode"])
def test_structured_llm_binds_a_real_base_chat_model_without_network(method, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("network used while building")

    monkeypatch.setattr(httpx.Client, "send", no_network)
    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)
    config = InterpreterConfig(
        mode="structured_llm",
        llm_method=method,
        provider={"order": ["nebius"], "allow_fallbacks": False},
    )
    interpreter = build_conversation_interpreter(config, api_key="test-key")
    assert interpreter.describe()["method"] == method
    assert "test-key" not in json.dumps(interpreter.describe())


# --------------------------------------------------------------------------- hybrid


class Counting(ScriptedInterpreter):
    def __init__(self, name, script, status="ok"):
        super().__init__(script, status)
        self.name = name


@pytest.mark.parametrize(
    "first,escalated",
    [
        (level_reply(), False),
        (reading(intent="uncertain", has_new_question=False), True),
        (
            reading(
                intent="mixed",
                declared_level="undergraduate",
                level_evidence="explicit",
                evidence_spans=("graduacao",),
            ),
            True,
        ),
    ],
)
@pytest.mark.asyncio
async def test_hybrid_escalates_only_mixed_or_uncertain(first, escalated):
    jev = Counting("jev", {MIXED.message: first})
    llm = Counting(
        "structured_llm", {MIXED.message: reading(extracted_question="e o jubilamento?")}
    )
    outcome = await HybridInterpreter(jev, llm).ainterpret(MIXED)
    assert len(jev.calls) == 1 and len(llm.calls) == int(escalated)
    assert outcome.interpreter == "hybrid" and outcome.calls == 1 + int(escalated)


@pytest.mark.asyncio
async def test_hybrid_never_falls_back_silently_on_first_model_failure():
    jev = Counting("jev", {}, status="provider_error")
    llm = Counting("structured_llm", {})
    outcome = await HybridInterpreter(jev, llm).ainterpret(MIXED)
    assert outcome.status == "provider_error" and not llm.calls


# --------------------------------------------------------------------------- transition policy


def decide(base, interpretation, pending=True, status="ok", message=None):
    message = message or PENDING.message
    context = (
        PENDING.model_copy(update={"message": message}) if pending else TurnContext(message=message)
    )
    outcome = (
        finalize("m", interpretation, context)
        if status == "ok"
        else InterpretationOutcome("m", status)
    )
    return ConversationTransitionPolicy().decide(base, outcome, context)


N = FollowUpAction.NORMATIVE_RAG


def test_no_resumption_without_pending():
    d = decide(N, level_reply(), pending=False)
    assert d.action == FollowUpAction.DECLARE_LEVEL and d.persist_level == "graduacao"
    d = decide(N, level_reply(subject="unknown"), pending=False)
    assert d.action == FollowUpAction.CLARIFY_INTENT and d.persist_level is None


def test_third_party_level_resumes_only_when_answering_but_is_never_stored():
    message = "minha irmã faz mestrado"
    d = decide(
        N,
        level_reply(level="postgraduate", span="mestrado", subject="third_party"),
        message=message,
    )
    assert d.action == FollowUpAction.CONTINUE_CLARIFICATION and d.persist_level is None
    d = decide(
        N,
        level_reply(
            level="postgraduate", span="mestrado", subject="third_party", intent="level_declaration"
        ),
        pending=False,
        message=message,
    )
    assert d.persist_level is None and d.action == FollowUpAction.CLARIFY_INTENT


def test_grammar_reply_is_passed_unchanged_other_replies_canonical():
    d = decide(N, level_reply(span="graduacao"), message="Sou de graduação")
    assert d.clarification_text == "Sou de graduação"
    d = decide(N, level_reply())
    assert d.clarification_text == "graduação"  # "graduação, curso de engenharia civil"


def test_new_question_is_never_consumed_as_clarification():
    d = decide(N, reading())
    assert d.action == N and d.clarification_text is None and d.persist_level is None


def test_hedged_level_is_asked_back_and_indirect_level_is_never_stored():
    hedged = {**level_reply(), "level_evidence": "hedged"}
    assert decide(N, hedged).action == FollowUpAction.CLARIFY_INTENT
    indirect = {**level_reply(), "level_evidence": "indirect"}
    d = decide(N, indirect)
    assert d.action == FollowUpAction.CONTINUE_CLARIFICATION and d.persist_level is None


def test_comparison_resumes_with_both_and_is_never_stored():
    both = level_reply(level="both", span="as duas", subject="generic")
    d = decide(N, both, message="as duas, quero comparar")
    assert d.clarification_text == "ambas" and d.persist_level is None


def test_mixed_reply_answers_pending_and_records_extra_question_without_substitution():
    mixed = reading(
        intent="mixed",
        declared_level="undergraduate",
        level_evidence="explicit",
        references_pending=True,
        extracted_question="curso de engenharia civil",
        evidence_spans=("graduação",),
    )
    d = decide(N, mixed)
    assert d.action == FollowUpAction.CONTINUE_CLARIFICATION
    assert d.clarification_text == "graduação"
    assert d.deferred_question == "curso de engenharia civil" and d.question_override is None


def test_mixed_cancel_runs_the_extracted_question_and_clears_pending():
    mixed = reading(
        intent="mixed", cancels_pending=True, extracted_question="curso de engenharia civil"
    )
    d = decide(N, mixed)
    assert d.action == N and d.clear_pending and d.question_override == "curso de engenharia civil"


@pytest.mark.parametrize(
    "status", ["provider_error", "timeout", "invalid_response", "inconsistent", "ungrounded"]
)
def test_technical_failure_keeps_the_unchanged_base_decision(status):
    for base in (N, FollowUpAction.CONTINUE_CLARIFICATION, FollowUpAction.DECLARE_LEVEL):
        d = decide(base, None, status=status)
        assert d.action == base and d.reason == f"interpreter_{status}"


@pytest.mark.parametrize(
    "base",
    [
        FollowUpAction.SAFE_DIRECT,
        FollowUpAction.CLEAR_PENDING,
        FollowUpAction.CALCULATOR,
        FollowUpAction.GROUNDED_TRANSFORM,
        FollowUpAction.CONTEXTUAL_NORMATIVE_RAG,
    ],
)
def test_structural_decisions_are_never_reinterpreted(base):
    assert decide(base, level_reply()).action == base


def test_uncertain_reply_to_pending_is_asked_back():
    d = decide(N, reading(intent="uncertain", has_new_question=False))
    assert d.action == N  # no level, not grammar: keep A' (new operation)
    d = decide(
        FollowUpAction.CONTINUE_CLARIFICATION, reading(intent="uncertain", has_new_question=False)
    )
    assert d.action == FollowUpAction.CLARIFY_INTENT


# --------------------------------------------------------------------------- graph integration


@pytest.mark.asyncio
async def test_novel_clarification_resumes_same_operation_with_canonical_level():
    reply = "graduação, curso de engenharia civil"
    interpreter = ScriptedInterpreter({AMBIGUOUS: reading(), reply: level_reply()})
    graph, facade, gate = graph_with(interpreter)
    who = identity(c)
    first = await turn(graph, who, AMBIGUOUS)
    assert first["normative_result"].status == "CLARIFICATION"
    resumed = await turn(graph, who, reply)
    audit = resumed["turn_audit"]
    assert audit.conversation_action == "CONTINUE_CLARIFICATION"
    assert audit.base_conversation_action == "NORMATIVE_RAG"  # A' would have failed here
    assert audit.nodes_visited[:2] == ("conversation_entry", "conversation_interpretation")
    assert facade.calls[-1]["question"] == AMBIGUOUS
    assert facade.calls[-1]["clarification"] == "graduação"
    assert facade.calls[-1]["correlation_id"] == first["normative_result"].correlation_id
    memory = resumed["conversation_memory"]
    assert memory.declared_level == "graduacao"
    assert memory.declared_level_source == "confirmed_clarification"
    assert memory.pending_clarification is None and gate.questions[-1] == AMBIGUOUS


@pytest.mark.asyncio
async def test_new_question_during_pending_starts_new_operation():
    interpreter = ScriptedInterpreter({AMBIGUOUS: reading(), NEW_QUESTION: reading()})
    graph, facade, _ = graph_with(interpreter)
    who = identity(c)
    first = await turn(graph, who, AMBIGUOUS)
    state = await turn(graph, who, NEW_QUESTION)
    assert facade.calls[-1]["question"] == NEW_QUESTION
    assert facade.calls[-1]["correlation_id"] != first["normative_result"].correlation_id
    assert state["conversation_memory"].declared_level is None


@pytest.mark.asyncio
async def test_uncertain_reply_asks_back_and_keeps_pending_without_calls():
    reply = "acho que é pós, não sei"
    uncertain = {
        **level_reply(level="postgraduate", span="pos"),
        "intent": "uncertain",
        "level_evidence": "hedged",
        "references_pending": True,
    }
    graph, facade, gate = graph_with(ScriptedInterpreter({AMBIGUOUS: reading(), reply: uncertain}))
    who = identity(c)
    first = await turn(graph, who, AMBIGUOUS)
    calls = len(facade.calls)
    state = await turn(graph, who, reply)
    assert state["turn_audit"].conversation_action == "CLARIFY_INTENT"
    assert "Graduação ou pós?" in state["messages"][-1].content
    assert len(facade.calls) == calls and len(gate.questions) == 1
    pending = state["conversation_memory"].pending_clarification
    assert pending.correlation_id == first["normative_result"].correlation_id


@pytest.mark.asyncio
async def test_cancel_and_new_question_runs_extracted_question_only():
    message = "Esquece isso. Como funciona o reingresso na graduação?"
    mixed = reading(
        intent="mixed",
        cancels_pending=True,
        extracted_question="Como funciona o reingresso na graduação?",
    )
    graph, facade, gate = graph_with(ScriptedInterpreter({AMBIGUOUS: reading(), message: mixed}))
    who = identity(c)
    await turn(graph, who, AMBIGUOUS)
    facade.require_level, facade.status = False, "ANSWER"
    state = await turn(graph, who, message)
    assert facade.calls[-1]["question"] == "Como funciona o reingresso na graduação?"
    assert gate.questions[-1] == "Como funciona o reingresso na graduação?"
    assert state["turn_audit"].question_override == "Como funciona o reingresso na graduação?"
    assert state["conversation_memory"].pending_clarification is None


@pytest.mark.asyncio
async def test_self_declaration_persists_over_turns_and_explicit_change_replaces_it():
    declare = "Oi, sou aluna do mestrado em Letras"
    change = "na verdade agora sou da graduação"
    script = {
        declare: level_reply(level="postgraduate", span="mestrado", intent="level_declaration"),
        change: level_reply(level="undergraduate", span="graduacao", intent="level_declaration"),
        AMBIGUOUS: reading(),
        NEW_QUESTION: reading(),
    }
    graph, facade, _ = graph_with(ScriptedInterpreter(script))
    who = identity(c)
    state = await turn(graph, who, declare)
    assert not facade.calls and state["conversation_memory"].declared_level == "pos_graduacao"
    await turn(graph, who, AMBIGUOUS)
    assert facade.calls[-1]["clarification"] == "pós-graduação"
    await turn(graph, who, NEW_QUESTION)
    assert facade.calls[-1]["clarification"] == "pós-graduação"
    changed = await turn(graph, who, change)
    assert changed["conversation_memory"].declared_level == "graduacao"
    await turn(graph, who, AMBIGUOUS)
    assert facade.calls[-1]["clarification"] == "graduação"


@pytest.mark.asyncio
async def test_mixed_self_declaration_with_question_persists_and_answers_first_turn():
    message = "Faço graduação em Direito. Como funciona o trancamento?"
    mixed = reading(
        intent="mixed",
        declared_level="undergraduate",
        level_evidence="explicit",
        level_subject="self",
        evidence_spans=("graduação",),
    )
    graph, facade, _ = graph_with(ScriptedInterpreter({message: mixed, AMBIGUOUS: reading()}))
    who = identity(c)
    state = await turn(graph, who, message)
    assert facade.calls[-1]["question"] == message  # no extraction: full text
    assert state["conversation_memory"].declared_level == "graduacao"
    assert state["conversation_memory"].declared_level_source == "explicit_declaration"
    assert state["turn_audit"].interpreted_level_persisted == "graduacao"
    await turn(graph, who, AMBIGUOUS)
    assert facade.calls[-1]["clarification"] == "graduação"


@pytest.mark.asyncio
async def test_third_party_declaration_never_persists():
    message = "Meu orientando faz doutorado e quer trancar."
    third = reading(
        intent="new_question",
        declared_level="postgraduate",
        level_evidence="explicit",
        level_subject="third_party",
        evidence_spans=("doutorado",),
    )
    graph, facade, _ = graph_with(ScriptedInterpreter({message: third, NEW_QUESTION: reading()}))
    who = identity(c)
    facade.require_level, facade.status = False, "ANSWER"
    state = await turn(graph, who, message)
    assert state["conversation_memory"].declared_level is None
    await turn(graph, who, NEW_QUESTION)
    assert facade.calls[-1]["clarification"] is None


@pytest.mark.asyncio
async def test_declared_level_stays_in_its_thread():
    declare = "Sou do mestrado em Economia."
    script = {
        declare: level_reply(level="postgraduate", span="mestrado", intent="level_declaration"),
        AMBIGUOUS: reading(),
    }
    interpreter = ScriptedInterpreter(script)
    graph, facade, _ = graph_with(interpreter)
    await turn(graph, identity(c, thread="A"), declare)
    other = await turn(graph, identity(c, thread="B"), AMBIGUOUS)
    assert facade.calls[-1]["clarification"] is None
    assert other["conversation_memory"].declared_level is None
    # Context handed to the interpreter in thread B carries nothing from thread A.
    assert interpreter.calls[-1].declared_level is None


@pytest.mark.asyncio
async def test_interpreter_failure_keeps_a_prime_behaviour_and_is_audited():
    reply = "graduação, curso de engenharia civil"
    graph, facade, _ = graph_with(ScriptedInterpreter({}, status="timeout"))
    who = identity(c)
    await turn(graph, who, AMBIGUOUS)
    state = await turn(graph, who, reply)
    assert state["turn_audit"].interpreter_status == "timeout"
    assert state["turn_audit"].transition_reason == "interpreter_timeout"
    assert state["turn_audit"].conversation_action == "NORMATIVE_RAG"
    assert facade.calls[-1]["question"] == reply  # same as A'


@pytest.mark.parametrize("text", ["Obrigado.", "Quem é você?", "Quanto é 12 * 3?", "cancelar"])
@pytest.mark.asyncio
async def test_structural_turns_do_not_call_the_interpreter(text):
    interpreter = ScriptedInterpreter({AMBIGUOUS: reading()})
    graph, _, _ = graph_with(interpreter)
    who = identity(c)
    await turn(graph, who, AMBIGUOUS)
    calls = len(interpreter.calls)
    state = await turn(graph, who, text)
    assert len(interpreter.calls) == calls
    assert state["turn_audit"].interpreter_status == "not_invoked"


R1R2_SCRIPT = [
    AMBIGUOUS,
    "Faço mestrado.",
    NEW_QUESTION,
    "Sou aluno de graduação.",
    AMBIGUOUS,
    "Como funciona o trancamento na pós?",
    "graduação",
    AMBIGUOUS,
    "ambas",
    "Obrigado.",
]


@pytest.mark.asyncio
async def test_rules_interpreter_reproduces_a_prime_exactly():
    """Same grammar through the new contract: identical facade calls and memory."""
    outcomes = []
    for interpreter in (None, RuleBasedInterpreter()):
        graph, facade, _ = graph_with(interpreter)
        who = identity(c)
        memories = []
        for text in R1R2_SCRIPT:
            state = await turn(graph, who, text)
            memory = state["conversation_memory"]
            memories.append(
                None
                if memory is None
                else (
                    memory.declared_level,
                    memory.declared_level_source,
                    bool(memory.pending_clarification),
                )
            )
        calls = [(k["question"], k["clarification"]) for k in facade.calls]
        outcomes.append((calls, memories))
    assert outcomes[0] == outcomes[1]


@pytest.mark.asyncio
async def test_same_contextualized_question_reaches_retrieval_unchanged():
    """With an identical question, the interpreter changes nothing downstream."""
    calls = []
    for interpreter in (None, ScriptedInterpreter({NEW_QUESTION: reading()})):
        graph, facade, gate = graph_with(interpreter, Facade())
        await turn(graph, identity(c), NEW_QUESTION)
        calls.append(
            (facade.calls[-1]["question"], facade.calls[-1]["clarification"], gate.questions)
        )
    assert calls[0] == calls[1]


@pytest.mark.asyncio
async def test_full_graph_with_structured_llm_over_fake_runnable_and_no_network(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("network")

    monkeypatch.setattr(httpx.Client, "send", no_network)
    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)
    reply = "pos graduacao, mestrado em quimica"
    answers = {
        AMBIGUOUS: TurnReading(**{**reading(), "evidence_spans": []}),
        reply: TurnReading(
            **{
                **level_reply(level="postgraduate", span="mestrado", subject="unknown"),
                "evidence_spans": ["pos graduacao", "mestrado"],
            }
        ),
    }
    seen = []

    def fake(messages):
        state = json.loads(messages[1].content)
        seen.append(state)
        return {
            "raw": AIMessage(content=""),
            "parsed": answers[state["user_message"]],
            "parsing_error": None,
        }

    interpreter = StructuredLLMInterpreter(structured=RunnableLambda(fake), model_name="fake")
    graph, facade, _ = graph_with(interpreter)
    who = identity(c)
    await turn(graph, who, AMBIGUOUS)
    state = await turn(graph, who, reply)
    assert facade.calls[-1]["clarification"] == "pós-graduação"
    assert state["conversation_memory"].declared_level == "pos_graduacao"
    assert seen[1]["pending_question"] == AMBIGUOUS and seen[0]["pending_question"] is None


# --------------------------------------------------------------------------- decoupling


PROVIDER_MODULES = {
    "httpx",
    "openai",
    "langchain_openai",
    "langchain_openrouter",
    "anthropic",
    "langchain_anthropic",
    "requests",
    "rag_baseline.openrouter",
}


def imported(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize(
    "module",
    [
        "conversation_graph.py",
        "conversation_policy.py",
        "conversation_interpretation/transition.py",
        "conversation_interpretation/contracts.py",
        "conversation_interpretation/structured_llm.py",
        "conversation_interpretation/hybrid.py",
        "conversation_interpretation/rules.py",
    ],
)
def test_business_modules_import_no_provider_sdk(module):
    found = {
        name
        for name in imported(SRC / module)
        if any(name == p or name.startswith(p + ".") for p in PROVIDER_MODULES)
    }
    assert not found


def test_provider_details_live_only_in_adapter_and_factory():
    assert "httpx" in imported(SRC / "conversation_interpretation/jev.py")
    factory = (SRC / "conversation_interpretation/factory.py").read_text(encoding="utf-8")
    assert "from langchain_openai import ChatOpenAI" in factory


def test_mode_none_builds_no_interpreter_and_a_prime_topology():
    assert build_conversation_interpreter(InterpreterConfig()) is None
    graph, _, _ = graph_with(None)
    assert "conversation_interpretation" not in graph.get_graph().nodes
    graph, _, _ = graph_with(RuleBasedInterpreter())
    assert "conversation_interpretation" in graph.get_graph().nodes


def test_interpreter_requires_persistent_conversation():
    with pytest.raises(ValueError):
        build_integrated_graph(Facade(), interpreter=RuleBasedInterpreter())


@pytest.mark.parametrize("status", ["inconsistent", "timeout", "provider_error"])
@pytest.mark.asyncio
async def test_failure_on_grammar_decisions_reproduces_a_prime(status):
    """Regression (P1, A2J G2-019): a failed interpretation must leave A' fully in charge."""
    for interpreter in (None, ScriptedInterpreter({}, status=status)):
        graph, facade, _ = graph_with(interpreter)
        who = identity(c)
        declared = await turn(graph, who, "Faço mestrado.")
        assert declared["conversation_memory"].declared_level == "pos_graduacao"
        facade.require_level, facade.status = True, "CLARIFICATION"
        await turn(graph, identity(c, thread="Y"), AMBIGUOUS)
        resumed = await turn(graph, identity(c, thread="Y"), "graduação")
        assert facade.calls[-1]["question"] == AMBIGUOUS
        assert facade.calls[-1]["clarification"] == "graduação"
        assert resumed["conversation_memory"].declared_level == "graduacao"
