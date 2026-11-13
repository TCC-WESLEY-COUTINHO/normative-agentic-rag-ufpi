"""Deterministic math, routing and checkpoint boundaries; no remote providers."""

import asyncio
import importlib
from decimal import Decimal, localcontext

import pytest
import test_conversation_memory_followups as memory
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import ValidationError

from rag_baseline.conversation_policy import ConversationFollowUpPolicy
from schema import ChatMessage
from service.normative_transport import project_integrated_state

conversation = memory.conversation


@pytest.fixture
def calc():
    name = "rag_baseline.calculator"
    if importlib.util.find_spec(name) is None:
        pytest.fail("Deterministic calculator is not implemented")
    return importlib.import_module(name)


def execute(calc, text):
    intent = calc.CalculatorIntentParser().parse(text)
    assert intent.is_calculator_intent
    return calc.build_calculator_tool().invoke({"request": intent.parsed_request})


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2+2", "4"),
        ("Quanto é 15 * 4?", "60"),
        ("Calcule 100 / 4.", "25"),
        ("2 * (3 + 4)", "14"),
        ("-5 + 2", "-3"),
        ("1.5 + 2.5", "4"),
        ("10 / 4", "2.5"),
        ("0.1 + 0.2", "0.3"),
        ("1 - -2", "3"),
        ("+5 / (-2)", "-2.5"),
        ("0 * -1", "0"),
        ("(20 - 4) / 2 * 3", "24"),
    ],
)
def test_arithmetic(calc, text, expected):
    result = execute(calc, text)
    assert result.status == "ANSWER" and result.operation_kind == "ARITHMETIC"
    assert result.content == expected and result.numeric_result == Decimal(expected)
    assert result.date_result is None and result.days_result is None
    assert ConversationFollowUpPolicy().decide(text).action == "CALCULATOR"


@pytest.mark.parametrize(
    "expression,code",
    [
        ("1/0", "division_by_zero"),
        ('__import__("os")', "invalid_expression"),
        ('open("x")', "invalid_expression"),
        ("2 ** 999999", "unsupported_operation"),
        ("foo + 1", "invalid_expression"),
        ("[1, 2]", "invalid_expression"),
        ("lambda: 1", "invalid_expression"),
        ('"string"', "invalid_expression"),
        ("1 << 100", "unsupported_operation"),
        ("sin(1)", "invalid_expression"),
        ("(1).__class__", "invalid_expression"),
        ("{'a': 1}", "invalid_expression"),
        ("[x for x in []]", "invalid_expression"),
        ("1e3", "invalid_expression"),
        ("1,5 + 2,5", "invalid_expression"),
        ("2//2", "unsupported_operation"),
        ("2%2", "unsupported_operation"),
        ("", "invalid_expression"),
        ("(2+3", "invalid_expression"),
        ("2 3", "invalid_expression"),
    ],
)
def test_forbidden_arithmetic_returns_safe_error(calc, expression, code):
    result = calc.build_calculator_tool().invoke(
        {"request": calc.ArithmeticRequest(expression=expression)}
    )
    assert result.status == "ERROR" and result.error_code == code
    assert result.content == result.safe_message
    assert result.numeric_result is None and result.date_result is None
    assert expression not in result.safe_message or not expression


@pytest.mark.parametrize(
    "expression",
    ["1" * 513, "1" * 25, "(" * 17 + "1" + ")" * 17, "+" * 130 + "1", "999999999999999999999999*2"],
)
def test_complexity_bounded(calc, expression):
    result = calc.build_calculator_tool().invoke(
        {"request": calc.ArithmeticRequest(expression=expression)}
    )
    assert result.status == "ERROR"
    assert result.error_code in {"input_too_large", "expression_too_complex", "numeric_limit"}


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Adicione 10 dias corridos a 05/11/2026.", "15/11/2026"),
        ("Some 10 dias corridos a 2026-11-05", "15/11/2026"),
        ("Subtraia 5 dias corridos de 05/11/2026", "31/10/2026"),
        ("1 dias depois de 28/02/2028", "29/02/2028"),
        ("1 dias depois de 28/02/2027", "01/03/2027"),
        ("5 dias antes de 05/11/2026", "31/10/2026"),
        ("Adicione 0 dias corridos a 05/11/2026", "05/11/2026"),
    ],
)
def test_date_offsets(calc, text, expected):
    result = execute(calc, text)
    assert result.status == "ANSWER" and result.operation_kind == "DATE_OFFSET"
    assert result.content == expected
    assert result.numeric_result is None


@pytest.mark.parametrize(
    "text,days",
    [
        ("Quantos dias existem entre 05/11/2026 e 15/11/2026?", 10),
        ("Quantos dias entre 15/11/2026 e 05/11/2026?", -10),
        ("Quantos dias entre 2026-11-05 e 05/11/2026?", 0),
    ],
)
def test_date_difference_is_signed_subtraction(calc, text, days):
    result = execute(calc, text)
    assert result.status == "ANSWER" and result.operation_kind == "DATE_DIFFERENCE"
    assert result.days_result == days
    assert result.content == f"Diferença entre as datas: {days} dias."


@pytest.mark.parametrize(
    "text,code",
    [
        ("10 dias a partir de 05/11/2026", "ambiguous_date_offset"),
        ("10 dias úteis depois de 05/11/2026", "unsupported_business_days"),
        ("10 dias depois de amanhã", "unsupported_relative_date"),
        ("Adicione 10 dias corridos a hoje", "unsupported_relative_date"),
        ("Adicione 1 dias corridos a 31/02/2026", "invalid_date"),
        ("Adicione 1 dias corridos a 31/12/9999", "invalid_date"),
        ("Adicione 999999999999 dias corridos a 05/11/2026", "numeric_limit"),
        ("Quantos dias entre 31/02/2026 e 05/11/2026?", "invalid_date"),
        ("Calcule 2+", "invalid_expression"),
    ],
)
def test_clear_but_unsupported_intents_stay_calculator(calc, text, code):
    intent = calc.CalculatorIntentParser().parse(text)
    assert intent.is_calculator_intent and not intent.normative_mix_detected
    assert ConversationFollowUpPolicy().decide(text).action == "CALCULATOR"
    result = execute(calc, text)
    assert result.status == "ERROR" and result.error_code == code


NORMATIVE = [
    "Qual o prazo do art. 53?",
    "O prazo é de 10 dias úteis?",
    "Se o art. 53 fala em 10 dias, qual é o último dia?",
    "Na graduação, se eu pedir dia 5, quando vence?",
    "Segundo a resolução 956/2025, são 10 dias?",
    "Se a Resolução 956/2025 dá 10 dias, qual a data?",
    "O art. 53 conta 10 dias a partir da ciência?",
    "Na graduação são 10 dias úteis?",
    "Segundo o art. 53, some o prazo até 20/11.",
    "O prazo da UFPI conta o primeiro dia?",
    "São dias úteis ou corridos?",
    "Calcule 2+2 conforme a norma.",
    "Calcule o prazo para recurso: 10 dias depois de 05/11/2026",
    "Adicione 10 dias corridos a 05/11/2026 para a matrícula",
    "2+2; conforme o regulamento",
    "E na pós, são 10 dias?",
]


@pytest.mark.parametrize("text", NORMATIVE)
def test_normative_queries_never_execute_partially(calc, text):
    intent = calc.CalculatorIntentParser().parse(text)
    assert not intent.is_calculator_intent and intent.parsed_request is None
    assert ConversationFollowUpPolicy().decide(text).action == "NORMATIVE_RAG"


@pytest.mark.parametrize(
    "text,action",
    [
        ("Obrigado", "SAFE_DIRECT"),
        ("cancelar", "CLEAR_PENDING"),
        ("2+2", "CALCULATOR"),
        ("graduação", "CONTINUE_CLARIFICATION"),
    ],
)
def test_pending_priority(text, action):
    assert ConversationFollowUpPolicy().decide(text, pending=True).action == action


@pytest.mark.parametrize(
    "text,action",
    [
        ("Resuma em 2 linhas", "GROUNDED_TRANSFORM"),
        ("Explique em 3 passos", "GROUNDED_TRANSFORM"),
        ("E na pós?", "CONTEXTUAL_NORMATIVE_RAG"),
        ("Obrigado, quanto é 2+2?", "NORMATIVE_RAG"),
        ("E vezes 3?", "NORMATIVE_RAG"),
    ],
)
def test_numbers_do_not_determine_intent(text, action):
    assert ConversationFollowUpPolicy().decide(text).action == action


def test_decimal_context_and_repeatability(calc):
    with localcontext() as context:
        context.prec = 3
        results = [execute(calc, "1/3").model_dump_json() for _ in range(5)]
    assert len(set(results)) == 1
    assert execute(calc, "1/3").content == "0.3333333333333333333333333333"


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["2+2", "1/0", "10 dias a partir de 05/11/2026"])
async def test_calculator_preserves_answer_pending_and_continuation(conversation, tmp_path, text):
    c, facade, who = conversation, memory.Facade(), memory.identity(conversation)
    path = str(tmp_path / "calc.sqlite")
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        graph = memory.build(c, saver, facade)
        first = await memory.turn(graph, who, "Posso cancelar uma disciplina?")
        facade.status = "CLARIFICATION"
        pending_state = await memory.turn(graph, who, "Pergunta ambígua")
        before = pending_state["conversation_memory"].model_dump_json()
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        graph = memory.build(c, saver, facade)
        state = await memory.turn(graph, who, text)
        assert state["conversation_memory"].model_dump_json() == before
        assert state["calculator_result"] is not None
        assert state["normative_result"] is None and state["grounded_followup_result"] is None
        assert len(facade.calls) == 2
        audit = state["turn_audit"]
        assert audit.calculator_called and audit.calculator_calls == 1 and not audit.facade_calls
        assert audit.memory_preserved and audit.pending_preserved
        assert audit.conversation_action == "CALCULATOR"
        assert project_integrated_state(state).calculator_result == state["calculator_result"]
        facade.status = "ANSWER"
        final = await memory.turn(graph, who, "graduação")
        assert final["calculator_result"] is None
        pending = pending_state["conversation_memory"].pending_clarification
        assert final["normative_result"].correlation_id == pending.correlation_id
        assert facade.calls[-1]["question"] == pending.original_question
        assert facade.calls[-1]["clarification"] == "graduação"
        assert memory.source(first).references == memory.source(final).references


@pytest.mark.asyncio
@pytest.mark.parametrize("followup", ["Repita", "Explique mais simples", "Resuma em 2 linhas"])
async def test_normative_followup_after_calculator(conversation, tmp_path, followup):
    c, facade, who = conversation, memory.Facade(), memory.identity(conversation)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "follow.sqlite")) as saver:
        graph = memory.build(c, saver, facade, memory.Provider())
        first = await memory.turn(graph, who, "Qual o prazo?")
        second = await memory.turn(graph, who, "2+2")
        assert second["conversation_memory"] == first["conversation_memory"]
        final = await memory.turn(graph, who, followup)
        assert final["calculator_result"] is None
        assert (
            final["grounded_followup_result"].source_correlation_id
            == memory.source(first).correlation_id
        )
        assert len(facade.calls) == 1


@pytest.mark.asyncio
async def test_calculator_never_reads_normative_answer_as_parameters(conversation, tmp_path):
    c, facade, who = conversation, memory.Facade(), memory.identity(conversation)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "text.sqlite")) as saver:
        graph = memory.build(c, saver, facade)
        await memory.turn(graph, who, "Qual o prazo de 10 dias?")
        state = await memory.turn(graph, who, "Calcule com aquele prazo")
        assert (
            state.get("calculator_result") is None or state["calculator_result"].status == "ERROR"
        )
        assert len(facade.calls) <= 2


@pytest.mark.asyncio
async def test_three_concurrent_identities_keep_results_distinct(conversation, tmp_path):
    c, facade = conversation, memory.Facade()
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "concurrent.sqlite")) as saver:
        graph = memory.build(c, saver, facade)
        a, b, d = await asyncio.gather(
            *[
                memory.turn(graph, memory.identity(c, user=user), text)
                for user, text in [
                    ("A", "2+2"),
                    ("B", "Qual o art. 68?"),
                    ("C", "Adicione 10 dias corridos a 05/11/2026"),
                ]
            ]
        )
        assert a["calculator_result"].content == "4" and a["conversation_memory"] is None
        assert d["calculator_result"].content == "15/11/2026" and d["conversation_memory"] is None
        assert b["calculator_result"] is None and b["normative_result"]
        assert len(facade.calls) == 1
        assert a["normative_correlation_id"] == d["normative_correlation_id"] == ""


def test_typed_schema_content_exclusivity_and_revalidation(calc):
    result = execute(calc, "2+2")
    message = ChatMessage(type="ai", content="4", calculator_result=result)
    restored = ChatMessage.model_validate_json(message.model_dump_json())
    assert isinstance(restored.calculator_result, calc.CalculatorToolResult)
    for changes in [
        {"type": "human"},
        {"content": "5"},
        {"normative_result": memory.NormativeToolResult(**memory.answer_data())},
    ]:
        with pytest.raises(ValidationError):
            ChatMessage(**{**message.model_dump(), **changes})
    for changes in [
        {"numeric_result": None},
        {"status": "ERROR"},
        {"content": "5"},
        {"references": []},
        {"date_result": "2026-11-05"},
        {"numeric_result": "NaN"},
    ]:
        with pytest.raises(ValidationError):
            calc.CalculatorToolResult(**{**result.model_dump(), **changes})


def test_projection_rejects_forged_calculator_emission(calc):
    from dataclasses import replace

    from langchain_core.messages import AIMessage

    from rag_baseline.conversation_graph import ConversationTurnAudit

    result = execute(calc, "2+2")
    audit = ConversationTurnAudit(
        action="CALCULATOR",
        action_reason_code="calculator_arithmetic",
        correlation_id="",
        conversation_action="CALCULATOR",
        calculator_called=True,
        calculator_calls=1,
        calculator_operation="ARITHMETIC",
        calculator_status="ANSWER",
        nodes_visited=("conversation_entry", "calculator", "calculator_emission"),
        final_source="calculator_result.content",
    )
    state = dict(
        messages=[AIMessage(content="4")],
        calculator_result=result,
        action="CALCULATOR",
        turn_audit=audit,
        normative_correlation_id="",
    )
    assert project_integrated_state(state).content == "4"
    for changes in [
        {"action": "DIRECT"},
        {"turn_audit": replace(audit, calculator_called=False)},
        {"normative_correlation_id": "forged"},
        {"messages": [AIMessage(content="5")]},
    ]:
        with pytest.raises(ValueError):
            project_integrated_state({**state, **changes})


@pytest.mark.asyncio
async def test_calculator_calls_actual_tool_once_and_no_normative_or_network(
    conversation, monkeypatch, tmp_path
):
    import socket

    import httpx

    c = conversation
    calls = []
    real_builder = c.build_calculator_tool

    class SpyTool:
        async def ainvoke(self, args, config):
            calls.append(args)
            return await real_builder().ainvoke(args, config)

    class ForbiddenFacade:
        async def query(self, **kwargs):
            pytest.fail("Calculator called normative facade")

    external = []

    def forbidden(*args, **kwargs):
        external.append(True)
        pytest.fail("Calculator attempted external IO")

    monkeypatch.setattr(c, "build_calculator_tool", SpyTool)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "zero-io.sqlite")) as saver:
        graph = memory.build(c, saver, ForbiddenFacade())
        state = await memory.turn(graph, memory.identity(c), "2+2")
    assert state["calculator_result"].content == "4"
    assert len(calls) == 1 and not external


@pytest.mark.asyncio
async def test_stale_memory_is_preserved_but_never_used_by_calculator(conversation, tmp_path):
    c, facade, who = conversation, memory.Facade(), memory.identity(conversation)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "stale.sqlite")) as saver:
        first = await memory.turn(memory.build(c, saver, facade), who, "Qual o prazo?")
        graph = memory.build(
            c, saver, facade, current=memory.stamp(c, registry_fingerprint="c" * 64)
        )
        state = await memory.turn(graph, who, "2+2")
        assert state["conversation_memory"] == first["conversation_memory"]
        assert state["turn_audit"].memory_status == "STALE"
        assert state["calculator_result"].content == "4"
        final = await memory.turn(graph, who, "Repita")
        assert final["calculator_result"] is None and final["grounded_followup_result"] is None
        assert len(facade.calls) == 1


def test_current_decimal_context_does_not_weaken_result_bounds(calc):
    result = execute(calc, "2+2")
    with localcontext() as context:
        context.prec = 3
        with pytest.raises(ValidationError):
            calc.CalculatorToolResult(
                **{
                    **result.model_dump(),
                    "numeric_result": "1000000000000000000000001",
                    "content": "1000000000000000000000001",
                }
            )


@pytest.mark.parametrize("text", ["2026-11-05", "05/11/2026"])
def test_bare_dates_are_neither_calculator_nor_domain_clarification(calc, text):
    assert not calc.CalculatorIntentParser().parse(text).is_calculator_intent
    assert ConversationFollowUpPolicy().decide(text, pending=True).action == "NORMATIVE_RAG"


@pytest.mark.parametrize(
    "text",
    [
        "Calcule 2+2 e explique se posso perder minha bolsa estudantil",
        "Calcule 2+2 conforme a resolução 956/2025",
    ],
)
def test_mixed_prose_and_nfd_normative_text_are_conservative(calc, text):
    import unicodedata

    for candidate in (text, unicodedata.normalize("NFD", text)):
        assert not calc.CalculatorIntentParser().parse(candidate).is_calculator_intent
        assert ConversationFollowUpPolicy().decide(candidate).action == "NORMATIVE_RAG"


def test_huge_typed_date_offset_returns_error_instead_of_exception(calc):
    from datetime import date

    result = calc.build_calculator_tool().invoke(
        {"request": calc.DateOffsetRequest(start_date=date(2026, 11, 5), days=10**511)}
    )
    assert result.status == "ERROR" and result.error_code == "numeric_limit"


@pytest.mark.parametrize(
    "text,code",
    [
        ("Calcule 10 dias úteis depois de 05/11/2026", "unsupported_business_days"),
        ("Calcule 10 dias a partir de 05/11/2026", "ambiguous_date_offset"),
    ],
)
def test_explicit_calculate_prefix_preserves_date_error_codes(calc, text, code):
    assert execute(calc, text).error_code == code
