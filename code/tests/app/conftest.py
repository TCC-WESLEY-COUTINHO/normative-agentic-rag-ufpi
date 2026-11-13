from unittest.mock import patch

import pytest

from schema import AgentInfo, ServiceMetadata
from schema.models import OpenAIModelName


@pytest.fixture
def mock_agent_client(mock_env):
    """Fixture for creating a mock AgentClient with a clean environment."""

    mock_info = ServiceMetadata(
        default_agent="test-agent",
        agents=[
            AgentInfo(key="test-agent", description="Test agent"),
            AgentInfo(key="chatbot", description="Chatbot"),
        ],
        default_model=OpenAIModelName.GPT_4O,
        models=[OpenAIModelName.GPT_4O, OpenAIModelName.GPT_4O_MINI],
    )

    with patch("client.AgentClient") as mock_agent_client:
        mock_agent_client_instance = mock_agent_client.return_value
        mock_agent_client_instance.info = mock_info
        yield mock_agent_client_instance


@pytest.fixture(autouse=True)
def isolated_ui_working_directory(tmp_path, monkeypatch):
    """App tests never read the user's real .env or credentials."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def no_real_progressive_delay(monkeypatch):
    """AppTest tests rendering, not wall-clock animation."""
    monkeypatch.setattr("rag_baseline.ui_presentation.pause", lambda seconds: None)
