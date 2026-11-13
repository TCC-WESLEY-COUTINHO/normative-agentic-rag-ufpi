"""Article presentation, direct delivery of the validated message and own-anchor scroll."""

from collections import Counter
from unittest.mock import Mock

import pytest
import streamlit as st
import streamlit.components.v1 as components
import test_tcc_ui as ui

from schema import ChatMessage

controlled = ui.controlled


def scroll_scripts(html):
    return [
        c.args[0]
        for c in html.call_args_list
        if "scrollIntoView" in c.args[0]
        or "scroller.scrollTop = scroller.scrollHeight" in c.args[0]
    ]


def test_each_structural_reference_is_an_independent_closed_article(controlled):
    at, fake = ui.start(controlled)
    source = ui.normative().normative_result
    first = source.references[0].model_copy(update={"evidence_text": "Texto inteiro.\nRegra A."})
    second = first.model_copy(update={"chunk_id": "other-identity", "evidence_text": "Regra B."})
    third = source.references[1].model_copy(update={"evidence_text": "Regra C."})
    refs = [first, second, third, first]
    value = source.model_copy(update={"references": refs})
    fake.events = [ChatMessage(type="ai", content=value.answer, normative_result=value)]
    before = [r.model_dump() for r in refs]
    ui.send(at)
    view = ui.sources(at)
    assert [entry.title for entry in view.entries] == [
        "Art. 68",
        "Art. 68",
        "Art. 68, § 1º",
        "Art. 68",
    ]
    assert view.open_details == 0
    assert Counter(entry.text for entry in view.entries) == Counter(r.evidence_text for r in refs)
    assert [r.model_dump() for r in refs] == before
    assert not any(r.chunk_id in ui.visible(at) for r in refs)
    at.run(timeout=15)
    assert len(ui.sources(at).entries) == 4


@pytest.mark.parametrize(
    "factory",
    [
        ui.normative,
        ui.grounded,
        lambda: ChatMessage(type="ai", content="Direta."),
        lambda: ui.normative("CLARIFICATION"),
        lambda: ui.normative("ERROR"),
        ui.calculator,
    ],
)
def test_the_service_delivers_one_final_message_and_no_typing_is_simulated(
    controlled, monkeypatch, factory
):
    renderer = Mock(wraps=st.write_stream)
    monkeypatch.setattr(st, "write_stream", renderer)
    at, fake = ui.start(controlled)
    message = factory()
    fake.events = [message]
    ui.send(at)
    renderer.assert_not_called()
    is_error = message.normative_result is not None and message.normative_result.status == "ERROR"
    shown = at.chat_message[-1].warning if is_error else at.chat_message[-1].markdown
    assert shown[0].value == message.content.strip()
    at.run(timeout=15)
    renderer.assert_not_called()


@pytest.mark.parametrize(
    "events",
    [
        ["UNSAFE raw"],
        [ui.normative(), ui.normative()],
        [
            ChatMessage.model_construct(
                type="ai", content="UNSAFE", normative_result={"invalid": True}
            )
        ],
    ],
)
def test_invalid_or_incomplete_stream_never_reaches_progressive_renderer(
    controlled, monkeypatch, events
):
    renderer = Mock(wraps=st.write_stream)
    monkeypatch.setattr(st, "write_stream", renderer)
    at, fake = ui.start(controlled)
    fake.events = events
    ui.send(at)
    renderer.assert_not_called()
    assert len(at.session_state.messages) == 1
    assert "UNSAFE" not in ui.visible(at)


def test_page_is_never_moved_against_streamlits_own_scroll(controlled, monkeypatch):
    """Submit places the page at the bottom; on the answer only focus is restored. Streamlit's
    container then follows the new content itself: a second mover would make the page shake."""
    html = Mock(wraps=components.html)
    monkeypatch.setattr(components, "html", html)
    at, fake = ui.start(controlled)
    opening = scroll_scripts(html)
    assert len(opening) == 1 and "getElementById('conversation-top')" in opening[0], (
        "Only the home's own top, once, so a short screen shows the figure and greeting"
    )
    fake.events = [ui.normative()]
    ui.send(at)
    scripts = scroll_scripts(html)[1:]
    assert len(scripts) == 2
    assert "getElementById('chat-bottom-anchor')" in scripts[0]
    # The conversation's own scroll container goes to its end, so the new turn is not left under
    # the pinned composer; aligning the anchor with the visible end did exactly that.
    assert "closest('section.stMain')" in scripts[0] and "scrollIntoView" not in scripts[0]
    assert "getElementById('')" in scripts[1] and "focus(" in scripts[1]
    assert any('id="chat-bottom-anchor"' in m.value for m in at.markdown)
    at.run(timeout=15)
    assert len(scroll_scripts(html)) == 3, "An ordinary rerun must not move the page"
    assert len(at.session_state.messages) == 2


def test_successful_retry_clears_the_previously_rendered_error(controlled):
    at, fake = ui.start(controlled)
    fake.error = RuntimeError("UNSAFE failure")
    ui.send(at)
    assert len(at.error) == 1
    fake.error = None
    fake.events = [ChatMessage(type="ai", content="Resposta recuperada.")]
    ui.send(at, "Tentar novamente")
    assert not at.error
    assert at.chat_message[-1].markdown[0].value == "Resposta recuperada."


def test_repeated_failure_displays_only_the_current_error(controlled):
    at, fake = ui.start(controlled)
    fake.error = RuntimeError("UNSAFE failure")
    ui.send(at)
    ui.send(at, "Outra tentativa")
    assert len(at.error) == 1


def test_new_turns_emit_fresh_scroll_srcdoc_even_at_reused_component_slots(controlled, monkeypatch):
    html = Mock(wraps=components.html)
    monkeypatch.setattr(components, "html", html)
    at, fake = ui.start(controlled)
    opening = len(scroll_scripts(html))
    ui.send(at)
    first = scroll_scripts(html)[opening:]
    ui.send(at, "Nova pergunta")
    second = scroll_scripts(html)[opening + 2 :]
    assert len(first) == len(second) == 2
    assert all(old != new for old, new in zip(first, second)), (
        "same iframe srcdoc may not execute again"
    )


def test_long_validated_answer_is_shown_whole_and_stored_exactly(controlled):
    at, fake = ui.start(controlled)
    text = "  Texto final validado com **formatação** e acentuação.\n\n" * 120
    result = ui.normative().normative_result.model_copy(update={"answer": text})
    fake.events = [ChatMessage(type="ai", content=text, normative_result=result)]
    ui.send(at)
    # Native Markdown removes common paragraph indentation; stored text stays exact.
    assert (
        at.chat_message[-1].markdown[0].value
        == ("Texto final validado com **formatação** e acentuação.\n\n" * 120).strip()
    )
    assert at.session_state.messages[-1].content == text
