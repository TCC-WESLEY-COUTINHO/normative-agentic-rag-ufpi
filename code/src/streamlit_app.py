"""Bisco chat UI for the integrated normative agent used by the v3.4 prototype.

Normative verification and conversation memory remain in the backend service.
"""

import asyncio
import os
import re
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from PIL import Image

from chat_ui.character import character_markup
from chat_ui.conversations import (
    RENAME_MAX_CHARACTERS,
    RESPONSE_TIMEOUT_SECONDS,
    Conversation,
    clean_title,
    escape_widget_label,
    title_from_question,
)
from chat_ui.rendering import copy_markup, literal_markdown, note_markup, sources_markup
from chat_ui.requests import ResponseWait
from chat_ui.theme import stylesheet
from client import AgentClient
from schema import ChatMessage

TCC_AGENT_ID = "chatbot_ufpi_integrated_v1"
APP_NAME = "Bisco"
APP_ROLE = "Assistente Normativo"
APP_TITLE = f"{APP_NAME} · {APP_ROLE} da UFPI"
APP_GREETING = "Olá! Eu sou o Bisco."
APP_LEAD = "Seu assistente virtual para consultas aos regulamentos acadêmicos da UFPI."
SESSION_VERSION = 3
UNAVAILABLE = "O assistente está temporariamente indisponível. Tente novamente em instantes."
INTERNAL_ERROR = "Não foi possível obter a resposta: o serviço encontrou um erro interno."
CONNECTION_LOST = "A conexão com o assistente foi interrompida antes do fim da resposta."
REQUEST_ERROR = "Não foi possível obter a resposta agora. Tente novamente."
TIMED_OUT = "A resposta demorou mais que o esperado. Tente novamente."
INTERRUPTED = "A resposta anterior foi interrompida antes de terminar."
RESEARCH_NOTICE = (
    "Protótipo de pesquisa. Consulte os documentos oficiais para confirmar as informações."
)
SESSION_NOTICE = (
    "As conversas ficam apenas nesta aba. Ao recarregar ou fechar a página, a lista é perdida."
)
FALLBACK_LABEL = "Resposta inconclusiva"
FALLBACK_NOTICE = (
    "Os trechos abaixo foram consultados, mas não sustentaram uma resposta conclusiva. "
    "Consulte o texto da norma."
)
UNCONFIRMED_LABEL = "Origem não confirmada"
UNCONFIRMED_NOTICE = "A resposta em que este texto se baseia não aparece nesta conversa."
ABSTENTION_LABEL = "Sem resposta normativa"
ABSTENTION_NOTICE = "Nenhum trecho normativo foi usado nesta resposta."
CLARIFICATION_LABEL = "Preciso de um esclarecimento"
HISTORICAL_LABEL = "Consulta histórica"
HISTORICAL_NOTICE = "O texto localizado não certifica a vigência da norma naquele momento."
UNANSWERED_LABEL = "Sem resposta"
UNANSWERED_NOTICE = "Esta pergunta não foi concluída."
PROGRESS = "Analisando sua pergunta…"
CANCELLED = (
    "A espera foi cancelada. Sua pergunta continua nesta conversa. "
    "O serviço pode continuar processando a consulta."
)
PLACEHOLDER = "Faça sua pergunta sobre os regulamentos da UFPI..."
UNAVAILABLE_STATUSES = frozenset({502, 503, 504})
UNREACHABLE_ERRORS = (httpx.ConnectError, httpx.TimeoutException)
CHAT_UI = Path(__file__).parent / "chat_ui"
# Page scripts, in order; bisco.js (the character runtime) is inserted before character.js.
PAGE_SCRIPTS = ("bridge.js", "presentation.js", "transition.js", "character.js")


def character_runtime() -> str:
    """Bisco's rig runtime (bisco.js, the same file the character lab runs as an ES module) as a
    classic script, preceded by the rig data it draws from.

    It runs inside its own strict function scope: none of its names, function declarations
    included, can reach the shared page script and replace another script's function. Only
    BiscoRuntime is published."""
    source = (CHAT_UI / "bisco.js").read_text(encoding="utf-8")
    source = re.sub(r"^export (?=const |class |function )", "", source, flags=re.MULTILINE)
    rig = (CHAT_UI / "bisco_rig.json").read_text(encoding="utf-8").strip()
    return (
        f"var BISCO_RIG = {rig};\n"
        f'var BiscoRuntime = (function () {{\n"use strict";\n{source}\n'
        "return { BiscoCharacter };\n})();"
    )


BRIDGE_SCRIPT = "\n".join(
    [
        *((CHAT_UI / name).read_text(encoding="utf-8") for name in PAGE_SCRIPTS[:3]),
        character_runtime(),
        (CHAT_UI / PAGE_SCRIPTS[3]).read_text(encoding="utf-8"),
        (CHAT_UI / "wait.js").read_text(encoding="utf-8"),
    ]
)
# Bisco's neutral face, rendered from the same rig layers the page draws, on a transparent
# background. 64 px stays sharp on high-density tabs and downscales cleanly to 16-32.
FAVICON = Image.open(Path(__file__).parent / "static" / "bisco" / "favicon-64.png")


def active_conversation() -> Conversation:
    return st.session_state.conversations[st.session_state.thread_id]


def activate(conversation: Conversation) -> None:
    """`thread_id` and `messages` always describe exactly one stored conversation."""
    st.session_state.thread_id = conversation.thread_id
    st.session_state.messages = conversation.messages
    st.session_state.pop("confirm_delete", None)
    st.session_state.pop("editing_question", None)
    st.session_state.pop("response_ready", None)


def new_conversation() -> None:
    """Start a local conversation; existing backend checkpoints are retained."""
    conversations = st.session_state.conversations
    if conversations and not active_conversation().messages:
        return
    conversation = Conversation()
    conversations[conversation.thread_id] = conversation
    activate(conversation)
    st.session_state.scroll_target = "top"


def open_conversation(thread_id: str) -> None:
    activate(st.session_state.conversations[thread_id])
    st.session_state.scroll_target = "bottom"


def rename_conversation(thread_id: str, key: str) -> None:
    title = clean_title(st.session_state.get(key, ""))
    if title:
        st.session_state.conversations[thread_id].title = title
        st.session_state[key] = title
        st.session_state[f"rename_feedback_{thread_id}"] = "Nome da conversa atualizado."
    else:
        st.session_state[f"rename_feedback_{thread_id}"] = "Digite um nome para a conversa."


def ask_delete(thread_id: str) -> None:
    st.session_state.confirm_delete = thread_id


def keep_conversation() -> None:
    st.session_state.pop("confirm_delete", None)


def delete_conversation(thread_id: str) -> None:
    """Remove from this list only; the service keeps no user-facing delete operation."""
    conversations = st.session_state.conversations
    was_active = st.session_state.thread_id == thread_id
    del conversations[thread_id]
    st.session_state.pop("confirm_delete", None)
    if was_active:
        replacement = Conversation()
        conversations[replacement.thread_id] = replacement
        activate(replacement)


def initialize_session() -> None:
    """Migrate legacy sessions once, without adopting URL identities/history."""
    try:
        UUID(st.session_state.get("user_id", ""))
    except (ValueError, TypeError, AttributeError):
        st.session_state.user_id = str(uuid4())
    if st.session_state.get("_tcc_ui_version") != SESSION_VERSION:
        st.session_state.conversations = {}
        # The home opens at its top: on a short screen Streamlit would otherwise start it at the
        # bottom, hiding the figure and the greeting.
        new_conversation()
        for key in ("agent_client", "agent_id", "agent", "model", "pending_turn", "in_flight"):
            st.session_state.pop(key, None)
        st.session_state._tcc_ui_version = SESSION_VERSION
    for key in ("agent", "agent_id", "thread_id", "user_id"):
        if key in st.query_params:
            del st.query_params[key]


def recover_interrupted_turn() -> None:
    """A run stopped mid-request cannot be resumed: say so instead of showing silence."""
    if "response_wait" in st.session_state:
        return
    if (turn := st.session_state.pop("in_flight", None)) is None:
        return
    conversation = st.session_state.conversations.get(turn["thread_id"])
    answered = conversation is not None and conversation.messages[-1].type != "human"
    if conversation is not None and not answered:
        conversation.error = INTERRUPTED
        conversation.failed_question = turn["question"]
        conversation.recovery_action = "retry"


def start_turn(question: str) -> None:
    # Several controls can fire before the same rerun (composer and "Tentar novamente"): the first
    # question in flight wins and the others are not recorded, so nothing appears as asked
    # without having been sent.
    if "pending_turn" in st.session_state or "in_flight" in st.session_state:
        return
    conversation = active_conversation()
    if not conversation.messages:
        conversation.title = title_from_question(question)
    conversation.messages.append(ChatMessage(type="human", content=question))
    conversation.error = conversation.failed_question = None
    conversation.recovery_action = "retry"
    st.session_state.pop("response_ready", None)
    st.session_state.pending_turn = {"thread_id": conversation.thread_id, "question": question}


def submit_composer() -> None:
    if question := st.session_state.get("composer"):
        start_turn(question)


def retry_turn(thread_id: str) -> None:
    if "pending_turn" in st.session_state or "in_flight" in st.session_state:
        return
    conversation = st.session_state.conversations[thread_id]
    question, conversation.failed_question = conversation.failed_question, None
    conversation.error = None
    st.session_state.pending_turn = {"thread_id": thread_id, "question": question}
    st.session_state.pop("response_ready", None)


def edit_question(thread_id: str) -> None:
    conversation = st.session_state.conversations[thread_id]
    st.session_state.editing_question = conversation.failed_question
    st.session_state.question_draft = conversation.failed_question


def submit_edit() -> None:
    question = st.session_state.get("question_draft", "")
    if question.strip():
        st.session_state.pop("editing_question", None)
        start_turn(question)


def cancel_edit() -> None:
    st.session_state.pop("editing_question", None)


def cancel_turn() -> None:
    wait = st.session_state.pop("response_wait", None)
    if wait is not None:
        wait.cancel()
    turn = st.session_state.pop("in_flight", None) or st.session_state.pop("pending_turn", None)
    if turn is not None:
        conversation = st.session_state.conversations[turn["thread_id"]]
        index = max(i for i, m in enumerate(conversation.messages) if m.type == "human")
        conversation.cancelled_questions.add(index)
        conversation.error = conversation.failed_question = None
    st.session_state.pop("response_ready", None)


def current_theme() -> str:
    return st.session_state.get("theme_mode", "system")


def set_theme(mode: str) -> None:
    st.session_state.theme_mode = mode


def scroll_page(target: str) -> None:
    """One placement at our own marker; a fresh script body forces it to execute.

    Streamlit keeps its scroll container at the bottom while content grows, so the page is never
    moved against that: only "top" (an empty conversation) and "bottom" are requested.

    "bottom" moves the conversation's own scroll container to its end, so the new question and the
    thinking figure sit above the pinned composer, whatever the reader's position was. Once at the
    end, Streamlit follows the turn as it grows. Growth while the turn is being built is kept at
    the end by the page script (keepTurnEnd in bridge.js), which yields to the reader's gestures.
    """
    anchors = {"top": "conversation-top", "bottom": "chat-bottom-anchor", "focus": None}
    if target == "bottom":
        placement = (
            "const scroller = anchor && anchor.closest('section.stMain');\n"
            "if (scroller) scroller.scrollTop = scroller.scrollHeight;\n"
        )
    else:
        placement = "if (anchor) anchor.scrollIntoView({block: 'start'});\n"
    components.html(
        f"<script>/* {target} {uuid4()} */\n"
        "const doc = window.parent.document;\n"
        f"const anchor = doc.getElementById('{anchors[target] or ''}');\n"
        f"{placement}"
        "const touch = window.parent.matchMedia('(pointer: coarse)').matches;\n"
        "const box = doc.querySelector('[data-testid=\"stChatInputTextArea\"]');\n"
        "if (box && !box.disabled && !touch) box.focus({preventScroll: true});\n"
        "</script>",
        height=0,
        scrolling=False,
    )


def agent_base_url() -> str:
    return (
        os.getenv("AGENT_URL")
        or f"http://{os.getenv('HOST', 'localhost')}:{os.getenv('PORT', '8080')}"
    ).rstrip("/")


def render_sidebar(busy: bool) -> None:
    with st.sidebar:
        # The same Bisco as everywhere else, smiling, as a still picture; the UFPI mark is not used
        # without a verified official source.
        head = character_markup("happy", variant="chat", uid="brand")
        st.markdown(
            f'<div class="ufpi-brand">{head}<div class="ufpi-brand-text">'
            f'<span class="ufpi-brand-name">{APP_NAME}</span>'
            f'<span class="ufpi-brand-role">{APP_ROLE}</span></div></div>',
            unsafe_allow_html=True,
        )
        st.button(
            "Nova conversa",
            key="new_conversation",
            icon=":material/add:",
            use_container_width=True,
            disabled=busy,
            on_click=new_conversation,
        )
        listed = [c for c in st.session_state.conversations.values() if c.messages]
        if listed:
            st.markdown('<h2 class="ufpi-section-label">Conversas</h2>', unsafe_allow_html=True)
        for conversation in reversed(listed):
            render_conversation_row(conversation, busy)
        # The temporary-history notice lives next to the composer only (one occurrence).
        render_theme_control(busy)


def render_theme_control(busy: bool) -> None:
    """Both directions exist; the stylesheet shows the one that leaves the current palette.

    The server cannot know the system preference, and this is what lets it stay the default.
    """
    with st.container(key="theme_control"):
        for mode, label, icon in (
            ("dark", "Usar tema escuro", ":material/dark_mode:"),
            ("light", "Usar tema claro", ":material/light_mode:"),
        ):
            st.button(
                label,
                key=f"theme_to_{mode}",
                icon=icon,
                disabled=busy,
                on_click=set_theme,
                args=(mode,),
            )


def render_conversation_row(conversation: Conversation, busy: bool) -> None:
    thread_id = conversation.thread_id
    is_active = thread_id == st.session_state.thread_id
    state = "active" if is_active else "idle"
    with st.container(key=f"conv_row_{thread_id}"):
        title_column, menu_column = st.columns([5, 1], gap="small", vertical_alignment="center")
        title_column.button(
            escape_widget_label(conversation.title),
            key=f"conv_open_{state}_{thread_id}",
            use_container_width=True,
            disabled=busy,
            on_click=open_conversation,
            args=(thread_id,),
        )
        with menu_column.container(key=f"conv_menu_{thread_id}"):
            with st.popover(":material/more_horiz:", disabled=busy):
                rename_key = f"conv_title_{thread_id}"
                st.text_input(
                    "Nome da conversa",
                    value=conversation.title,
                    key=rename_key,
                    max_chars=RENAME_MAX_CHARACTERS,
                    on_change=rename_conversation,
                    args=(thread_id, rename_key),
                    help="Pressione Enter para salvar o nome.",
                )
                if feedback := st.session_state.get(f"rename_feedback_{thread_id}"):
                    if not clean_title(st.session_state.get(rename_key, "")):
                        st.error(feedback)
                    else:
                        st.caption(feedback)
                if st.session_state.get("confirm_delete") == thread_id:
                    st.caption(
                        "Esta conversa deixará de aparecer nesta aba. "
                        "Esta ação não apaga os registros mantidos pelo serviço."
                    )
                    st.button(
                        "Manter conversa",
                        key=f"conv_delete_keep_{thread_id}",
                        use_container_width=True,
                        on_click=keep_conversation,
                    )
                    st.button(
                        "Remover da lista",
                        key=f"conv_delete_confirm_{thread_id}",
                        use_container_width=True,
                        on_click=delete_conversation,
                        args=(thread_id,),
                    )
                else:
                    st.button(
                        "Remover da lista",
                        key=f"conv_delete_{thread_id}",
                        use_container_width=True,
                        on_click=ask_delete,
                        args=(thread_id,),
                    )


def render_composer(busy: bool) -> None:
    if "editing_question" in st.session_state:
        # This Streamlit version forbids setting chat_input through session_state. A native
        # editor in the composer restores the original text without submitting it again.
        editor = st._bottom if active_conversation().messages else st
        with editor.container(key="question_editor"):
            st.text_area("Edite sua pergunta", key="question_draft", disabled=busy)
            st.button("Enviar pergunta", key="submit_edit", on_click=submit_edit, disabled=busy)
            st.button("Cancelar edição", key="cancel_edit", on_click=cancel_edit, disabled=busy)
            if not st.session_state.get("question_draft", "").strip():
                st.caption("Digite uma pergunta antes de enviar.")
    else:
        st.chat_input(PLACEHOLDER, key="composer", disabled=busy, on_submit=submit_composer)
    # Streamlit 1.40 cannot replace chat_input's submit action. Keep a native
    # callback button in an always-present, absolutely positioned overlay host.
    # wait.js aligns it with the submit button without moving React-owned nodes.
    with st._bottom.container(key="composer_action"):
        st.button(
            "Parar", key="cancel_turn", icon=":material/stop:",
            help="Parar", on_click=cancel_turn, disabled=not busy,
        )
    notice = f'<p class="ufpi-session-notice">{SESSION_NOTICE}</p>'
    if active_conversation().messages:
        st._bottom.markdown(notice, unsafe_allow_html=True)
    else:
        st.markdown(notice, unsafe_allow_html=True)


def render_empty_state(busy: bool) -> None:
    with st.container(key="empty_state"):
        st.markdown(
            character_markup(
                "happy",
                variant="home",
                uid="home",
                label="Bisco, o assistente. Ativar para receber um cumprimento",
                lead="home",
                interactive=True,
            ),
            unsafe_allow_html=True,
        )
        greeting = APP_GREETING.replace(
            APP_NAME, f'<span class="ufpi-name-gradient">{APP_NAME}</span>', 1
        )
        st.markdown(f'<h1 class="ufpi-greeting">{greeting}</h1>', unsafe_allow_html=True)
        st.markdown(f'<p class="ufpi-empty-lead">{APP_LEAD}</p>', unsafe_allow_html=True)
        # On the home the composer sits in the flow, right under the greeting.
        with st.container(key="home_composer"):
            render_composer(busy)


def state_note(label: str, text: str = "", *, kind: str = "neutral") -> None:
    st.caption(note_markup(label, text, kind), unsafe_allow_html=True)


def render_sources(result, *, conclusive: bool = True) -> None:
    if not result.references:
        return
    provenance = result.temporal_provenance
    uncertified = frozenset(
        state.chunk_id
        for state in (provenance.evidence_states if provenance else ())
        if state.normative_status == "desconhecida"
    )
    st.markdown(
        sources_markup(
            result.references,
            domain=result.domain,
            uncertified_chunks=uncertified,
            conclusive=conclusive,
        ),
        unsafe_allow_html=True,
    )


def source_state(message: ChatMessage, history: list[ChatMessage]) -> str | None:
    """A follow-up carries only its source's id, so the source's state is read from the history.

    An answer that never reached this page, as after a failed delivery, cannot vouch for anything.
    """
    followup = message.grounded_followup_result
    if followup is None:
        return None
    for earlier in history:
        result = earlier.normative_result
        if result is not None and result.correlation_id == followup.source_correlation_id:
            return "inconclusive" if result.core_status == "fallback" else "conclusive"
    return "unknown"


def message_expression(message: ChatMessage, history: list[ChatMessage] = ()) -> str | None:
    """The expression follows the typed state, never the wording, and never smiles at an answer:
    a pleasant face must not read as a sign that the content was validated."""
    if message.type == "human":
        return None
    normative = message.normative_result
    if normative is not None and normative.status == "CLARIFICATION":
        slot = "clarification"
    elif (normative is not None and normative.status == "ERROR") or (
        message.calculator_result is not None and message.calculator_result.status == "ERROR"
    ):
        slot = "error"
    elif source_state(message, history) in ("inconclusive", "unknown") or (
        normative is not None and normative.core_status in ("abstained", "fallback")
    ):
        slot = "abstained"
    else:
        slot = "neutral"
    return slot


def render_message(
    message: ChatMessage, index: int, history: list[ChatMessage], *, lead: str | None = None
) -> None:
    """Content is presentation text; typed contracts alone select the renderer."""
    with (
        st.container(key=f"msg_{message.type}_{index}"),
        st.chat_message(message.type),
    ):
        if message.type == "human":
            st.text(message.content)
            return
        normative = message.normative_result
        calculator = message.calculator_result
        if normative is not None and normative.status == "CLARIFICATION":
            state_note(CLARIFICATION_LABEL)
        elif normative is not None and normative.core_status == "abstained":
            state_note(ABSTENTION_LABEL, ABSTENTION_NOTICE)
        elif normative is not None and normative.core_status == "fallback":
            state_note(FALLBACK_LABEL, FALLBACK_NOTICE, kind="caution")
        if normative is not None and normative.status == "ERROR":
            st.warning(message.content)
        elif calculator is not None and calculator.status == "ERROR":
            st.warning(calculator.safe_message)
        else:
            # Its own block, so the page script can present a freshly received answer
            # (presentation.js); the stored content is rendered whole, as for any other message.
            with st.container(key=f"ans_{index}"):
                st.markdown(literal_markdown(message.content))
            st.markdown(copy_markup(message.content), unsafe_allow_html=True)
        if normative is not None and normative.status == "ANSWER":
            provenance = normative.temporal_provenance
            if provenance is not None and provenance.temporal_intent == "historical":
                state_note(HISTORICAL_LABEL, HISTORICAL_NOTICE)
            render_sources(normative, conclusive=normative.core_status != "fallback")
        elif (grounded := message.grounded_followup_result) is not None:
            repeated = grounded.kind == "REPEAT" or grounded.guard_status == "FALLBACK_TO_SOURCE"
            st.caption(
                "Repetição da resposta normativa anterior."
                if repeated
                else "Reformulação baseada na resposta normativa anterior."
            )
            state = source_state(message, history)
            if state == "inconclusive":
                state_note(FALLBACK_LABEL, FALLBACK_NOTICE, kind="caution")
            elif state == "unknown":
                state_note(UNCONFIRMED_LABEL, UNCONFIRMED_NOTICE, kind="caution")
            render_sources(grounded, conclusive=state == "conclusive")
        st.markdown(
            character_markup(
                message_expression(message, history), variant="chat", uid=str(index), lead=lead
            ),
            unsafe_allow_html=True,
        )


def render_conversation(conversation: Conversation, busy: bool) -> None:
    st.markdown('<div id="conversation-top"></div>', unsafe_allow_html=True)
    if not conversation.messages:
        render_empty_state(busy)
    last_question = max(
        (i for i, m in enumerate(conversation.messages) if m.type == "human"), default=None
    )
    for index, message in enumerate(conversation.messages):
        if index == last_question:
            st.markdown('<div id="last-turn"></div>', unsafe_allow_html=True)
        # Only the newest answer is the figure the head travels to; older answers keep still.
        newest = index == len(conversation.messages) - 1 and not busy
        lead = f"{conversation.thread_id}-{index}" if newest else None
        render_message(message, index, conversation.messages, lead=lead)
        following = conversation.messages[index + 1 : index + 2]
        if index in conversation.cancelled_questions:
            state_note("Consulta cancelada", CANCELLED)
        elif message.type == "human" and following and following[0].type == "human":
            state_note(UNANSWERED_LABEL, UNANSWERED_NOTICE)
    if busy:
        wait = st.session_state.get("response_wait")
        elapsed = int(wait.elapsed) if wait is not None else 0
        st.markdown(
            '<div class="ufpi-progress" role="status" aria-live="polite">'
            f"{character_markup('thinking', variant='loading', uid='loading', lead='loading')}"
            f'<span class="ufpi-progress-label">{PROGRESS}</span>'
            f'<span class="ufpi-progress-elapsed" data-elapsed="{elapsed}" '
            f'aria-live="off">{elapsed} s</span></div>',
            unsafe_allow_html=True,
        )
    elif conversation.error:
        with st.container(key="msg_ai_failure"), st.chat_message("ai"):
            st.markdown(
                character_markup(
                    "error",
                    variant="chat",
                    uid="failure",
                    lead=f"{conversation.thread_id}-failure",
                ),
                unsafe_allow_html=True,
            )
            st.error(conversation.error)
    if not busy and conversation.failed_question:
        if conversation.recovery_action == "edit":
            st.button(
                "Editar pergunta",
                key="edit_question",
                on_click=edit_question,
                args=(conversation.thread_id,),
            )
        else:
            st.button(
                "Tentar novamente",
                key="retry_turn",
                on_click=retry_turn,
                args=(conversation.thread_id,),
            )
    st.markdown('<div id="chat-bottom-anchor"></div>', unsafe_allow_html=True)


async def receive_message(events: AsyncGenerator[ChatMessage | str, None]) -> ChatMessage:
    """The integrated stream contains one complete AI message; DONE is client-owned."""
    final = None
    async for event in events:
        if not isinstance(event, ChatMessage) or event.type != "ai" or final is not None:
            raise ValueError("Unexpected integrated stream payload.")
        # Revalidate even constructed instances before retaining/displaying a payload.
        final = ChatMessage.model_validate(event.model_dump())
    if final is None:
        raise ValueError("Missing integrated response.")
    return final


def safe_service_error(error: Exception) -> str:
    """Read HTTP status through the existing client's chained exception, never its text."""
    seen = set()
    current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, TimeoutError):
            return TIMED_OUT
        if isinstance(current, UNREACHABLE_ERRORS):
            return UNAVAILABLE
        if isinstance(current, httpx.TransportError):
            return CONNECTION_LOST
        if isinstance(current, httpx.HTTPStatusError):
            status = current.response.status_code
            if status in UNAVAILABLE_STATUSES:
                return UNAVAILABLE
            if status >= 500:
                return INTERNAL_ERROR
        current = current.__cause__ or current.__context__
    return REQUEST_ERROR


def process_pending_turn(client: AgentClient) -> None:
    turn = st.session_state.pop("pending_turn")
    st.session_state.in_flight = turn
    user_id = st.session_state.user_id
    st.session_state.response_wait = ResponseWait(
        lambda: receive_message(
            client.astream(message=turn["question"], thread_id=turn["thread_id"], user_id=user_id)
        ),
        RESPONSE_TIMEOUT_SECONDS,
    )
    scroll_page("bottom")


def set_recovery(conversation: Conversation, response: ChatMessage, question: str) -> None:
    normative, calculator = response.normative_result, response.calculator_result
    if calculator is not None and calculator.status == "ERROR":
        conversation.failed_question = question
        conversation.recovery_action = "edit"
    elif normative is not None and normative.status == "ERROR":
        conversation.failed_question = question
        conversation.recovery_action = (
            "edit"
            if normative.error_code
            in {"invalid_request", "no_eligible_context", "clarification_unresolved"}
            else "retry"
        )


@st.fragment(run_every=1)
def poll_response() -> None:
    wait = st.session_state.get("response_wait")
    if wait is None:
        st.rerun()
    turn = st.session_state.in_flight
    if not wait.result.done() and wait.elapsed < wait.timeout:
        return
    conversation = st.session_state.conversations[turn["thread_id"]]
    ready = False
    try:
        if not wait.result.done():
            wait.cancel()
            raise TimeoutError
        response = wait.result.result()
        conversation.messages.append(response)
        set_recovery(conversation, response, turn["question"])
        ready = conversation.failed_question is None
    except Exception as error:
        # The public UI boundary also handles malformed transport payloads safely.
        conversation.error = safe_service_error(error)
        conversation.failed_question = turn["question"]
        conversation.recovery_action = "retry"
    st.session_state.pop("in_flight", None)
    st.session_state.pop("response_wait", None)
    st.session_state.response_ready = ready
    st.rerun()


async def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon=FAVICON, menu_items={})
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    initialize_session()
    recover_interrupted_turn()
    with st.container(key="ufpi_style"):
        st.markdown(stylesheet(current_theme()), unsafe_allow_html=True)
    # Second element on every screen: Streamlit identifies elements by position, so the page script
    # survives every rerun only if nothing that varies is rendered before it.
    scripts = st.container(key="ufpi_scripts")
    with scripts:
        components.html(f"<script>{BRIDGE_SCRIPT}</script>", height=0, scrolling=False)

    busy = "pending_turn" in st.session_state or "in_flight" in st.session_state
    render_sidebar(busy)

    if "agent_client" not in st.session_state:
        agent_url = agent_base_url()
        # Skip /info default selection: requests always name the integrated agent.
        st.session_state.agent_client = AgentClient(base_url=agent_url, get_info=False)
    client: AgentClient = st.session_state.agent_client
    client.update_agent(TCC_AGENT_ID, verify=False)

    render_conversation(active_conversation(), busy)
    if st.session_state.get("response_ready"):
        st.markdown(
            '<div class="ufpi-ready" role="status" aria-live="polite">Resposta pronta.</div>',
            unsafe_allow_html=True,
        )
    if active_conversation().messages:
        # In a conversation the composer is pinned under the messages.
        render_composer(busy)
    st._bottom.markdown(
        f'<p class="ufpi-research-notice">{RESEARCH_NOTICE}</p>', unsafe_allow_html=True
    )

    with scripts:
        if "pending_turn" in st.session_state:
            process_pending_turn(client)
        elif not busy and (target := st.session_state.pop("scroll_target", None)):
            scroll_page(target)
        if busy:
            poll_response()


if __name__ == "__main__":
    asyncio.run(main())
