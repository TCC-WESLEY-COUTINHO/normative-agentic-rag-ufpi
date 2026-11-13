"""Operational UI revision: states the frozen UI image could not present safely. No backend, no provider."""

from uuid import uuid4

import httpx
import pytest
import test_tcc_ui as ui

from client import AgentClientError
from rag_baseline.tool_contracts import NormativeToolResult
from schema import ChatMessage

controlled = ui.controlled

NOTICE = "Protótipo de pesquisa"
FALLBACK_NOTICE = "não sustentaram uma resposta conclusiva"
ABSTENTION_NOTICE = "Nenhum trecho normativo foi usado nesta resposta"


def abstained():
    result = NormativeToolResult(
        contract_version="1",
        core_version="structured_output_v2",
        status="ANSWER",
        answer="Não há evidência elegível para responder com segurança.",
        core_status="abstained",
        domain="graduacao",
        retrieval_strategy="dense_vector",
        correlation_id=uuid4(),
    )
    return ChatMessage(type="ai", content=result.answer, normative_result=result)


def test_research_notice_is_always_visible(controlled):
    at, _ = ui.start(controlled)
    text = ui.visible(at)
    assert NOTICE in text
    assert "Consulte os documentos oficiais" in text
    for forbidden in ("certificad", "validado juridicamente", "oficial da UFPI"):
        assert forbidden not in text


def test_abstained_with_null_temporal_fields_renders_without_sources(controlled):
    at, fake = ui.start(controlled)
    message = abstained()
    assert message.normative_result.temporal_provenance is None
    fake.events = [message]
    ui.send(at)
    text = ui.visible(at)
    assert message.content in text
    assert ABSTENTION_NOTICE in text
    assert "Consulta histórica" not in text
    assert ui.sources(at) is None
    for private in ui.PRIVATE:
        assert private not in text
    at.run(timeout=15)
    assert not at.exception
    assert ABSTENTION_NOTICE in ui.visible(at)


@pytest.mark.parametrize("core_status", ["accepted", "regenerated"])
def test_substantive_answer_has_no_state_notice(controlled, core_status):
    at, fake = ui.start(controlled)
    fake.events = [ui.normative(core_status=core_status)]
    ui.send(at)
    text = ui.visible(at)
    assert FALLBACK_NOTICE not in text and ABSTENTION_NOTICE not in text


def test_fallback_says_the_sources_did_not_support_a_conclusion(controlled):
    at, fake = ui.start(controlled)
    fake.events = [ui.normative(core_status="fallback")]
    ui.send(at)
    text = ui.visible(at)
    assert FALLBACK_NOTICE in text
    assert "fallback" not in text
    assert "Resposta inconclusiva" in text
    view = ui.sources(at)
    assert len(view.entries) == 3
    assert "Trechos consultados" in view.summary and "Fontes normativas" not in view.summary
    assert not view.sources_open, "Inconclusive text is not presented like a supporting source"


def test_normative_error_uses_warning_and_is_not_plain_answer(controlled):
    at, fake = ui.start(controlled)
    fake.events = [ui.normative("ERROR")]
    ui.send(at)
    message = fake.events[0].content
    assert [w.value for w in at.chat_message[-1].warning] == [message]
    assert message not in [m.value for m in at.chat_message[-1].markdown]
    assert ui.sources(at) is None
    at.run(timeout=15)
    assert [w.value for w in at.chat_message[-1].warning] == [message]


def test_clarification_stays_a_message_without_sources(controlled):
    at, fake = ui.start(controlled)
    fake.events = [ui.normative("CLARIFICATION")]
    ui.send(at)
    assert at.chat_message[-1].markdown[0].value == fake.events[0].content
    assert not at.chat_message[-1].warning


@pytest.mark.parametrize(
    "cause",
    [
        httpx.ConnectError("UNSAFE host"),
        httpx.ConnectTimeout("UNSAFE host"),
        httpx.ReadTimeout("UNSAFE host"),
    ],
)
def test_unreachable_service_is_unavailable(controlled, cause):
    at, fake = ui.start(controlled)
    error = AgentClientError("UNSAFE exception")
    error.__cause__ = cause
    fake.error = error
    ui.send(at)
    assert "temporariamente indisponível" in ui.visible(at)
    assert "UNSAFE" not in ui.visible(at)
    assert len(at.session_state.messages) == 1


@pytest.mark.parametrize("status", [502, 503, 504])
def test_gateway_statuses_are_unavailable(controlled, status):
    at, fake = ui.start(controlled)
    request = httpx.Request("POST", "http://local/private")
    error = AgentClientError("UNSAFE exception")
    error.__cause__ = httpx.HTTPStatusError(
        "UNSAFE", request=request, response=httpx.Response(status, request=request)
    )
    fake.error = error
    ui.send(at)
    assert "temporariamente indisponível" in ui.visible(at)
    assert "UNSAFE" not in ui.visible(at)


def test_context_chained_error_is_read(controlled):
    """The client raises inside `except`, so the httpx error is reached through __context__."""
    at, fake = ui.start(controlled)
    try:
        try:
            raise httpx.ConnectError("UNSAFE host")
        except httpx.HTTPError as inner:
            raise AgentClientError(f"Error: {inner}")
    except AgentClientError as outer:
        fake.error = outer
    ui.send(at)
    assert "temporariamente indisponível" in ui.visible(at)


@pytest.mark.parametrize(
    "kind, guard, expected",
    [
        ("REPEAT", "ACCEPTED", "Repetição da resposta normativa anterior."),
        ("SUMMARY", "FALLBACK_TO_SOURCE", "Repetição da resposta normativa anterior."),
        ("SUMMARY", "ACCEPTED", "Reformulação baseada na resposta normativa anterior."),
        ("REPHRASE", "ACCEPTED", "Reformulação baseada na resposta normativa anterior."),
    ],
)
def test_grounded_caption_states_what_actually_happened(controlled, kind, guard, expected):
    at, fake = ui.start(controlled)
    message = ui.grounded(kind)
    result = message.grounded_followup_result.model_copy(update={"guard_status": guard})
    fake.events = [message.model_copy(update={"grounded_followup_result": result})]
    ui.send(at)
    assert expected in ui.visible(at)


def test_reference_without_article_or_full_text_is_presented(controlled):
    at, fake = ui.start(controlled)
    message = ui.normative()
    result = message.normative_result
    first = result.references[0].model_copy(update={"article": None, "evidence_text": None})
    new = result.model_copy(update={"references": [first]})
    fake.events = [message.model_copy(update={"normative_result": new})]
    ui.send(at)
    entry = ui.sources(at).entries[0]
    assert entry.title == "Trecho normativo"
    assert entry.text is None
    assert entry.missing == "Texto integral indisponível nesta resposta."


@pytest.mark.parametrize(
    "role, label", [("historical", "Contexto histórico"), ("posterior", "Contexto posterior")]
)
def test_reference_temporal_role_is_presented(controlled, role, label):
    at, fake = ui.start(controlled)
    message = ui.normative()
    result = message.normative_result
    first = result.references[0].model_copy(update={"temporal_role": role})
    new = result.model_copy(update={"references": [first]})
    fake.events = [message.model_copy(update={"normative_result": new})]
    ui.send(at)
    assert label in ui.sources(at).entries[0].tags
