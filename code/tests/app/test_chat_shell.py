"""Sidebar, conversations, composer states and visual tokens, through the real script runner."""

import asyncio
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
import streamlit as st
import test_tcc_ui as ui
from streamlit.testing.v1 import AppTest

from chat_ui.character import EXPRESSIONS, RIG, character_markup
from chat_ui.conversations import clean_title, escape_widget_label, title_from_question
from chat_ui.rendering import copy_markup, literal_markdown, note_markup, sources_markup
from chat_ui.theme import DARK, LIGHT, SHARED, stylesheet
from client import AgentClientError
from schema import ChatMessage

controlled = ui.controlled
NOTICE = "Protótipo de pesquisa. Consulte os documentos oficiais para confirmar as informações."
STYLES = Path(ui.APP).with_name("chat_ui") / "styles.css"
PAIRS_BODY = (("c-text", "c-bg"), ("c-muted", "c-bg"), ("c-text", "c-surface"))
PAIRS_MORE = (
    ("c-on-brand", "c-brand"),
    ("c-link", "c-bg"),
    ("c-link", "c-tint"),
    ("c-text", "c-bubble"),
    ("c-text", "c-tint"),
    ("c-muted", "c-surface"),
    ("c-text", "c-raised"),
    ("c-text", "c-hover"),
    ("c-text", "c-selected"),
    ("c-accent", "c-bg"),
    ("c-accent", "c-raised"),
    ("c-warn", "c-bg"),
    ("c-warn", "c-warn-soft"),
    ("c-danger", "c-danger-soft"),
)


def conversation_buttons(at):
    return [b for b in at.sidebar.button if b.key.startswith("conv_open_")]


def by_key(at, prefix):
    return next(b for b in at.button if b.key.startswith(prefix))


def contents(at):
    return [m.content for m in at.session_state.messages]


# Empty state


def test_home_greets_with_only_the_name_highlighted(controlled):
    at, fake = ui.start(controlled)
    greeting = [m.value for m in at.markdown if m.value.startswith("<h1")]
    assert greeting == [
        '<h1 class="ufpi-greeting">Olá! Eu sou o '
        '<span class="ufpi-name-gradient">Bisco</span>.</h1>'
    ]
    text = ui.visible(at)
    assert "Seu assistente virtual para consultas aos regulamentos acadêmicos da UFPI." in text
    assert not at.chat_message, "No invented greeting is shown as if it were an answer"
    assert fake.calls == []


def test_home_has_no_suggestion_cards(controlled):
    at, fake = ui.start(controlled)
    assert [b.key for b in at.main.button] == [], "Nothing under the composer but the notice"
    text = ui.visible(at)
    for title in ("Aproveitamento de disciplinas", "Trancamento de matrícula", "Colação de grau"):
        assert title not in text
    styles = STYLES.read_text(encoding="utf-8")
    assert "suggest" not in styles and "suggest" not in Path(ui.APP).read_text(encoding="utf-8")


def test_one_composer_inline_on_the_home_and_pinned_in_a_conversation(controlled):
    at, fake = ui.start(controlled)
    assert len(at.chat_input) == 1
    assert at.chat_input[0].placeholder == "Faça sua pergunta sobre os regulamentos da UFPI..."
    ui.send(at)
    assert len(at.chat_input) == 1, "Never two composers"
    ui.send(at, "Segunda")
    assert [c["message"] for c in fake.calls] == ["Pergunta", "Segunda"]


def test_research_notice_has_the_exact_wording_and_is_always_present(controlled):
    at, fake = ui.start(controlled)
    assert NOTICE in ui.visible(at)
    ui.send(at)
    assert NOTICE in ui.visible(at)


def test_session_only_history_is_disclosed_before_first_question_and_during_chat(controlled):
    at, _ = ui.start(controlled)
    assert "ficam apenas nesta aba" in ui.visible(at)
    ui.send(at)
    assert "ficam apenas nesta aba" in ui.visible(at)


# Sending


@pytest.mark.parametrize(
    "question",
    ["  Pergunta com  espaços ", "Linha 1\nLinha 2", "**art. 5** <b>x</b> $10 :red[y]", "ção? ñ €"],
)
def test_the_question_reaches_the_service_exactly_as_typed(controlled, question):
    at, fake = ui.start(controlled)
    ui.send(at, question)
    assert fake.calls[0]["message"] == question
    assert at.session_state.messages[0].content == question
    # Streamlit trims outer whitespace in the display element only.
    assert at.chat_message[0].text[0].value == question.strip(), "User text is not Markdown"


def test_controls_release_after_wait_and_cancel_is_available(controlled):
    at, fake = ui.start(controlled)
    ui.send(at, "Primeira")
    original = fake.astream

    async def observing(**kwargs):
        await asyncio.sleep(0.1)
        async for event in original(**kwargs):
            yield event

    fake.astream = observing
    at.chat_input[0].set_value("Segunda").run(timeout=15)
    assert at.chat_input[0].proto.disabled
    assert "Analisando sua pergunta" in ui.visible(at)
    assert at.session_state.in_flight["question"] == "Segunda"
    assert not by_key(at, "cancel_turn").proto.disabled
    ui.settle(at)
    # After the answer: everything is back, with nothing left in flight.
    assert "Analisando sua pergunta" not in ui.visible(at)
    assert not at.chat_input[0].proto.disabled
    assert not any(b.proto.disabled for b in at.sidebar.button if b.key != "theme_system")
    assert "in_flight" not in at.session_state and "pending_turn" not in at.session_state
    assert len(fake.calls) == 2, "Each question is sent exactly once"


# Conversations


def test_conversation_is_listed_with_a_short_title_from_the_first_question(controlled):
    at, _ = ui.start(controlled)
    assert not conversation_buttons(at), "An empty conversation is not listed"
    long_question = (
        "Como funciona o aproveitamento de estudos para quem veio de outra universidade?"
    )
    ui.send(at, long_question)
    label = conversation_buttons(at)[0].label
    assert label.endswith("…") and len(label) < len(long_question)
    assert at.session_state.messages[0].content == long_question


def test_switching_keeps_conversations_and_their_threads_isolated(controlled):
    at, fake = ui.start(controlled)
    ui.send(at, "Primeira")
    first = at.session_state.thread_id
    at.sidebar.button[0].click().run(timeout=15)
    ui.send(at, "Segunda")
    second = at.session_state.thread_id
    assert first != second
    assert [c["thread_id"] for c in fake.calls] == [first, second]
    assert contents(at) == ["Segunda", "Olá!"]

    assert len(conversation_buttons(at)) == 2
    by_key(at, f"conv_open_idle_{first}").click().run(timeout=15)
    assert at.session_state.thread_id == first
    assert contents(at) == ["Primeira", "Olá!"]
    assert "Segunda" not in " ".join(str(t.value) for t in at.text)

    ui.send(at, "Continuação")
    assert fake.calls[-1]["thread_id"] == first
    assert contents(at) == ["Primeira", "Olá!", "Continuação", "Olá!"]
    by_key(at, f"conv_open_idle_{second}").click().run(timeout=15)
    assert contents(at) == ["Segunda", "Olá!"]


def test_new_conversation_on_an_empty_one_does_not_multiply_threads(controlled):
    at, _ = ui.start(controlled)
    thread = at.session_state.thread_id
    at.sidebar.button[0].click().run(timeout=15)
    assert at.session_state.thread_id == thread
    assert len(at.session_state.conversations) == 1


def test_errors_stay_with_their_conversation(controlled):
    at, fake = ui.start(controlled)
    fake.error = RuntimeError("UNSAFE")
    ui.send(at, "Falhou")
    failed = at.session_state.thread_id
    assert len(at.error) == 1
    fake.error = None
    at.sidebar.button[0].click().run(timeout=15)
    assert not at.error
    ui.send(at, "Funcionou")
    assert not at.error
    by_key(at, f"conv_open_idle_{failed}").click().run(timeout=15)
    assert len(at.error) == 1


def test_rename_applies_only_to_that_conversation_and_ignores_blank(controlled):
    at, _ = ui.start(controlled)
    ui.send(at, "Primeira")
    first = at.session_state.thread_id
    at.sidebar.button[0].click().run(timeout=15)
    ui.send(at, "Segunda")
    field = next(t for t in at.text_input if t.key == f"conv_title_{first}")
    field.set_value("  Aproveitamento   de estudos ").run(timeout=15)
    labels = [b.label for b in conversation_buttons(at)]
    assert labels == ["Segunda", "Aproveitamento de estudos"]
    next(t for t in at.text_input if t.key == f"conv_title_{first}").set_value("  ").run(timeout=15)
    assert [b.label for b in conversation_buttons(at)] == labels


def test_markdown_in_a_title_is_shown_literally(controlled):
    at, _ = ui.start(controlled)
    ui.send(at, "**negrito** :red[x] $y$")
    assert conversation_buttons(at)[0].label == r"\*\*negrito\*\* \:red\[x\] \$y\$"


def test_delete_needs_confirmation_and_removes_only_that_conversation(controlled):
    at, _ = ui.start(controlled)
    ui.send(at, "Primeira")
    first = at.session_state.thread_id
    at.sidebar.button[0].click().run(timeout=15)
    ui.send(at, "Segunda")
    second = at.session_state.thread_id
    by_key(at, f"conv_delete_{first}").click().run(timeout=15)
    assert first in at.session_state.conversations, "First click only asks for confirmation"
    by_key(at, f"conv_delete_confirm_{first}").click().run(timeout=15)
    assert first not in at.session_state.conversations
    assert at.session_state.thread_id == second
    assert contents(at) == ["Segunda", "Olá!"]


def test_deleting_the_active_conversation_opens_a_clean_one(controlled):
    at, fake = ui.start(controlled)
    ui.send(at, "Única")
    only = at.session_state.thread_id
    by_key(at, f"conv_delete_{only}").click().run(timeout=15)
    by_key(at, f"conv_delete_confirm_{only}").click().run(timeout=15)
    assert at.session_state.thread_id != only
    assert at.session_state.messages == []
    assert not at.chat_message
    ui.send(at, "Nova")
    assert fake.calls[-1]["thread_id"] == at.session_state.thread_id


# Recoverable failures


def test_retry_resends_the_same_question_without_duplicating_it(controlled):
    at, fake = ui.start(controlled)
    fake.error = RuntimeError("UNSAFE")
    ui.send(at, "Pergunta exata  ")
    assert contents(at) == ["Pergunta exata  "]
    fake.error = None
    by_key(at, "retry_turn").click().run(timeout=15)
    ui.settle(at)
    assert [c["message"] for c in fake.calls] == ["Pergunta exata  ", "Pergunta exata  "]
    assert contents(at) == ["Pergunta exata  ", "Olá!"]
    assert not at.error
    assert not [b for b in at.button if b.key == "retry_turn"]


def test_a_run_stopped_after_the_answer_was_stored_is_not_reported_or_resent(controlled):
    at, fake = ui.start(controlled)
    ui.send(at, "Respondida")
    thread = at.session_state.thread_id
    at.session_state["in_flight"] = {"thread_id": thread, "question": "Respondida"}
    at.run(timeout=15)
    assert not at.error
    assert not [b for b in at.button if b.key == "retry_turn"]
    assert contents(at) == ["Respondida", "Olá!"]
    assert len(fake.calls) == 1


def test_a_response_that_never_arrives_releases_the_interface(controlled, monkeypatch):
    monkeypatch.setattr("chat_ui.conversations.RESPONSE_TIMEOUT_SECONDS", 0.05)
    at, fake = ui.start(controlled)

    async def hanging(**kwargs):
        fake.calls.append(kwargs)
        await asyncio.sleep(30)
        yield ChatMessage(type="ai", content="UNSAFE tardia")

    fake.astream = hanging
    ui.send(at, "Pendurada")
    assert "demorou mais que o esperado" in at.error[0].value
    assert not at.chat_input[0].proto.disabled
    assert contents(at) == ["Pendurada"]
    assert by_key(at, "retry_turn")
    assert "UNSAFE" not in ui.visible(at)


def test_a_failed_question_stays_marked_when_the_conversation_continues(controlled):
    at, fake = ui.start(controlled)
    fake.error = RuntimeError("UNSAFE")
    ui.send(at, "Falhou")
    assert "Sem resposta" not in ui.visible(at), "While it can be retried, the alert says it all"
    fake.error = None
    ui.send(at, "Seguiu")
    assert ui.visible(at).count("Sem resposta") == 1
    assert contents(at) == ["Falhou", "Seguiu", "Olá!"]


def test_a_turn_stopped_mid_request_is_reported_and_not_silently_resent(controlled):
    at, fake = ui.start(controlled)
    fake.error = RuntimeError("UNSAFE")
    ui.send(at, "Interrompida")
    fake.error = None
    thread = at.session_state.thread_id
    at.session_state["in_flight"] = {"thread_id": thread, "question": "Interrompida"}
    at.run(timeout=15)
    assert "interrompida" in at.error[0].value
    assert len(fake.calls) == 1
    by_key(at, "retry_turn").click().run(timeout=15)
    ui.settle(at)
    assert fake.calls[-1]["message"] == "Interrompida"


@pytest.mark.parametrize(
    "cause, expected",
    [
        (httpx.ReadError("UNSAFE"), "foi interrompida antes do fim"),
        (httpx.RemoteProtocolError("UNSAFE"), "foi interrompida antes do fim"),
        (httpx.ConnectError("UNSAFE"), "temporariamente indisponível"),
    ],
)
def test_communication_failure_differs_from_unavailable(controlled, cause, expected):
    at, fake = ui.start(controlled)
    error = AgentClientError("UNSAFE")
    error.__cause__ = cause
    fake.error = error
    ui.send(at)
    assert expected in at.error[0].value
    assert "UNSAFE" not in ui.visible(at)


def test_internal_error_has_its_own_message(controlled):
    at, fake = ui.start(controlled)
    request = httpx.Request("POST", "http://local/private")
    error = AgentClientError("UNSAFE")
    error.__cause__ = httpx.HTTPStatusError(
        "UNSAFE", request=request, response=httpx.Response(500, request=request)
    )
    fake.error = error
    ui.send(at)
    assert "erro interno" in at.error[0].value
    assert "Traceback" not in ui.visible(at)


# States and sources


def test_states_are_stated_in_words(controlled):
    at, fake = ui.start(controlled)
    fake.events = [ui.normative("CLARIFICATION")]
    ui.send(at)
    assert "Preciso de um esclarecimento" in ui.visible(at)
    fake.events = [ui.normative(core_status="accepted")]
    ui.send(at, "Outra")
    last = "\n".join(str(c.value) for c in at.chat_message[-1].caption)
    assert "inconclusiva" not in last and "esclarecimento" not in last


def test_uncertified_status_comes_from_the_typed_evidence_state_only(controlled):
    at, fake = ui.start(controlled)
    message = ui.normative()
    result = message.normative_result
    states = [
        state.model_copy(update={"chunk_id": result.references[0].chunk_id})
        for state in result.temporal_provenance.evidence_states
    ]
    provenance = result.temporal_provenance.model_copy(update={"evidence_states": states})
    for status, expected in (("desconhecida", True), ("vigente", False)):
        marked = [s.model_copy(update={"normative_status": status}) for s in states]
        new = result.model_copy(
            update={
                "temporal_provenance": provenance.model_copy(update={"evidence_states": marked})
            }
        )
        fake.events = [message.model_copy(update={"normative_result": new})]
        ui.send(at, status)
        tags = [tag for entry in ui.sources(at).entries for tag in entry.tags]
        assert ("Vigência não certificada" in tags) is expected


def test_sources_escape_everything_received_from_the_service():
    base = ui.normative().normative_result.references[0]
    hostile = base.model_copy(
        update={
            "source": "<img src=x onerror=alert(1)>",
            "article": "1<script>",
            "validated_subdivision": "<b>§</b>",
            "evidence_text": "A\n\n<script>alert(1)</script>\n\n**B** & C",
        }
    )
    markup = sources_markup([hostile])
    view = ui.SourcesView(markup)
    assert view.script_or_bold_elements == 0
    assert "\n" not in markup, "A blank line would reopen Markdown parsing inside the block"
    assert view.entries[0].text == "A\n\n<script>alert(1)</script>\n\n**B** & C"
    assert view.norms == ["<img src=x onerror=alert(1)>"]


def test_sources_label_is_singular_and_does_not_claim_support():
    base = ui.normative().normative_result.references[0]
    view = ui.SourcesView(sources_markup([base], domain="pos_graduacao"))
    assert "1 norma · 1 trecho" in view.summary
    assert "normas de pós-graduação" in view.hint
    assert "recuperados" in view.hint and "não indica" in view.hint


def test_no_score_or_url_is_invented_for_sources():
    base = ui.normative().normative_result.references[0]
    markup = sources_markup([base])
    assert "<a " not in markup and "http" not in markup
    assert "score" not in markup.lower() and "%" not in markup


@pytest.mark.parametrize(
    "raw, shown",
    [
        ("Taxa de R$ 10,00 e R$ 50,00", r"Taxa de R\$ 10,00 e R\$ 50,00"),
        ("Ver :smile: e :red[x]", r"Ver \:smile: e \:red[x]"),
        ("Em `R$ 1` fica", "Em `R$ 1` fica"),
        ("Em ``R$ 1`` fica", "Em ``R$ 1`` fica"),
        ("``a ` R$ 1`` e R$ 2", r"``a ` R$ 1`` e R\$ 2"),
        ("```\nR$ 1\n\nR$ 2\n```\nR$ 3", "```\nR$ 1\n\nR$ 2\n```\nR\\$ 3"),
        ("```\nR$ 1\n``` e R$ 2", "```\nR$ 1\n``` e R$ 2"),
        ("```text\nExemplo: ```\nR$ 1\n```\nR$ 2", "```text\nExemplo: ```\nR$ 1\n```\nR\\$ 2"),
        ("````\n```\nR$ 1\n````\nR$ 2", "````\n```\nR$ 1\n````\nR\\$ 2"),
        ("Solto ` R$ 1\n\noutro ` R$ 2", "Solto ` R\\$ 1\n\noutro ` R\\$ 2"),
        ("```a ```` R$ 1``` e R$ 2", "```a ```` R$ 1``` e R\\$ 2"),
        ("```\nR$ 1 sem fechar", "```\nR$ 1 sem fechar"),
        ("~~~\nR$ 1\n~~~\nR$ 2", "~~~\nR$ 1\n~~~\nR\\$ 2"),
        ("Às 10:30 e https://ufpi.br/a", "Às 10:30 e https://ufpi.br/a"),
        ("**Negrito** e | tabela |", "**Negrito** e | tabela |"),
    ],
)
def test_literal_markdown_only_neutralizes_math_and_shortcodes(raw, shown):
    assert literal_markdown(raw) == shown


@pytest.mark.parametrize(
    "raw, shown",
    [
        ("> ~~~sh\n> echo $HOME\n> ~~~\n> R$ 1", "> ~~~sh\n> echo $HOME\n> ~~~\n> R\\$ 1"),
        ("```\n```~\necho $TWO\n```\nR$ 2", "```\n```~\necho $TWO\n```\nR\\$ 2"),
        ("~~~\n```\nR$ 1\n~~~\nR$ 2", "~~~\n```\nR$ 1\n~~~\nR\\$ 2"),
        ("```sh\n> ```\necho $TWO\n```\nR$ 2", "```sh\n> ```\necho $TWO\n```\nR\\$ 2"),
        (
            ">    ~~~sh\n>    echo $HOME\n>    ~~~\nR$ 2",
            ">    ~~~sh\n>    echo $HOME\n>    ~~~\nR\\$ 2",
        ),
    ],
)
def test_literal_markdown_follows_fence_rules(raw, shown):
    assert literal_markdown(raw) == shown


def test_literal_markdown_is_linear_on_hostile_backticks_and_only_adds_escapes():
    hostile = "a " + " x ".join("`" * k for k in range(1, 801)) + " R$ 1 :red[y]"
    started = time.perf_counter()
    shown = literal_markdown(hostile)
    assert time.perf_counter() - started < 0.5
    assert shown.replace("\\$", "$").replace("\\:", ":") == hostile


@pytest.mark.parametrize(
    "raw, shown",
    [
        ("Exemplo:\n\n    R$ 10,00 :smile:\n\nR$ 2", "Exemplo:\n\n    R$ 10,00 :smile:\n\nR\\$ 2"),
        ("    R$ 1 logo no início", "    R$ 1 logo no início"),
        ("Exemplo:\n\n\tR$ 1", "Exemplo:\n\n\tR$ 1"),
        ("    R$ 1\n\n    R$ 2\n", "    R$ 1\n\n    R$ 2\n"),
        ("Parágrafo\n    R$ 1 continua", "Parágrafo\n    R\\$ 1 continua"),
        ("Exemplo:\n\n>     R$ 10,00 :smile:", "Exemplo:\n\n>     R$ 10,00 :smile:"),
        ("> Citação:\n>\n>     R$ 1\n\nR$ 2", "> Citação:\n>\n>     R$ 1\n\nR\\$ 2"),
        ("> Citação\n>     R$ 1 continua", "> Citação\n>     R\\$ 1 continua"),
        ("1. Item\n\n    Taxa de R$ 1 e R$ 2", "1. Item\n\n    Taxa de R\\$ 1 e R\\$ 2"),
        (
            "- Item\n\n    R$ 1\n\nFim R$ 2\n\n    R$ 3",
            "- Item\n\n    R\\$ 1\n\nFim R\\$ 2\n\n    R$ 3",
        ),
    ],
)
def test_literal_markdown_leaves_indented_code_untouched(raw, shown):
    assert literal_markdown(raw) == shown


@pytest.mark.parametrize(
    "raw, shown",
    [
        ("Já escapado R\\$ 10", "Já escapado R\\$ 10"),
        ("Barra literal \\\\$ 10", "Barra literal \\\\\\$ 10"),
        ("Já escapado \\:smile:", "Já escapado \\:smile:"),
    ],
)
def test_literal_markdown_does_not_double_an_existing_escape(raw, shown):
    assert literal_markdown(raw) == shown


def _followup_of(source, kind="SUMMARY"):
    result = source.normative_result
    followup = ui.grounded(kind).grounded_followup_result.model_copy(
        update={
            "source_correlation_id": result.correlation_id,
            "references": result.references,
            "guard_status": "ACCEPTED",
        }
    )
    return ChatMessage(type="ai", content=followup.content, grounded_followup_result=followup)


@pytest.mark.parametrize("kind", ["REPEAT", "REPHRASE", "SUMMARY"])
def test_a_followup_of_an_inconclusive_answer_stays_inconclusive(controlled, kind):
    at, fake = ui.start(controlled)
    source = ui.normative(core_status="fallback")
    fake.events = [source]
    ui.send(at)
    fake.events = [_followup_of(source, kind)]
    ui.send(at, "Resuma")
    captions = " ".join(str(c.value) for c in at.chat_message[-1].caption)
    assert "Resposta inconclusiva" in captions
    view = ui.sources(at)
    assert "Trechos consultados" in view.summary and "Fontes normativas" not in view.summary
    assert not view.sources_open


def test_a_followup_whose_source_never_arrived_is_not_presented_as_supported(controlled):
    at, fake = ui.start(controlled)
    fake.error = RuntimeError("UNSAFE")
    ui.send(at)
    fake.error = None
    fake.events = [_followup_of(ui.normative(core_status="fallback"))]
    ui.send(at, "Repita")
    view = ui.sources(at)
    assert "Trechos consultados" in view.summary and "Fontes normativas" not in view.summary
    assert not view.sources_open
    captions = " ".join(str(c.value) for c in at.chat_message[-1].caption)
    assert "Origem não confirmada" in captions
    assert "Resposta inconclusiva" not in captions, "The state of an unseen answer is not asserted"


def test_a_followup_of_a_conclusive_answer_keeps_its_sources(controlled):
    at, fake = ui.start(controlled)
    source = ui.normative(core_status="accepted")
    fake.events = [source]
    ui.send(at)
    fake.events = [_followup_of(source)]
    ui.send(at, "Resuma")
    captions = " ".join(str(c.value) for c in at.chat_message[-1].caption)
    assert "Resposta inconclusiva" not in captions
    assert "Fontes normativas" in ui.sources(at).summary


def test_an_older_inconclusive_answer_does_not_mark_a_followup_of_another_answer(controlled):
    at, fake = ui.start(controlled)
    fake.events = [ui.normative(core_status="fallback")]
    ui.send(at)
    source = ui.normative(core_status="accepted")
    distinct = source.normative_result.model_copy(update={"correlation_id": uuid4()})
    source = source.model_copy(update={"normative_result": distinct})
    fake.events = [source]
    ui.send(at, "Outra")
    fake.events = [_followup_of(source)]
    ui.send(at, "Resuma")
    assert "Fontes normativas" in ui.sources(at).summary


def test_answer_with_currency_is_stored_exactly_and_displayed_literally(controlled):
    at, fake = ui.start(controlled)
    fake.events = [ChatMessage(type="ai", content="Taxa de R$ 10,00 a R$ 50,00.")]
    ui.send(at)
    assert at.session_state.messages[-1].content == "Taxa de R$ 10,00 a R$ 50,00."
    assert at.chat_message[-1].markdown[0].value == r"Taxa de R\$ 10,00 a R\$ 50,00."


def test_note_markup_escapes_and_names_the_state():
    assert "<strong>Rótulo.</strong> a &lt;b&gt;" in note_markup("Rótulo", "a <b>")


# Titles


@pytest.mark.parametrize(
    "question, title",
    [
        ("  Curta \n pergunta ", "Curta pergunta"),
        ("", "Nova conversa"),
        ("x" * 200, "x" * 60 + "…"),
    ],
)
def test_title_from_question(question, title):
    assert title_from_question(question) == title


def test_clean_title_limits_and_normalizes():
    assert clean_title("  a   b ") == "a b"
    assert len(clean_title("y" * 500)) == 80


def test_escape_widget_label_covers_markdown_triggers():
    assert escape_widget_label("a*b_c`d[e]$f:g") == r"a\*b\_c\`d\[e\]\$f\:g"


# Theme


def _style(at):
    return next(m.value for m in at.markdown if m.value.startswith("<style>"))


def test_theme_follows_the_system_until_the_toggle_is_used(controlled):
    at, _ = ui.start(controlled)
    style = _style(at)
    assert "prefers-color-scheme: dark" in style
    assert LIGHT["c-surface"] in style and DARK["c-surface"] in style
    by_key(at, "theme_to_dark").click().run(timeout=15)
    style = _style(at)
    assert DARK["c-surface"] in style and LIGHT["c-surface"] not in style
    by_key(at, "theme_to_light").click().run(timeout=15)
    style = _style(at)
    assert LIGHT["c-surface"] in style and DARK["c-surface"] not in style


def test_theme_toggle_is_one_control_with_moon_and_sun_icons(controlled):
    at, _ = ui.start(controlled)
    keys = [b.key for b in at.sidebar.button if "theme" in b.key]
    assert keys == ["theme_to_dark", "theme_to_light"]
    assert by_key(at, "theme_to_dark").proto.icon == ":material/dark_mode:"
    assert by_key(at, "theme_to_light").proto.icon == ":material/light_mode:"


@pytest.mark.parametrize(
    "mode, visible, hidden",
    [("light", "theme_to_dark", "theme_to_light"), ("dark", "theme_to_light", "theme_to_dark")],
)
def test_only_the_direction_leaving_the_palette_is_shown(mode, visible, hidden):
    style = stylesheet(mode)
    assert f".st-key-{hidden}{{display:none}}" in style
    assert f".st-key-{visible}{{display:block}}" in style


def test_system_mode_switches_the_toggle_inside_the_dark_preference():
    style = stylesheet("system")
    light, dark = style.split("@media (prefers-color-scheme: dark)")[:2]
    assert ".st-key-theme_to_light{display:none}" in light
    assert (
        ".st-key-theme_to_dark{display:none}" in dark[: dark.index("}.st-key-theme_to_light") + 40]
    )


def test_palettes_declare_the_same_tokens():
    assert set(LIGHT) == set(DARK)


def _luminance(color):
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("palette", [LIGHT, DARK], ids=["light", "dark"])
@pytest.mark.parametrize("foreground, background", PAIRS_BODY + PAIRS_MORE)
def test_text_tokens_meet_wcag_aa(palette, foreground, background):
    assert _contrast(palette[foreground], palette[background]) >= 4.5


def test_styles_use_tokens_and_no_loose_colors():
    css = STYLES.read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css), "Colors belong in the tokens"
    used = set(re.findall(r"var\(--([\w-]+)\)", css))
    assert used <= set(LIGHT) | set(SHARED), used - (set(LIGHT) | set(SHARED))
    assert set(LIGHT) == set(DARK), "Every token exists in both themes"
    assert "backdrop-filter" not in css
    gradients = re.findall(r"([^{}]+)\{[^{}]*linear-gradient", css)
    assert sorted(g.strip().split("\n")[-1] for g in gradients) == [
        ".ufpi-name-gradient",
        ".ufpi-progress-label",
    ], "Only the name and the progress label's shimmer carry gradients"


def test_style_never_carries_internal_vocabulary():
    assert "fallback" not in stylesheet().lower()
    assert "reduced-motion" in stylesheet()


def test_page_has_no_emoji_decoration():
    source = Path(ui.APP).read_text(encoding="utf-8")
    assert not re.search(r"[\U0001F300-\U0001FAFF]", source)
    assert "write_stream" not in source and "re.search" not in source


def test_app_runs_with_no_exception_after_full_rerun(controlled):
    at = AppTest.from_file(str(ui.APP)).run(timeout=15)
    at.run(timeout=15)
    assert not at.exception


# Identity


def test_palette_uses_the_specified_institutional_colors():
    assert LIGHT["c-brand"] == "#0033CC" and LIGHT["c-brand-deep"] == "#083897"
    assert (LIGHT["grad-from"], LIGHT["grad-mid"], LIGHT["grad-to"]) == (
        "#083897",
        "#0033CC",
        "#4D7CFF",
    )
    assert LIGHT["c-app"] == "#F5F6F8" and LIGHT["c-bg"] == "#FFFFFF"
    assert LIGHT["c-highlight"] == "#F3BD35", "Tassel yellow, for small details only"
    for theme in (LIGHT, DARK):
        assert _contrast(theme["c-on-brand"], theme["c-brand"]) >= 4.5, "Text on blue buttons"
        assert _contrast(theme["c-on-interact"], theme["c-interact"]) >= 3, "Send icon"
        for surface in ("c-bg", "c-app", "c-raised"):
            assert _contrast(theme["c-text"], theme[surface]) >= 7
            assert _contrast(theme["c-muted"], theme[surface]) >= 4.5, (theme["c-muted"], surface)
        assert _contrast(theme["c-brand-deep"], theme["c-app"]) >= 4.5, "Sidebar name"
    styles = STYLES.read_text(encoding="utf-8")
    assert "var(--c-highlight)" in styles and styles.count("var(--c-highlight)") <= 2


def test_interaction_purple_is_used_sparingly():
    css = STYLES.read_text(encoding="utf-8")
    assert css.count("var(--c-interact)") <= 8


def test_sidebar_shows_bisco_and_no_unverified_mark(controlled):
    at, _ = ui.start(controlled)
    markup = " ".join(m.value for m in at.sidebar.markdown)
    assert 'class="ufpinho ufpinho-chat bisco-figure" data-state="happy"' in markup
    assert '<div class="ufpi-brand">' in markup, "Bisco, name and role in one card"
    assert '<span class="ufpi-brand-name">Bisco</span>' in markup
    assert '<span class="ufpi-brand-role">Assistente Normativo</span>' in markup
    brand = STYLES.read_text(encoding="utf-8").split(".ufpi-brand {", 1)[1].split("}", 1)[0]
    assert "background: var(--c-raised)" in brand and "border-radius" in brand
    assert "border: 1px solid var(--c-border)" in brand
    assert 'href="app/static/bisco/rig/sm/v3_base.png"' in markup
    assert "data-ufpinho-lead" not in markup, "The sidebar card is a still picture, never the lead"
    assert "data:image" not in markup and "Marca da UFPI" not in markup
    assert not (Path(ui.APP).with_name("chat_ui") / "assets").exists()


def test_only_bisco_ships_and_every_rig_layer_exists():
    static = Path(ui.APP).with_name("static")
    assert sorted(p.name for p in static.iterdir()) == ["bisco", "fonts"], "No previous character"
    bisco = static / "bisco"
    shipped = {p.relative_to(bisco).as_posix() for p in bisco.rglob("*.png")}
    referenced = set()

    def collect(node):
        if isinstance(node, dict):
            if isinstance(node.get("files"), dict):
                referenced.update(node["files"].values())
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    collect(RIG)
    assert referenced and referenced <= shipped, sorted(referenced - shipped)[:5]
    assert shipped - referenced == {"favicon-64.png"}, "Only what the rig draws, plus the favicon"
    assert {Path(f).parts[1] for f in referenced} == {"sm", "md", "hi"}
    assert len(EXPRESSIONS) == 10 and set(EXPRESSIONS) == {
        "neutral",
        "happy",
        "thinking",
        "clarification",
        "answering",
        "surprise",
        "abstained",
        "error",
        "blink",
        "looking",
    }


def test_favicon_is_bisco_on_a_transparent_background():
    from PIL import Image

    icon_path = Path(ui.APP).with_name("static") / "bisco" / "favicon-64.png"
    icon = Image.open(icon_path)
    assert icon.size == (64, 64) and icon.mode == "RGBA"
    alpha = icon.getchannel("A")
    assert alpha.getextrema()[0] == 0 and alpha.getextrema()[1] >= 250, "Transparent corners"
    assert alpha.getpixel((0, 0)) == 0 and alpha.getpixel((63, 63)) == 0
    rgb = icon.convert("RGB")
    assert any(
        rgb.getpixel((x, 32))[2] > 180 and rgb.getpixel((x, 32))[0] < 90 for x in range(64)
    ), "The blue scribble is recognisable"
    source = Path(ui.APP).read_text(encoding="utf-8")
    assert source.count("st.set_page_config(") == 1 and "page_icon=FAVICON" in source
    assert '"bisco" / "favicon-64.png"' in source and "Image.open(LOGO_PATH)" not in source


def test_still_picture_uses_the_rig_canvas_and_boxes():
    markup = character_markup("neutral", variant="home", uid="h")
    assert 'viewBox="0 0 1024 1024"' in markup
    boxes = re.findall(r'x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)"', markup)
    expected = [RIG["v3"]["base"]["box"], RIG["body"]["eye_whites"]["box"]] + [
        RIG["expressions"]["neutral"]["parts"][slot]["box"]
        for slot in ("eye_left", "eye_right", "brow_left", "brow_right", "mouth")
    ]
    assert [list(map(int, b)) for b in boxes] == expected, "Base, eye whites, then one expression"
    assert markup.count("<image ") == 7 and "/rig/md/" in markup
    closed = character_markup("blink", variant="chat")
    assert "eye_whites" not in closed and closed.count("<image ") == 6, "Blink closes the whole eye"
    assert "/rig/sm/" in closed


def test_character_markup_nests_the_still_picture_in_its_host():
    markup = character_markup("happy", variant="home", uid="h")
    order = [
        markup.index(name)
        for name in ('class="ufpinho ', 'class="bisco-host"', 'class="bisco-still"')
    ]
    assert order == sorted(order), "figure > host > still picture"
    assert "tabindex" not in markup and 'role="button"' not in markup


def test_only_an_interactive_figure_is_a_labelled_button():
    button = character_markup(
        "happy", variant="home", uid="h", label="Bisco <b>", lead="home", interactive=True
    )
    assert 'class="ufpinho ufpinho-home bisco-figure ufpinho-interactive"' in button
    assert 'role="button" tabindex="0" aria-label="Bisco &lt;b&gt;"' in button
    with pytest.raises(ValueError):
        character_markup("happy", variant="home", interactive=True)


def test_home_figure_greets_and_answers_avatars_do_not(controlled):
    at, fake = ui.start(controlled)
    home = [m.value for m in at.markdown if "ufpinho-home" in m.value and "<style>" not in m.value]
    assert len(home) == 1 and "ufpinho-interactive" in home[0] and 'role="button"' in home[0]
    fake.events = [ui.normative()]
    ui.send(at)
    avatars = [
        m.value for m in at.markdown if "ufpinho-chat" in m.value and "<style>" not in m.value
    ]
    assert avatars and not any("ufpinho-interactive" in a or "tabindex" in a for a in avatars)


def test_character_markup_shows_one_expression_and_carries_no_ids():
    markup = character_markup("thinking", variant="loading", uid="x1")
    assert "\n" not in markup, "A blank line would reopen Markdown parsing"
    assert 'data-state="thinking"' in markup and "ufpinho-loading" in markup
    assert "thinking__eye_left" in markup and "neutral__" not in markup, "One expression only"
    assert " id=" not in markup, "Nothing two figures could clash on"
    assert 'aria-hidden="true"' in markup
    for name in EXPRESSIONS:
        assert f"{name}__mouth" in character_markup(name)
    labelled = character_markup("happy", variant="home", uid="h", label='UF "<b>"')
    assert 'role="img" aria-label="UF &quot;&lt;b&gt;&quot;"' in labelled
    with pytest.raises(ValueError):
        character_markup("celebrating")
    with pytest.raises(ValueError):
        character_markup("neutral", variant="huge")


def test_home_shows_the_living_character_and_the_chat_a_still_one(controlled):
    at, fake = ui.start(controlled)
    home = [m.value for m in at.markdown if "ufpinho-home" in m.value and "<style>" not in m.value]
    assert len(home) == 1 and 'data-state="happy"' in home[0]
    fake.events = [ui.normative()]
    ui.send(at)
    assert not any("ufpinho-home" in m.value and "<style>" not in m.value for m in at.markdown)
    avatars = [m.value for m in at.chat_message[-1].markdown if "ufpinho-chat" in m.value]
    assert len(avatars) == 1 and 'data-state="neutral"' in avatars[0]
    assert not [m.value for m in at.chat_message[0].markdown if "ufpinho" in m.value]


def test_thinking_figure_appears_only_while_the_request_runs(controlled, monkeypatch):
    at, fake = ui.start(controlled)
    seen = {}
    markdown = Mock(wraps=st.markdown)
    monkeypatch.setattr(st, "markdown", markdown)
    original = fake.astream

    async def observing(**kwargs):
        seen["loading"] = any("ufpinho-loading" in str(c.args) for c in markdown.call_args_list)
        async for event in original(**kwargs):
            yield event

    fake.astream = observing
    ui.send(at)
    assert seen["loading"]
    assert not any("ufpinho-loading" in m.value for m in at.markdown if "<style>" not in m.value)


@pytest.mark.parametrize(
    "factory, expression",
    [
        (lambda: ui.normative("CLARIFICATION"), "clarification"),
        (lambda: ui.normative(core_status="fallback"), "abstained"),
        (
            lambda: ui.normative(core_status="abstained") if False else ui.normative("ERROR"),
            "error",
        ),
        (ui.normative, "neutral"),
        (lambda: ui.normative(core_status="regenerated"), "neutral"),
        (lambda: ChatMessage(type="ai", content="Direta."), "neutral"),
        (ui.calculator, "neutral"),
        (lambda: ui.calculator("1/0"), "error"),
    ],
)
def test_expression_follows_the_typed_state(factory, expression):
    import streamlit_app

    assert streamlit_app.message_expression(factory()) == expression


def test_abstention_and_unconfirmed_followups_are_calm_not_smiling():
    from test_ui_operational import abstained

    import streamlit_app

    assert streamlit_app.message_expression(abstained()) == "abstained"
    followup = _followup_of(ui.normative(core_status="fallback"))
    assert streamlit_app.message_expression(followup, []) == "abstained"
    assert streamlit_app.message_expression(ChatMessage(type="human", content="x")) is None


def test_no_answer_state_maps_to_a_happy_face():
    import streamlit_app

    for factory in (ui.normative, lambda: ui.normative(core_status="regenerated"), ui.grounded):
        assert streamlit_app.message_expression(factory()) != "happy"


def test_transport_failure_shows_the_attentive_face_beside_the_alert(controlled):
    at, fake = ui.start(controlled)
    fake.error = RuntimeError("UNSAFE")
    ui.send(at)
    faces = [
        m.value for m in at.markdown if 'data-state="error"' in m.value and "<style>" not in m.value
    ]
    assert len(faces) == 1 and len(at.error) == 1


def _leads(at):
    return [
        re.search(r'data-ufpinho-lead="([^"]+)"', m.value).group(1)
        for m in at.markdown
        if "data-ufpinho-lead=" in m.value and "<style>" not in m.value
    ]


def test_exactly_one_lead_figure_on_every_screen(controlled, monkeypatch):
    at, fake = ui.start(controlled)
    assert _leads(at) == ["home"]
    seen = {}
    markdown = Mock(wraps=st.markdown)
    monkeypatch.setattr(st, "markdown", markdown)
    original = fake.astream

    async def observing(**kwargs):
        seen["busy"] = [
            re.search(r'data-ufpinho-lead="([^"]+)"', str(c.args)).group(1)
            for c in markdown.call_args_list
            if "data-ufpinho-lead=" in str(c.args) and "<style>" not in str(c.args)
        ]
        async for event in original(**kwargs):
            yield event

    fake.astream = observing
    ui.send(at)
    assert seen["busy"][-1] == "loading" and "home" not in seen["busy"]
    thread = at.session_state.thread_id
    assert _leads(at) == [f"{thread}-1"]
    ui.send(at, "Outra")
    assert _leads(at) == [f"{thread}-3"], "Older answers are no longer the lead"
    fake.error = RuntimeError("UNSAFE")
    ui.send(at, "Falha")
    assert _leads(at) == [f"{thread}-failure"]
    fake.error = None
    at.sidebar.button[0].click().run(timeout=15)
    assert _leads(at) == ["home"]


def test_page_script_keeps_its_position_on_every_screen(controlled):
    """Streamlit remounts an element whose position changes; the page script must never move."""
    at, fake = ui.start(controlled)

    def script_slot():
        block = at.main.children[1]
        return "leadObserver" in str(list(block.children.values())[0].proto)

    states = [script_slot()]
    ui.send(at)
    states.append(script_slot())
    fake.error = RuntimeError("UNSAFE")
    ui.send(at, "Falha")
    states.append(script_slot())
    at.sidebar.button[0].click().run(timeout=15)
    states.append(script_slot())
    assert states == [True, True, True, True]


def test_transition_script_handles_only_geometry_and_no_content():
    script = (Path(ui.APP).with_name("chat_ui") / "transition.js").read_text(encoding="utf-8")
    for forbidden in (
        "innerHTML",
        "textContent",
        "eval(",
        "new Function",
        "fetch(",
        "localStorage",
    ):
        assert forbidden not in script
    assert "prefers-reduced-motion: reduce" in script
    assert "removeEventListener" in script and "disconnect()" in script
    assert 'aria-hidden", "true"' in script, "The ghost never enters the accessibility tree"


def test_character_script_touches_only_its_figures_and_cleans_up():
    folder = Path(ui.APP).with_name("chat_ui")
    script = (folder / "character.js").read_text(encoding="utf-8")
    for forbidden in (
        "innerHTML",
        "textContent",
        "eval(",
        "new Function",
        "fetch(",
        "localStorage",
    ):
        assert forbidden not in script
    assert "\n{\n" in script, "Its own block: no clash with the other page scripts' names"
    # A function declaration inside a block leaks to the shared script's global scope (Annex B)
    # and once replaced presentation.js's own release(): helpers must be const functions.
    assert not re.search(r"^\s*function\s", script, flags=re.MULTILINE)
    assert "prefers-reduced-motion: reduce" in script
    assert "win: pageWin" in script, "Timers and frames run on the page, not in the 0-px iframe"
    assert script.count("addEventListener(") == script.count("removeEventListener(") + 1, (
        "Every page listener is removed on pagehide (the pagehide listener itself excepted)"
    )
    assert "disconnect()" in script and "cancelAnimationFrame" in script and ".destroy()" in script
    app = Path(ui.APP).read_text(encoding="utf-8")
    assert '("bridge.js", "presentation.js", "transition.js", "character.js")' in app


def test_character_runtime_is_bundled_as_a_classic_script_in_its_own_block():
    import streamlit_app

    runtime = streamlit_app.character_runtime()
    assert runtime.startswith("var BISCO_RIG = {") and "\nexport " not in runtime
    # Its own strict function scope: no runtime name, function declarations included, can reach
    # the shared page script; only BiscoRuntime is published.
    assert 'var BiscoRuntime = (function () {\n"use strict";' in runtime
    assert runtime.rstrip().endswith("return { BiscoCharacter };\n})();")
    script = streamlit_app.BRIDGE_SCRIPT
    assert script.index("var BISCO_RIG") < script.index("const LIVE = "), "Runtime before its user"
    assert script.index("leadObserver") < script.index("var BISCO_RIG"), "Transition first"
    assert "</script" not in script.lower()


def test_figure_opts_out_of_selection_without_blocking_text_or_clicks():
    folder = Path(ui.APP).with_name("chat_ui")
    css = (folder / "character.css").read_text(encoding="utf-8")
    rules = re.findall(r"([^{}]+)\{([^{}]*user-select:\s*none[^{}]*)\}", css)
    assert rules, "The figure is not selectable"
    for selector, _ in rules:
        parts = [part for part in selector.split("*/")[-1].split(",") if part.strip()]
        assert all(".ufpinho" in part for part in parts), selector
    assert ".ufpinho-interactive:focus-visible" in css
    interactive = re.findall(r"\.ufpinho-interactive[^{]*\{([^}]*)\}", css)
    assert not any("pointer-events: none" in body for body in interactive)
    assert "user-select: none" not in (folder / "styles.css").read_text(encoding="utf-8")


def test_mobile_drawer_floats_over_the_page_only_on_phones():
    folder = Path(ui.APP).with_name("chat_ui")
    styles = (folder / "styles.css").read_text(encoding="utf-8")
    start = styles.index("@media (max-width: 768px)")
    mobile = styles[start : styles.index("\n}\n", start)]
    assert '[data-testid="stSidebar"][aria-expanded="true"]' in mobile
    assert "position: fixed !important" in mobile and "min(300px, 85vw)" in mobile
    assert "::after" in mobile and "overflow: hidden !important" in mobile
    sidebar = styles[styles.index("/* Sidebar */") : start]
    assert "position: fixed" not in sidebar.split("\n\n")[0], "Desktop sidebar unchanged"
    bridge = (folder / "bridge.js").read_text(encoding="utf-8")
    assert '"Escape"' in bridge and 'toggleAttribute("inert"' in bridge
    assert 'addEventListener("click", closeSidebarOnMobile, true)' in bridge
    assert 'removeEventListener("click", closeSidebarOnMobile, true)' in bridge


def test_character_motion_is_small_and_respects_reduced_motion():
    css = (Path(ui.APP).with_name("chat_ui") / "character.css").read_text(encoding="utf-8")
    assert "prefers-reduced-motion: reduce" in css and "animation: none !important" in css
    assert ".bisco--reduced" in css
    for name in ("bisco-bob", "bisco-sway", "ufpinho-enter", "ufpinho-halo-in"):
        assert f"@keyframes {name}" in css
    sways = [float(v) for v in re.findall(r"--bisco-sway:\s*(-?[\d.]+)deg", css)]
    bobs = [float(v) for v in re.findall(r"--bisco-bob:\s*(-?[\d.]+)%", css)]
    assert sways and max(sways) <= 1 and bobs and max(bobs) <= 2.5, "Small float and sway"
    assert ".ufpinho-chat .bisco { --bisco-bob: 2.2%; --bisco-sway: 0deg; }" in css, (
        "The newest answer only breathes"
    )
    assert '.ufpinho[style*="hidden"] .bisco-float' in css, "A hidden flight target waits at rest"
    assert ".ufpinho .bisco-host:not(.bisco-live) > .bisco-float { visibility: hidden; }" in css, (
        "A half-loaded live rig never shows beside the still picture"
    )
    transition = (Path(ui.APP).with_name("chat_ui") / "transition.js").read_text(encoding="utf-8")
    assert "window.biscoGhost.adopt(ghost, source)" in transition, (
        "The ghost starts from the source"
    )
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css)
    assert "rotateY" not in css and "perspective" not in css, "No artificial 3D rotation"


def test_fonts_ship_with_their_licenses_and_reach_the_image():
    code = Path(ui.APP).parents[1]
    fonts = Path(ui.APP).with_name("static") / "fonts"
    assert sorted(f.name for f in fonts.iterdir()) == [
        "google-sans-italic.woff2",
        "google-sans.OFL.txt",
        "google-sans.woff2",
    ]
    for name in ("google-sans.woff2", "google-sans-italic.woff2"):
        assert (fonts / name).read_bytes()[:4] == b"wOF2" and (fonts / name).stat().st_size < 80_000
    assert "SIL Open Font License" in (fonts / "google-sans.OFL.txt").read_text(encoding="utf-8")
    css = STYLES.read_text(encoding="utf-8")
    assert css.count('font-family: "Google Sans";') == 2 and css.count("font-display: swap") == 2
    assert SHARED["font-ui"].startswith('"Google Sans"') and "Inter" not in SHARED["font-ui"]
    dockerfile = (code.parent / "deploy/interface/Dockerfile").read_text(encoding="utf-8")
    assert "COPY code/src/static/ ./src/static/" in dockerfile
    assert "STREAMLIT_SERVER_ENABLE_STATIC_SERVING=true" in dockerfile


def test_no_font_or_image_is_requested_from_the_network():
    assert "http" not in re.sub(r"/\*.*?\*/", "", stylesheet(), flags=re.S)


def test_no_state_claims_validation_or_validity(controlled):
    at, fake = ui.start(controlled)
    fake.events = [ui.normative()]
    ui.send(at)
    text = ui.visible(at)
    for claim in ("Resposta fundamentada", "Em vigor", "fonte validada", "Fonte citada"):
        assert claim not in text


# Copy action


def test_copy_carries_the_stored_answer_exactly():
    content = 'Linha "um" <b>x</b> & R$ 1\n\n| a | b |\r\nfim  '
    view = _CopyView(copy_markup(content))
    assert view.copied == content
    assert "\n" not in copy_markup(content), "A blank line would reopen Markdown parsing"
    assert view.bold_elements == 0


@pytest.mark.parametrize(
    "factory, expected",
    [
        (ui.normative, 1),
        (lambda: ui.normative("CLARIFICATION"), 1),
        (lambda: ChatMessage(type="ai", content="Direta."), 1),
        (lambda: ui.normative("ERROR"), 0),
    ],
)
def test_copy_is_offered_on_delivered_text_only(controlled, factory, expected):
    at, fake = ui.start(controlled)
    message = factory()
    fake.events = [message]
    ui.send(at)
    blocks = [m.value for m in at.chat_message[-1].markdown if "ufpi-copy" in m.value]
    assert len(blocks) == expected
    if expected:
        assert _CopyView(blocks[0]).copied == message.content
    assert not [m.value for m in at.chat_message[0].markdown if "ufpi-copy" in m.value]


class _CopyView(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.copied, self.bold_elements = None, 0
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        if tag == "button":
            self.copied = dict(attrs)["data-copy"]
        if tag == "b":
            self.bold_elements += 1


def test_jump_to_latest_and_home_top_are_static_and_cleaned_up():
    bridge = (Path(ui.APP).with_name("chat_ui") / "bridge.js").read_text(encoding="utf-8")
    # The copy button's label is the only text the bridge writes, and only fixed strings.
    for forbidden in ("innerHTML", "eval(", "new Function", "fetch(", "localStorage"):
        assert forbidden not in bridge
    assert 'jump.type = "button"' in bridge
    assert 'setAttribute("aria-label", "Ir para a mensagem mais recente")' in bridge
    assert "jump.remove()" in bridge and "resized.disconnect()" in bridge
    assert "cancelAnimationFrame(jumpFrame)" in bridge
    assert "HOME_SETTLE_MS = 3000" in bridge and "homeTouched" in bridge
    styles = (Path(ui.APP).with_name("chat_ui") / "styles.css").read_text(encoding="utf-8")
    assert ".ufpi-jump.is-visible" in styles and "visibility: hidden" in styles


def test_two_controls_in_one_rerun_send_one_question_and_record_only_it(controlled):
    at, fake = ui.start(controlled)
    fake.error = RuntimeError("UNSAFE")
    ui.send(at, "Primeira")
    fake.error = None
    retry = next(b for b in at.button if b.key == "retry_turn")
    at.chat_input[0].set_value("Pergunta digitada")
    retry.click()
    at.run(timeout=15)
    ui.settle(at)
    assert not at.exception
    sent = [c["message"] for c in fake.calls][1:]
    asked = [m.content for m in at.session_state.messages if m.type == "human"]
    assert len(sent) == 1, sent
    assert asked[0] == "Primeira" and sent[0] in ("Primeira", "Pergunta digitada")
    if sent[0] == "Primeira":
        assert asked == ["Primeira"], "The other question is not recorded unsent"
    else:
        assert asked == ["Primeira", "Pergunta digitada"]


def test_progress_label_shimmers_and_stops_with_reduced_motion(controlled, monkeypatch):
    css = STYLES.read_text(encoding="utf-8")
    rule = css.split(".ufpi-progress-label {", 1)[1].split("}", 1)[0]
    assert "animation: ufpi-shimmer" in rule and "background-clip: text" in rule
    reduced = css.split("@media (prefers-reduced-motion: reduce), (forced-colors: active) {", 1)[1]
    assert "animation: none" in reduced.split("}\n}", 1)[0]
    for theme in (LIGHT, DARK):
        surface = theme["c-bg"]
        # Every colour the letters take while the band passes stays readable (WCAG G18).
        for stop in ("shimmer-base", "shimmer-light"):
            assert _contrast(theme[stop], surface) >= 4.5, (stop, theme[stop], surface)
    at, fake = ui.start(controlled)
    seen = {}
    markdown = Mock(wraps=st.markdown)
    monkeypatch.setattr(st, "markdown", markdown)
    original = fake.astream

    async def observing(**kwargs):
        seen["label"] = any("ufpi-progress-label" in str(c.args) for c in markdown.call_args_list)
        async for event in original(**kwargs):
            yield event

    fake.astream = observing
    ui.send(at)
    assert seen == {"label": True}
    assert not any(
        "ufpi-progress-label" in m.value for m in at.markdown if "<style>" not in m.value
    )


def test_identity_lives_only_in_the_sidebar_card(controlled):
    at, _ = ui.start(controlled)
    page = " ".join(m.value for m in at.main.markdown if "<style>" not in m.value)
    assert "ufpi-topbar" not in page and "ufpi-brand" not in page, "No floating copy on the page"
    assert sum("ufpi-brand" in m.value for m in at.sidebar.markdown) == 1
    assert "topbar" not in STYLES.read_text(encoding="utf-8")


def test_a_sent_question_keeps_the_conversation_at_its_end_until_the_reader_moves_up():
    bridge = (Path(ui.APP).with_name("chat_ui") / "bridge.js").read_text(encoding="utf-8")
    keep = bridge.split("function keepTurnEnd()", 1)[1].split("\n}\n", 1)[0]
    assert "noteTurn()" in keep and "following" in keep and "turnInProgress()" in keep
    observer = bridge.split("new MutationObserver(() => {", 1)[1].splitlines()[1]
    assert "noteTurn();" in observer, "The turn is noted before any later gesture"
    assert "scroller.scrollTop = end" in keep
    assert "setTimeout" not in keep and "smooth" not in keep, "Instant, driven by layout changes"
    note = bridge.split("function noteTurn()", 1)[1].split("\n}\n", 1)[0]
    assert "following = true" in note and "armPresentation()" in note
    # Moving up (wheel, keys, touch, scroll bar) stops following; the end, or the button, resumes.
    assert "event.deltaY < 0" in bridge and '"PageUp"' in bridge and '"touchmove"' in bridge
    scroll = bridge.split("function readScroll(event)", 1)[1].split("\n}\n", 1)[0]
    assert "stopFollowing()" in scroll and "following = true" in scroll
    jump = bridge.split("function goToLatest()", 1)[1].split("\n}\n", 1)[0]
    assert "following = true" in jump and '"scrollend"' in jump
    home = bridge.split("function touchHome(event)", 1)[1].split("\n}\n", 1)[0]
    assert "following" not in home, "A click (opening an article) is not a request to stop"
    assert "lastInputAt" in home and "pointerHeld = true" in home
    scroll_rule = bridge.split("function readScroll(event)", 1)[1].split("\n}\n", 1)[0]
    assert "byReader" in scroll_rule, "The browser's own clamping is not the reader moving up"
    for name in ("readUpGesture", "readTouch", "readScroll"):
        added = bridge.count(f", {name}, {{ capture: true, passive: true }})")
        removed = bridge.count(f", {name}, {{ capture: true }})")
        assert added == removed >= 1, (name, added, removed)


def _blocks(node):
    for child in getattr(node, "children", {}).values():
        yield child
        yield from _blocks(child)


def test_answer_text_sits_in_its_own_block_for_the_presentation(controlled):
    at, fake = ui.start(controlled)
    fake.events = [ChatMessage(type="ai", content="Resposta validada.")]
    ui.send(at)
    blocks = [b for b in _blocks(at.main) if str(getattr(b.proto, "id", "")).endswith("-ans_1")]
    assert len(blocks) == 1, "Only the answer text, keyed by its position"
    assert [m.value for m in blocks[0].markdown] == ["Resposta validada."]
    keys = [str(getattr(b.proto, "id", "")) for b in _blocks(at.main)]
    assert not any(k.endswith("-ans_0") for k in keys), "The question is never presented"


PRESENTATION = Path(ui.APP).with_name("chat_ui") / "presentation.js"


def test_presentation_is_bundled_after_the_bridge_and_reads_only_the_rendered_page():
    app = Path(ui.APP).read_text(encoding="utf-8")
    assert '("bridge.js", "presentation.js", "transition.js", "character.js")' in app
    assert "sleep(" not in app and "write_stream" not in app, "The server never delays text"
    script = PRESENTATION.read_text(encoding="utf-8")
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "fetch(", "Storage"):
        assert forbidden not in script, forbidden
    bridge = (Path(ui.APP).with_name("chat_ui") / "bridge.js").read_text(encoding="utf-8")
    observer = bridge.split("new MutationObserver(() => {", 1)[1].split("if (scheduled) return;")[0]
    assert "presentFreshAnswer();" in observer, "Held before the browser paints what was inserted"


def test_presentation_builds_a_growing_copy_and_holds_later_parts_without_space():
    script = PRESENTATION.read_text(encoding="utf-8")
    build = script.split("function buildAnswerCopy(state)", 1)[1].split("\n}\n", 1)[0]
    # The copy grows by appending nodes and words: the layout is never sized for the whole text.
    assert "cloneNode(false)" in build and "appendData(part)" in build
    assert "cloneNode(true)" not in script, "Never a full copy laid out in advance"
    assert '"aria-hidden", "true"' in build and '"inert"' in build, "Read once, from the original"
    assert 'removeAttribute("id")' in build
    assert 'setAttribute("data-ufpi-held"' in build
    css = STYLES.read_text(encoding="utf-8")
    assert "[data-ufpi-wait] { display: none !important; }" in css
    held = css.split("[data-ufpi-held] {", 1)[1].split("}", 1)[0]
    assert "position: absolute" in held and "clip-path: inset(50%)" in held
    assert "opacity" not in held and "visibility" not in held
    assert ".ufpi-word" not in css and "ufpi-revealing" not in css


def test_sources_enter_after_the_text_heading_hint_norm_and_each_article_in_order():
    script = PRESENTATION.read_text(encoding="utf-8")
    begin = script.split("function beginSources(state, now)", 1)[1].split("\n}\n", 1)[0]
    assert begin.index('removeAttribute("data-ufpi-held")') < begin.index("laterParts(state)")
    assert '"details.ufpi-sources[open]"' in begin
    assert '".ufpi-sources-hint, .ufpi-norm, .ufpi-ref"' in begin, (
        "Page order: hint, norm, articles"
    )
    assert "PRESENT_STEPS_MS / " in begin, "Spacing adapts to the number of parts"
    frame = script.split("function presentFrame(now)", 1)[1].split("\n}\n", 1)[0]
    assert frame.index("REVEALING_ANSWER") < frame.index("beginSources(state, now)")
    assert "keepTurnEnd();" in frame, "The end follows what has just become visible"
    later = script.split("function laterParts(state)", 1)[1].split("\n}\n", 1)[0]
    assert '".ufpinho-chat"' in later, "The figure, the transition's destination, is never held"


def test_presentation_runs_once_for_a_new_answer_and_always_completes():
    script = PRESENTATION.read_text(encoding="utf-8")
    arm = script.split("function armPresentation()", 1)[1].split("\n}\n", 1)[0]
    assert "if (stillMotion.matches) return;" in arm, "Reduced motion: everything at once"
    assert arm.index("completePresentation();") < arm.index("armed = {"), "A new question ends it"
    # Only the AI message right after the sent question, in the conversation it was sent in.
    assert "Math.max(...questions) + 1" in arm
    assert "st-key-msg_ai_${index}" in arm and "st-key-ans_${index}" in arm
    assert "conversation: activeConversation()" in arm
    fresh = script.split("function presentFreshAnswer()", 1)[1].split("\n}\n", 1)[0]
    window = fresh.index("armed.until && now > armed.until")
    assert window < fresh.index("const box ="), "The window is checked before any candidate"
    assert "activeConversation() !== armed.conversation" in fresh
    assert "disarmPresentation()" in fresh
    # Notes stated before the text wait for it, and are shown if the message ends without text.
    assert '".ufpi-note"' in fresh and '".ufpinho-chat"' in fresh
    assert "PRESENT_NOTES_MS" in fresh
    disarm = script.split("function disarmPresentation()", 1)[1].split("\n}\n", 1)[0]
    assert 'removeAttribute("data-ufpi-wait")' in disarm
    intact = script.split("function presentationIntact(state)", 1)[1].split("\n}\n", 1)[0]
    assert "isConnected" in intact and 'hasAttribute("data-ufpi-held")' in intact
    assert "textContent === state.text" in intact, "Nodes reused for another text end it"
    assert "activeConversation() === state.conversation" in intact
    assert "!stillMotion.matches" in intact, "Reduced motion turned on midway ends it"
    done = script.split("function completePresentation()", 1)[1].split("\n}\n", 1)[0]
    for step in (
        "cancelAnimationFrame",
        'removeEventListener("click", completeOnInteraction, true)',
        'querySelectorAll("[data-ufpi-wait], [data-ufpi-held]")',
        'querySelectorAll("[data-ufpi-copy-of]")',
    ):
        assert step in done, step
    assert 'stillMotion.addEventListener("change", presentStill)' in script
    assert 'stillMotion.removeEventListener("change", presentStill)' in script
    interaction = script.split("function completeOnInteraction(event)", 1)[1].split("\n}\n", 1)[0]
    assert "REVEALING_SOURCES" in interaction and "completePresentation()" in interaction


def test_entering_parts_stay_still_with_reduced_motion():
    css = STYLES.read_text(encoding="utf-8")
    assert "[data-ufpi-enter] { animation: ufpi-enter" in css
    reduced = css.split("@media (prefers-reduced-motion: reduce), (forced-colors: active) {", 1)[1]
    assert "[data-ufpi-enter] { animation: none; }" in reduced.split("\n}\n", 1)[0]
