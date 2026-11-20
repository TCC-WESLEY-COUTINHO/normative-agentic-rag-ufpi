"""Local cancellation, recovery and accessibility regressions from the UX audit."""

import asyncio
from pathlib import Path
from threading import Event

import pytest
import streamlit.components.v1 as components
import test_tcc_ui as ui
from test_chat_shell import _contrast, by_key, contents

from chat_ui.requests import ResponseWait
from chat_ui.theme import DARK, LIGHT, SHARED
from rag_baseline.calculator_contracts import SAFE_MESSAGES, CalculatorToolResult
from rag_baseline.tool_contracts import ToolErrorCode
from schema import ChatMessage

controlled = ui.controlled


def test_cancel_releases_controls_retains_question_and_discards_late_response(controlled):
    at, fake = ui.start(controlled)
    closed = Event()
    original = fake.astream

    async def delayed(**kwargs):
        fake.calls.append(kwargs)
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            # A response already produced by a service must never revive a cancelled turn.
            yield ChatMessage(type="ai", content="UNSAFE resposta tardia")
        finally:
            closed.set()

    fake.astream = delayed
    at.chat_input[0].set_value("Pergunta preservada").run(timeout=15)
    wait = at.session_state.response_wait
    assert at.chat_input[0].proto.disabled
    cancel = by_key(at, "cancel_turn")
    assert cancel.label == "Parar" and not cancel.proto.disabled
    assert cancel.proto.help == "Parar"
    cancel.click().run(timeout=15)
    assert not at.exception
    assert not at.chat_input[0].proto.disabled
    assert "response_wait" not in at.session_state and "in_flight" not in at.session_state
    assert contents(at) == ["Pergunta preservada"]
    assert "A espera foi cancelada" in ui.visible(at)
    assert "O serviço pode continuar processando" in ui.visible(at)
    assert closed.wait(1)
    wait._thread.join(timeout=1)
    fake.astream = original
    ui.send(at, "Nova pergunta")
    assert contents(at) == ["Pergunta preservada", "Nova pergunta", "Olá!"]
    assert "A espera foi cancelada" in ui.visible(at)
    assert "UNSAFE" not in ui.visible(at)
    assert not at.error
    thread_id = at.session_state.thread_id
    by_key(at, "new_conversation").click().run(timeout=15)
    by_key(at, f"conv_open_idle_{thread_id}").click().run(timeout=15)
    assert "A espera foi cancelada" in ui.visible(at)


def test_wait_keeps_footer_structure_and_elapsed_time_inside_progress(controlled):
    at, fake = ui.start(controlled)
    ui.send(at, "Primeira pergunta")
    idle_bottom = at._tree[3]
    idle_captions = [c.value for c in at.caption if "Tempo de espera" in c.value]

    async def delayed(**kwargs):
        await asyncio.sleep(60)
        yield ChatMessage(type="ai", content="Resposta")

    at.session_state.agent_client.astream = delayed
    at.chat_input[0].set_value("Segunda pergunta").run(timeout=15)
    try:
        assert not at.exception
        assert "response_wait" in at.session_state, contents(at)
        markup = ui.visible(at)
        assert "Você pode cancelar a espera" not in markup
        assert not [c for c in at.caption if "Tempo de espera" in c.value]
        progress = next(m.value for m in at.markdown if 'class="ufpi-progress"' in m.value)
        assert 'class="ufpi-progress-elapsed"' in progress and "0 s" in progress
        assert by_key(at, "cancel_turn").label == "Parar"
        # The footer has the same top-level nodes; the stop control lives in an
        # always-present, out-of-flow container next to the composer.
        assert len(at._tree[3].children) == len(idle_bottom.children)
        assert not idle_captions
        assert "response_controls" not in str(at._tree[3])
        at.session_state.response_wait.started -= 36
        at.run(timeout=15)
        progress = next(m.value for m in at.markdown if 'class="ufpi-progress"' in m.value)
        assert "36 s" in progress
    finally:
        if "response_wait" in at.session_state:
            by_key(at, "cancel_turn").click().run(timeout=15)
    assert by_key(at, "cancel_turn").proto.disabled


def test_cancel_wins_when_result_finishes_before_the_next_poll(controlled):
    at, fake = ui.start(controlled)
    release = Event()

    async def delayed(**kwargs):
        while not release.is_set():
            await asyncio.sleep(0.01)
        yield ChatMessage(type="ai", content="UNSAFE pronta mas cancelada")

    fake.astream = delayed
    at.chat_input[0].set_value("Corrida").run(timeout=15)
    wait = at.session_state.response_wait
    release.set()
    wait._thread.join(timeout=1)
    assert wait.result.done()
    by_key(at, "cancel_turn").click().run(timeout=15)
    assert contents(at) == ["Corrida"]
    assert "Consulta cancelada" in ui.visible(at) and "UNSAFE" not in ui.visible(at)


def test_timeout_releases_ui_even_if_the_worker_ignores_cancellation(controlled, monkeypatch):
    monkeypatch.setattr("chat_ui.conversations.RESPONSE_TIMEOUT_SECONDS", 0.1)
    at, fake = ui.start(controlled)
    release = Event()

    async def stubborn(**kwargs):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            while not release.is_set():
                await asyncio.sleep(0.01)
            yield ChatMessage(type="ai", content="UNSAFE tardia")

    fake.astream = stubborn
    try:
        ui.send(at, "Lenta")
        assert "demorou mais que o esperado" in at.error[0].value
        assert not at.chat_input[0].proto.disabled
        assert contents(at) == ["Lenta"]
        assert by_key(at, "retry_turn")
    finally:
        release.set()


def test_cancel_before_worker_creates_its_event_loop(monkeypatch):
    run = ResponseWait._run
    entered, release = Event(), Event()
    received = []

    def paused(self, receive):
        entered.set()
        release.wait(1)
        run(self, receive)

    async def receive():
        received.append(True)
        return ChatMessage(type="ai", content="Nunca aceita")

    monkeypatch.setattr(ResponseWait, "_run", paused)
    wait = ResponseWait(receive, 1)
    assert entered.wait(1)
    wait.cancel()
    release.set()
    wait._thread.join(timeout=1)
    assert wait.result.cancelled() and not received


@pytest.mark.parametrize("code", list(ToolErrorCode))
def test_typed_normative_errors_offer_the_matching_recovery(controlled, code):
    at, fake = ui.start(controlled)
    message = ui.normative("ERROR")
    result = message.normative_result.model_copy(update={"error_code": code})
    fake.events = [message.model_copy(update={"normative_result": result})]
    ui.send(at, "Pergunta exata  ")
    assert len(at.warning) == 1
    edit = code in {"invalid_request", "no_eligible_context", "clarification_unresolved"}
    action = by_key(at, "edit_question" if edit else "retry_turn")
    if edit:
        calls = len(fake.calls)
        action.click().run(timeout=15)
        assert len(fake.calls) == calls
        assert at.text_area[0].value == "Pergunta exata  "
        assert len([m for m in at.session_state.messages if m.type == "human"]) == 1
    else:
        fake.events = [ChatMessage(type="ai", content="Resposta recuperada")]
        action.click().run(timeout=15)
        ui.settle(at)
        assert [c["message"] for c in fake.calls] == ["Pergunta exata  "] * 2
        assert len([m for m in at.session_state.messages if m.type == "human"]) == 1
        assert contents(at)[-1] == "Resposta recuperada"
        assert not [b for b in at.button if b.key == "retry_turn"]


@pytest.mark.parametrize("code", list(SAFE_MESSAGES))
def test_calculator_error_edits_original_input_without_blind_retry(controlled, code):
    at, fake = ui.start(controlled)
    value = CalculatorToolResult(
        status="ERROR",
        operation_kind=None,
        content=SAFE_MESSAGES[code],
        normalized_input="",
        error_code=code,
        safe_message=SAFE_MESSAGES[code],
    )
    fake.events = [ChatMessage(type="ai", content=value.content, calculator_result=value)]
    ui.send(at, "Cálculo a corrigir")
    assert not [b for b in at.button if b.key == "retry_turn"]
    by_key(at, "edit_question").click().run(timeout=15)
    assert not at.exception
    assert at.text_area[0].value == "Cálculo a corrigir"
    assert len(fake.calls) == 1
    at.text_area[0].set_value("2+2").run(timeout=15)
    fake.events = [ui.calculator()]
    by_key(at, "submit_edit").click().run(timeout=15)
    ui.settle(at)
    assert fake.calls[-1]["message"] == "2+2"
    assert contents(at)[-2:] == ["2+2", "4"]
    assert len(at.chat_input) == 1


def test_blank_edit_is_not_sent_and_can_be_cancelled(controlled):
    at, fake = ui.start(controlled)
    fake.events = [ui.calculator("1/0")]
    ui.send(at, "1/0")
    by_key(at, "edit_question").click().run(timeout=15)
    at.text_area[0].set_value("  ").run(timeout=15)
    by_key(at, "submit_edit").click().run(timeout=15)
    assert len(fake.calls) == 1
    assert "Digite uma pergunta antes de enviar." in ui.visible(at)
    by_key(at, "cancel_edit").click().run(timeout=15)
    assert at.chat_input and not at.text_area


def test_blank_rename_explains_rejection_and_enter_confirms_valid_name(controlled):
    at, _ = ui.start(controlled)
    ui.send(at, "Nome anterior")
    thread = at.session_state.thread_id
    field = next(t for t in at.text_input if t.key == f"conv_title_{thread}")
    assert "Enter" in field.proto.help
    field.set_value(" \n ").run(timeout=15)
    assert "Digite um nome para a conversa." in ui.visible(at)
    assert at.session_state.conversations[thread].title == "Nome anterior"
    next(t for t in at.text_input if t.key == field.key).set_value("  Novo   nome ").run(timeout=15)
    assert at.session_state.conversations[thread].title == "Novo nome"
    assert next(t for t in at.text_input if t.key == field.key).value == "Novo nome"
    assert "Nome da conversa atualizado." in ui.visible(at)


def test_local_removal_discloses_scope_and_allows_keeping_conversation(controlled):
    at, _ = ui.start(controlled)
    ui.send(at)
    thread = at.session_state.thread_id
    assert by_key(at, f"conv_delete_{thread}").label == "Remover da lista"
    by_key(at, f"conv_delete_{thread}").click().run(timeout=15)
    assert "Esta ação não apaga os registros mantidos pelo serviço." in ui.visible(at)
    assert by_key(at, f"conv_delete_confirm_{thread}").label == "Remover da lista"
    by_key(at, f"conv_delete_keep_{thread}").click().run(timeout=15)
    assert thread in at.session_state.conversations
    assert "confirm_delete" not in at.session_state


@pytest.mark.parametrize("palette", [LIGHT, DARK])
@pytest.mark.parametrize("background", ["c-bg", "c-raised", "c-app"])
@pytest.mark.parametrize("foreground", ["c-composer-border", "c-accent"])
def test_composer_boundary_and_focus_have_nontext_contrast(palette, background, foreground):
    assert _contrast(palette[foreground], palette[background]) >= 3


def test_reading_sizes_touch_targets_and_focus_styles_use_accessible_tokens():
    assert SHARED["fs-md"] == "1rem"
    assert float(SHARED["h-touch"].removesuffix("rem")) * 16 >= 44
    css = (Path(ui.APP).with_name("chat_ui") / "styles.css").read_text(encoding="utf-8")
    for selector in (".ufpi-ref-text", '[data-testid="stChatMessageContent"] table'):
        assert "font-size: var(--fs-md)" in css.split(selector + " {", 1)[1].split("}", 1)[0]
    for selector in (".ufpi-jump", '[data-testid="stChatInputSubmitButton"]'):
        rule = css.split(selector + " {", 1)[1].split("}", 1)[0]
        assert "width: var(--h-touch)" in rule and "height: var(--h-touch)" in rule
    for selector in (".ufpi-copy", ".ufpi-sources > summary"):
        assert "min-height: var(--h-touch)" in css.split(selector + " {", 1)[1].split("}", 1)[0]
    rule = css.split('[data-testid="stChatInput"]:focus-within {', 1)[1].split("}", 1)[0]
    assert "outline: 2px solid var(--c-accent)" in rule


def test_visual_section_titles_are_semantic(controlled):
    at, fake = ui.start(controlled)
    fake.events = [ui.normative()]
    ui.send(at)
    assert '<h2 class="ufpi-section-label">Conversas</h2>' in ui.visible(at)
    assert '<h2 class="ufpi-sources-title">Fontes normativas</h2>' in ui.visible(at)
    assert '<h3 class="ufpi-norm-title">' in ui.visible(at)


def test_completion_announces_result_without_a_focus_or_scroll_script(controlled, monkeypatch):
    scripts = []
    original = components.html

    def recording(markup, **kwargs):
        scripts.append(markup)
        return original(markup, **kwargs)

    monkeypatch.setattr(components, "html", recording)
    at, _ = ui.start(controlled)
    ui.send(at)
    positioning = [s for s in scripts if "const anchor = doc.getElementById" in s]
    assert len(positioning) == 2  # Home, then the explicit send action; none on completion.
    assert 'role="status" aria-live="polite">Resposta pronta.' in ui.visible(at)


@pytest.mark.parametrize("failure", ["transport", "normative", "calculator", "timeout"])
def test_failure_never_announces_an_answer_ready(controlled, monkeypatch, failure):
    if failure == "timeout":
        monkeypatch.setattr("chat_ui.conversations.RESPONSE_TIMEOUT_SECONDS", 0.05)
    at, fake = ui.start(controlled)
    if failure == "transport":
        fake.error = RuntimeError("UNSAFE")
    elif failure == "normative":
        fake.events = [ui.normative("ERROR")]
    elif failure == "calculator":
        fake.events = [ui.calculator("1/0")]
    else:

        async def delayed(**kwargs):
            await asyncio.sleep(60)
            yield ChatMessage(type="ai", content="Tardia")

        fake.astream = delayed
    ui.send(at)
    assert "Resposta pronta." not in ui.visible(at)


@pytest.mark.parametrize(
    "code",
    [
        "expression_too_complex",
        "unsupported_relative_date",
        "ambiguous_date_offset",
        "input_too_large",
        "numeric_limit",
    ],
)
def test_calculator_messages_remain_canonical_without_internal_terms(code):
    message = SAFE_MESSAGES[code]
    assert all(term not in message for term in ("calculator", "absoluta", "YYYY", " N "))
    result = CalculatorToolResult(
        status="ERROR",
        operation_kind=None,
        content=message,
        normalized_input="",
        error_code=code,
        safe_message=message,
    )
    assert result.content == message


def test_session_notice_appears_once_next_to_composer(controlled):
    from streamlit_app import SESSION_NOTICE

    at, _ = ui.start(controlled)
    assert not any(SESSION_NOTICE in m.value for m in at.sidebar.markdown)
    main_hits = [m for m in at.markdown if SESSION_NOTICE in m.value and "ufpi-session-notice" in m.value]
    assert len(main_hits) == 1


def test_ready_announcement_is_visually_hidden():
    from pathlib import Path as _P

    css = (_P(__file__).resolve().parents[2] / "src" / "chat_ui" / "styles.css").read_text("utf-8")
    block = css[css.index(".ufpi-ready {"): css.index("}", css.index(".ufpi-ready {"))]
    assert "clip" in block and "width: 1px" in block and "position: absolute" in block


def test_no_follow_system_theme_button(controlled):
    at, _ = ui.start(controlled)
    keys = [b.key for b in at.sidebar.button]
    assert "theme_system" not in keys
    by_key(at, "theme_to_dark").click().run(timeout=15)
    assert "theme_system" not in [b.key for b in at.sidebar.button]


def test_stop_button_host_cannot_overflow_the_page():
    """The overlay host sits at the composer's right edge; its Streamlit wrappers
    must not inherit the column width, or the page gains a horizontal scroll."""
    css = (Path(ui.APP).with_name("chat_ui") / "styles.css").read_text(encoding="utf-8")
    block = css.split('.st-key-composer_action [data-testid="stTooltipIcon"] > div {', 1)[1].split("}", 1)[0]
    assert "max-width: var(--h-touch) !important" in block
    assert ".st-key-composer_action > div," in css
