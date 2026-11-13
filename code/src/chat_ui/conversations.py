"""Conversations kept in this browser session only. The service owns its own checkpoints."""

import re
from dataclasses import dataclass, field
from uuid import uuid4

from schema import ChatMessage

UNTITLED = "Nova conversa"
TITLE_MAX_CHARACTERS = 60
RENAME_MAX_CHARACTERS = 80
# The client waits without limit and controls stay disabled meanwhile, so the page gives up itself.
RESPONSE_TIMEOUT_SECONDS = 300


@dataclass
class Conversation:
    thread_id: str = field(default_factory=lambda: str(uuid4()))
    title: str = UNTITLED
    messages: list[ChatMessage] = field(default_factory=list)
    error: str | None = None
    failed_question: str | None = None


def title_from_question(question: str) -> str:
    """Short readable label from the question; the question itself is never altered."""
    text = " ".join(question.split())
    if len(text) <= TITLE_MAX_CHARACTERS:
        return text or UNTITLED
    cut = text.rfind(" ", 0, TITLE_MAX_CHARACTERS)
    return text[: cut if cut > TITLE_MAX_CHARACTERS // 2 else TITLE_MAX_CHARACTERS].rstrip() + "…"


def clean_title(title: str) -> str:
    return " ".join(title.split())[:RENAME_MAX_CHARACTERS]


def escape_widget_label(text: str) -> str:
    """Widget labels accept Markdown; a user-given title must be shown literally."""
    return re.sub(r"([\\`*_~\[\]$:<>#|])", r"\\\1", text)
