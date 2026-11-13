"""TCC UI boundaries through Streamlit's real script runner; no backend network."""

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID, uuid4

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from client import AgentClientError
from rag_baseline.calculator import calculate
from rag_baseline.calculator_contracts import ArithmeticRequest
from rag_baseline.conversation_contracts import GroundedFollowUpResult
from rag_baseline.tool_contracts import NormativeToolResult
from schema import AgentInfo, ChatMessage, ServiceMetadata

APP = Path(__file__).resolve().parents[2] / "src/streamlit_app.py"
AGENT = "chatbot_ufpi_integrated_v1"
PRIVATE = (
    "internal_audit",
    "storage_key",
    "correlation_id",
    "contract_version",
    "core_version",
    "UNSAFE",
    "dense_vector",
    "fallback",
)


def normative(status="ANSWER", core_status="accepted"):
    # Use a validated transport fixture without acquisition of a provider/index.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "ui_transport_fixture",
        Path(__file__).parents[1] / "rag_baseline/normative_facade_fixtures.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if status == "ANSWER":
        data = module.answer_data()
        second = {
            **data["references"][0],
            "chunk_id": "distinct-private-id",
            "validated_subdivision": "§ 1º",
        }
        data.update(
            answer="  Resposta com art. 999.\nTexto intacto!  ",
            core_status=core_status,
            references=[data["references"][0], second, data["references"][0]],
            internal_audit=module.audit_data(),
        )
    else:
        data = dict(
            contract_version="1",
            core_version="structured_output_v2",
            status=status,
            retrieval_strategy="dense_vector",
            correlation_id=uuid4(),
        )
        if status == "CLARIFICATION":
            data.update(
                needs_clarification=True, clarification_question="Graduação ou pós-graduação?"
            )
        else:
            data.update(
                error_code="provider_error",
                safe_message="Não foi possível consultar agora.",
                internal_audit=module.audit_data(),
            )
    value = NormativeToolResult(**data)
    content = value.answer or value.clarification_question or value.safe_message
    return ChatMessage(type="ai", content=content, normative_result=value)


def grounded(kind="SUMMARY"):
    source = normative().normative_result
    result = GroundedFollowUpResult(
        kind=kind,
        content="Reformulação controlada.",
        source_correlation_id=source.correlation_id,
        source_core_version=source.core_version,
        source_contract_version="1",
        references=source.references,
        temporal_provenance=source.temporal_provenance,
        domain=source.domain,
        guard_status="FALLBACK_TO_SOURCE",
    )
    return ChatMessage(type="ai", content=result.content, grounded_followup_result=result)


def calculator(expression="2+2"):
    result = calculate(ArithmeticRequest(expression=expression))
    return ChatMessage(type="ai", content=result.content, calculator_result=result)


@pytest.fixture
def controlled(monkeypatch, mock_env):
    import client

    class FakeClient:
        def __init__(self, **kwargs):
            self.agent = None
            self.info = ServiceMetadata(
                default_agent="chatbot_ufpi_v2",
                agents=[
                    AgentInfo(key="chatbot_ufpi_v2", description="Legacy"),
                    AgentInfo(key=AGENT, description="Integrated"),
                ],
                default_model="gpt-4o",
                models=["gpt-4o"],
            )
            self.init_kwargs = kwargs
            self.calls = []
            self.events = [ChatMessage(type="ai", content="Olá!")]
            self.error = None
            self.get_history = Mock(
                side_effect=AssertionError("history is outside this UI contract")
            )
            instances.append(self)
            if kwargs.get("agent"):
                self.agent = kwargs["agent"]

        def update_agent(self, agent, verify=True):
            self.agent = agent

        async def astream(self, **kwargs):
            self.calls.append({"agent": self.agent, **kwargs})
            if self.error:
                raise self.error
            for event in self.events:
                yield event

    instances = []
    monkeypatch.setattr(client, "AgentClient", FakeClient)
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    return instances


def start(controlled):
    at = AppTest.from_file(str(APP)).run(timeout=15)
    assert not at.exception
    return at, controlled[0]


def send(at, text="Pergunta"):
    at.chat_input[0].set_value(text).run(timeout=15)
    assert not at.exception


@dataclass
class SourceEntry:
    norm: str
    title: str = ""
    tags: list = field(default_factory=list)
    text: str | None = None
    missing: str = ""


class SourcesView(HTMLParser):
    """Reads the delivered markup the way a browser would, including its escaping."""

    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.summary = self.hint = ""
        self.norms, self.entries, self.open_details = [], [], 0
        self.sources_open = False
        self.script_or_bold_elements = 0
        self._target = None
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        kind = attrs.get("class", "")
        if tag == "details" and "open" in attrs:
            if kind == "ufpi-ref":
                self.open_details += 1
            else:
                self.sources_open = True
        if tag in ("script", "b", "img", "style"):
            self.script_or_bold_elements += 1
        if kind == "ufpi-norm-title":
            self._target = "norm"
            self.norms.append("")
        elif kind == "ufpi-ref":
            self.entries.append(SourceEntry(norm=self.norms[-1]))
        elif kind in ("ufpi-sources-title", "ufpi-sources-count"):
            self._target = "summary"
        elif kind == "ufpi-sources-hint":
            self._target = "hint"
        elif kind == "ufpi-ref-title":
            self._target = "title"
        elif kind == "ufpi-ref-tag":
            self.entries[-1].tags.append("")
            self._target = "tag"
        elif kind == "ufpi-ref-label":
            self._target = None
        elif kind == "ufpi-ref-text":
            self.entries[-1].text = ""
            self._target = "text"
        elif kind == "ufpi-ref-missing":
            self._target = "missing"

    def handle_endtag(self, tag):
        if tag in ("p", "div", "span"):
            self._target = None

    def handle_data(self, data):
        if self._target == "norm":
            self.norms[-1] += data
        elif self._target == "summary":
            self.summary += data + " "
        elif self._target == "hint":
            self.hint += data
        elif self._target == "title":
            self.entries[-1].title += data
        elif self._target == "tag":
            self.entries[-1].tags[-1] += data
        elif self._target == "text":
            self.entries[-1].text += data
        elif self._target == "missing":
            self.entries[-1].missing += data


def sources(at, message=-1):
    """The single source region of a message, or None when it has no typed references."""
    blocks = [
        m.value for m in at.chat_message[message].markdown if 'class="ufpi-sources"' in m.value
    ]
    assert len(blocks) <= 1, "A message has one source region at most"
    return SourcesView(blocks[0]) if blocks else None


def visible(at):
    return "\n".join(
        str(x.value)
        for category in (at.markdown, at.caption, at.error, at.warning, at.text)
        for x in category
    )


def test_fixed_agent_and_no_selector(controlled):
    at, fake = start(controlled)
    send(at)
    assert fake.calls[0]["agent"] == AGENT
    assert not at.selectbox and not at.radio
    assert "model" not in fake.calls[0]
    assert not fake.get_history.called


def test_direct_and_complete_message_once(controlled):
    at, fake = start(controlled)
    send(at, "Oi")
    assert [m.content for m in at.session_state.messages] == ["Oi", "Olá!"]
    assert at.chat_message[-1].markdown[0].value == "Olá!"
    assert sources(at) is None
    assert "[DONE]" not in visible(at)


@pytest.mark.parametrize("core_status", ["accepted", "regenerated", "fallback"])
def test_normative_exact_content_typed_sources_and_rerun(controlled, core_status):
    at, fake = start(controlled)
    message = normative(core_status=core_status)
    original = message.model_dump()
    fake.events = [message]
    send(at)
    # Streamlit itself strips outer whitespace in its Markdown protobuf.
    assert at.chat_message[-1].markdown[0].value == message.content.strip()
    view = sources(at)
    assert view.open_details == 0, "Sources start closed and never force themselves open"
    assert len(view.entries) == 3
    titles = "\n".join(entry.title for entry in view.entries)
    assert "Art. 68" in titles and "§ 1º" in titles and "999" not in titles
    assert message.model_dump() == original
    for private in PRIVATE:
        assert private not in visible(at)
    at.run(timeout=15)
    assert isinstance(at.session_state.messages[-1], ChatMessage)
    assert (
        at.session_state.messages[-1].normative_result.references
        == message.normative_result.references
    )
    assert len(sources(at).entries) == 3


@pytest.mark.parametrize("status", ["CLARIFICATION", "ERROR"])
def test_normative_nonanswer_safe_no_empty_sources(controlled, status):
    at, fake = start(controlled)
    fake.events = [normative(status)]
    send(at)
    assert fake.events[0].content in visible(at)
    assert sources(at) is None
    assert status not in visible(at)
    for private in PRIVATE:
        assert private not in visible(at)


@pytest.mark.parametrize("kind", ["REPEAT", "REPHRASE", "SUMMARY"])
def test_grounded_inherits_typed_sources(controlled, kind):
    at, fake = start(controlled)
    fake.events = [grounded(kind)]
    send(at)
    assert "Reformulação controlada." in visible(at)
    assert "resposta normativa anterior" in visible(at)
    assert any("Art. 68" in entry.title for entry in sources(at).entries)
    assert "nova consulta" not in visible(at)
    for private in PRIVATE:
        assert private not in visible(at)


@pytest.mark.parametrize(
    "expression, expected", [("2+2", "4"), ("1/0", "Não é possível dividir por zero.")]
)
def test_calculator_no_normative_information(controlled, expression, expected):
    at, fake = start(controlled)
    fake.events = [calculator(expression)]
    send(at)
    assert expected in visible(at)
    assert sources(at) is None
    assert "division_by_zero" not in visible(at)


def test_thread_continuity_new_conversation_and_transient_reset(controlled):
    at, fake = start(controlled)
    user, thread = at.session_state.user_id, at.session_state.thread_id
    UUID(user)
    UUID(thread)
    fake.events = [normative("CLARIFICATION")]
    send(at)
    send(at, "Graduação")
    assert [c["thread_id"] for c in fake.calls] == [thread, thread]
    assert all(c["user_id"] == user for c in fake.calls)
    at.sidebar.button[0].click().run(timeout=15)
    assert at.session_state.thread_id != thread
    assert at.session_state.user_id == user
    assert at.session_state.messages == []
    send(at)
    assert fake.calls[-1]["thread_id"] == at.session_state.thread_id
    assert fake.calls[-1]["agent"] == AGENT


def test_legacy_state_migrated_once_ignores_query_identity(controlled):
    at = AppTest.from_file(str(APP))
    old_user = str(uuid4())
    at.session_state["user_id"] = old_user
    at.session_state["thread_id"] = "legacy-thread"
    at.session_state["messages"] = [ChatMessage(type="ai", content="OLD PRIVATE")]
    at.query_params.update(agent="chatbot_ufpi_v2", thread_id="unsafe", user_id="shared-id")
    at.run(timeout=15)
    assert not at.exception
    new_thread = at.session_state.thread_id
    UUID(new_thread)
    assert at.session_state.user_id == old_user
    assert at.session_state.messages == []
    assert "OLD PRIVATE" not in visible(at)
    at.run(timeout=15)
    assert at.session_state.thread_id == new_thread
    assert not controlled[0].get_history.called


@pytest.mark.parametrize("status", [503, 500])
def test_http_failure_safe_without_fallback(controlled, status):
    at, fake = start(controlled)
    request = httpx.Request("POST", "http://local/private")
    cause = httpx.HTTPStatusError(
        "UNSAFE secret", request=request, response=httpx.Response(status, request=request)
    )
    error = AgentClientError("UNSAFE exception")
    error.__cause__ = cause
    fake.error = error
    send(at)
    assert (
        "temporariamente indisponível" if status == 503 else "Não foi possível obter"
    ) in visible(at)
    assert len(fake.calls) == 1 and fake.calls[0]["agent"] == AGENT
    assert "UNSAFE" not in visible(at)
    assert len(at.session_state.messages) == 1
    at.sidebar.button[0].click().run(timeout=15)
    assert not at.error


@pytest.mark.parametrize(
    "event",
    ["legacy token", ChatMessage(type="tool", content="UNSAFE tool"), {"content": "UNSAFE object"}],
)
def test_unexpected_stream_payload_is_controlled(controlled, event):
    at, fake = start(controlled)
    fake.events = [event]
    send(at)
    assert "Não foi possível obter" in visible(at)
    assert "UNSAFE" not in visible(at)
    assert len(at.session_state.messages) == 1


def test_invalid_multiple_typed_results_rejected_by_existing_schema(controlled):
    at, fake = start(controlled)
    payload = normative().model_dump()
    payload["calculator_result"] = calculator().calculator_result.model_dump()
    fake.events = [ChatMessage.model_construct(**payload)]
    send(at)
    assert "Não foi possível obter" in visible(at)
    assert len(at.session_state.messages) == 1


def test_duplicate_final_events_rejected_before_rendering(controlled):
    at, fake = start(controlled)
    fake.events *= 2
    send(at)
    assert "Não foi possível obter" in visible(at)
    assert len(at.session_state.messages) == 1


def test_backend_default_still_v2():
    from agents.agents import DEFAULT_AGENT

    assert DEFAULT_AGENT == "chatbot_ufpi_v2"


def test_local_dotenv_configures_url_and_auth(controlled, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENT_URL", raising=False)
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    (tmp_path / ".env").write_text(
        "AGENT_URL=http://configured.local:1234\nAUTH_SECRET=controlled-auth-placeholder\n",
        encoding="utf-8",
    )
    at, fake = start(controlled)
    assert fake.init_kwargs["base_url"] == "http://configured.local:1234"
    from client.client import AgentClient as RealClient

    assert RealClient(get_info=False).auth_secret == "controlled-auth-placeholder"
    assert not at.exception


def test_process_environment_precedes_dotenv(controlled, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENT_URL", "http://explicit.local:4321")
    (tmp_path / ".env").write_text("AGENT_URL=http://ignored.local:1234\n", encoding="utf-8")
    at, fake = start(controlled)
    assert fake.init_kwargs["base_url"] == "http://explicit.local:4321"
