"""Presentation-only previews and progressive reveal of already accepted text."""

import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from rag_baseline.output_contracts import NormativeReference

REFERENCE_PREVIEW_CHARACTERS = 600
PROGRESSIVE_CHUNK_WORDS = 2
PROGRESSIVE_DELAY_SECONDS = 0.05
PROGRESSIVE_MAX_SECONDS = 6.0


@dataclass(frozen=True)
class ReferenceGroup:
    norm_id: str
    label: str
    references: tuple[NormativeReference, ...]


def group_references(references: list[NormativeReference]) -> tuple[ReferenceGroup, ...]:
    """Group typed identities in first-occurrence order without losing evidence."""
    grouped: dict[str, list[NormativeReference]] = {}
    for reference in references:
        grouped.setdefault(reference.norm_id, []).append(reference)
    return tuple(
        ReferenceGroup(norm_id, items[0].source or norm_id, tuple(items))
        for norm_id, items in grouped.items()
    )


def pause(seconds: float) -> None:
    time.sleep(seconds)


def reference_preview(text: str) -> str:
    if len(text) <= REFERENCE_PREVIEW_CHARACTERS:
        return text
    boundary = max(
        text.rfind(" ", 0, REFERENCE_PREVIEW_CHARACTERS + 1),
        text.rfind("\n", 0, REFERENCE_PREVIEW_CHARACTERS + 1),
    )
    if boundary < REFERENCE_PREVIEW_CHARACTERS // 2:
        boundary = REFERENCE_PREVIEW_CHARACTERS
    return text[:boundary].rstrip() + "…"


def stream_validated_text(
    text: str, *, sleep: Callable[[float], None] | None = None
) -> Iterator[str]:
    """Preserve every character; 100–200 words take about 2.5–5s, long text ≤6s."""
    words = list(re.finditer(r"\S+", text))
    if not words:
        if text:
            yield text
        return
    starts = [0] + [
        words[i].start()
        for i in range(PROGRESSIVE_CHUNK_WORDS, len(words), PROGRESSIVE_CHUNK_WORDS)
    ]
    ends = starts[1:] + [len(text)]
    delay = min(PROGRESSIVE_DELAY_SECONDS, PROGRESSIVE_MAX_SECONDS / len(starts))
    sleeper = sleep if sleep is not None else pause
    for start, end in zip(starts, ends):
        yield text[start:end]
        sleeper(delay)
