"""Entrypoint regressions updated for the TCC single-agent product contract."""

from pathlib import Path
from unittest.mock import Mock

import test_tcc_ui as ui
from streamlit.testing.v1 import AppTest

from client import AgentClient, AgentClientError
from schema import ChatMessage

APP = Path(__file__).resolve().parents[2] / "src/streamlit_app.py"
AGENT = "chatbot_ufpi_integrated_v1"


def app():
    return AppTest.from_file(str(APP)).run(timeout=15)


def respond(mock, messages):
    async def events(**kwargs):
        for message in messages:
            yield message

    mock.astream = Mock(side_effect=events)


def test_app_complete_stream_message(mock_agent_client):
    respond(mock_agent_client, [ChatMessage(type="ai", content="Resposta completa.")])
    at = app()
    ui.send(at, "Olá")
    assert not at.exception
    assert [m.content for m in at.session_state.messages] == ["Olá", "Resposta completa."]
    mock_agent_client.update_agent.assert_called_with(AGENT, verify=False)
    mock_agent_client.astream.assert_called_once_with(
        message="Olá", thread_id=at.session_state.thread_id, user_id=at.session_state.user_id
    )
    mock_agent_client.ainvoke.assert_not_called()


def test_app_has_no_agent_or_model_settings(mock_agent_client):
    at = app()
    assert not at.exception
    assert not at.selectbox and not at.radio and not at.toggle
    assert at.sidebar.button[0].label == "Nova conversa"
    assert any("Olá! Eu sou o" in m.value and "ufpi-greeting" in m.value for m in at.markdown)


def test_app_does_not_restore_legacy_history(mock_agent_client):
    at = AppTest.from_file(str(APP))
    at.query_params["thread_id"] = "legacy-thread"
    at.run(timeout=15)
    assert at.session_state.thread_id != "legacy-thread"
    assert at.session_state.messages == []
    mock_agent_client.get_history.assert_not_called()


def test_app_no_remote_feedback_or_share(mock_agent_client):
    respond(mock_agent_client, [ChatMessage(type="ai", content="Olá!")])
    at = app()
    ui.send(at, "Oi")
    labels = " ".join(button.label for button in at.button).lower()
    assert "feedback" not in labels and "compartilhar" not in labels
    assert not at.chat_message[-1].button
    mock_agent_client.acreate_feedback.assert_not_called()


def test_app_network_failure_safe(mock_agent_client):
    async def fail(**kwargs):
        raise AgentClientError("UNSAFE URL and secret")
        yield

    mock_agent_client.astream = Mock(side_effect=fail)
    at = app()
    ui.send(at, "Oi")
    assert not at.exception
    assert "Não foi possível obter" in at.error[0].value
    assert "UNSAFE" not in at.error[0].value


def test_app_done_is_consumed_by_real_client_parser(mock_agent_client):
    parser = AgentClient.__new__(AgentClient)
    # AgentClient is patched by the fixture: import its original implementation.
    from client.client import AgentClient as RealClient

    parser = RealClient(get_info=False)
    lines = [
        'data: {"type":"message","content":{"type":"ai","content":"Final único."}}',
        "data: [DONE]",
    ]
    events = [event for line in lines if (event := parser._parse_stream_line(line)) is not None]
    respond(mock_agent_client, events)
    at = app()
    ui.send(at, "Oi")
    assert not at.exception
    assert len(at.session_state.messages) == 2
    assert at.chat_message[-1].markdown[0].value == "Final único."
    assert "DONE" not in str([m.value for m in at.markdown])


def test_app_new_chat_clears_transient_state(mock_agent_client):
    async def fail(**kwargs):
        raise AgentClientError("UNSAFE")
        yield

    mock_agent_client.astream = Mock(side_effect=fail)
    at = app()
    ui.send(at, "Oi")
    assert at.error
    user, thread = at.session_state.user_id, at.session_state.thread_id
    at.sidebar.button[0].click().run(timeout=15)
    assert not at.exception
    assert at.session_state.user_id == user
    assert at.session_state.thread_id != thread
    assert not at.error


def test_app_sse_error_uses_safe_ux_and_is_not_an_assistant_answer(mock_agent_client):
    from client.client import AgentClient as RealClient

    parser = RealClient(get_info=False)

    async def events(**kwargs):
        event = parser._parse_stream_line(
            'data: {"type":"error","content":"UNSAFE server details"}'
        )
        yield event

    mock_agent_client.astream = Mock(side_effect=events)
    at = app()
    ui.send(at, "Oi")
    assert not at.exception
    assert len(at.session_state.messages) == 1
    assert "Não foi possível obter" in at.error[0].value
    assert "UNSAFE" not in str([m.value for m in at.markdown])
