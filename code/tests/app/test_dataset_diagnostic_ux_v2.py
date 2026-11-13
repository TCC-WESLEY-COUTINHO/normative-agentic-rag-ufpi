"""Frozen reveal helper stays exact; article evidence is delivered whole and on demand."""

import pytest
import test_tcc_ui as ui

from rag_baseline import ui_presentation
from schema import ChatMessage

controlled = ui.controlled


@pytest.mark.parametrize("count", [100, 200, 1200])
def test_reveal_is_word_grouped_exact_and_has_a_small_perceptible_delay(monkeypatch, count):
    pause = []
    monkeypatch.setattr(ui_presentation, "pause", pause.append)
    text = "  " + ("palavra\n" * count) + "  "
    fragments = list(ui_presentation.stream_validated_text(text))
    assert "".join(fragments) == text
    assert max(len(part.split()) for part in fragments) <= 2
    if count <= 200:
        assert 2 <= sum(pause) <= 6
    assert sum(pause) <= 6.001


def test_long_reference_is_delivered_whole_inside_its_closed_disclosure(controlled):
    at, fake = ui.start(controlled)
    source = ui.normative().normative_result
    long_text = ("Texto original com regras e condições. " * 50) + "FIM INTACTO."
    reference = source.references[0].model_copy(update={"evidence_text": long_text})
    result = source.model_copy(update={"references": [reference]})
    fake.events = [ChatMessage(type="ai", content=result.answer, normative_result=result)]
    ui.send(at)
    view = ui.sources(at)
    assert view.open_details == 0
    assert view.entries[0].text == long_text
    assert at.session_state.messages[-1].normative_result.references[0].evidence_text == long_text
