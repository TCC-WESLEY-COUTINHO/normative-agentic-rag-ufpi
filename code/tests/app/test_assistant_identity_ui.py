"""The prototype presents fixed identity replies as ordinary text without sources."""

import test_tcc_ui as ui

from rag_baseline.assistant_identity import assistant_identity_reply
from schema import ChatMessage

controlled = ui.controlled


def test_identity_reply_renders_without_normative_sources(controlled):
    at, fake = ui.start(controlled)
    reply = assistant_identity_reply("Quem é você?")
    fake.events = [ChatMessage(type="ai", content=reply.content)]
    ui.send(at, "Quem é você?")
    assert not at.exception
    assert reply.content in ui.visible(at)
    assert "Fontes normativas" not in ui.visible(at)
    assert "Trechos consultados" not in ui.visible(at)
    assert at.session_state.messages[-1].normative_result is None
