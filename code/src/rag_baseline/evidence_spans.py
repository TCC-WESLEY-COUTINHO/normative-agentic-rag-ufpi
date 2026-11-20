"""Line structure gives stable addresses without inferring normative meaning."""

from dataclasses import dataclass
from typing import Literal

from rag_baseline.content_locators import (
    _ALINEA_LINE,
    _INCISO_LINE,
    _PARAGRAPH_LINE,
    _ROMAN,
    _SINGLE_PARAGRAPH_LINE,
)
from rag_baseline.grounding import TemporalGroundingContext
from rag_baseline.models import RetrievedChunk
from rag_baseline.normative_output import (
    allowed_temporal_facts,
    norm_name,
    render_temporal_statements,
)
from rag_baseline.output_contracts import AllowedTemporalFacts, NormativeReference, TemporalFact


@dataclass(frozen=True)
class EvidenceSpan:
    span_id: str
    chunk_id: str
    norm_id: str
    article: str
    kind: Literal["article", "caput", "paragraph", "inciso", "alinea", "fact"]
    label: str
    parent_id: str | None
    text: str
    ambiguous: bool = False
    related_norm_ids: tuple[str, ...] = ()
    paragraph: str | None = None
    sector: str | None = None


def temporal_fact_spans(grounding: TemporalGroundingContext) -> dict[str, EvidenceSpan]:
    """Quote registry relations and rendered status facts in deterministic order.

    target_article/target_paragraph locate the affected source_norm provision;
    target_norm names the amending/revoking act, not the provision's owner.
    """
    entries = []
    for relation in sorted(
        grounding.known_relations,
        key=lambda r: (
            r.source_norm,
            r.target_norm,
            r.relation,
            r.target_article or "",
            r.target_paragraph or "",
            r.evidence_source,
            r.evidence_article,
        ),
    ):
        fact = TemporalFact(
            kind=relation.relation, norm_id=relation.source_norm, target_norm=relation.target_norm
        )
        text = render_temporal_statements(AllowedTemporalFacts(items=[fact]))
        device = []
        if relation.target_article:
            device.append(f"art. {relation.target_article}")
        if relation.target_paragraph:
            device.append(f"§ {relation.target_paragraph}")
        if device:
            text += (
                "\nDispositivo alterado: "
                + ", ".join(device)
                + f" da {norm_name(relation.source_norm)}."
            )
        entries.append((fact, text, relation.target_article, relation.target_paragraph))
    for fact in sorted(
        allowed_temporal_facts(grounding).items, key=lambda f: (f.kind, f.norm_id or "")
    ):
        if fact.kind == "STATUS_UNKNOWN":
            entries.append(
                (fact, render_temporal_statements(AllowedTemporalFacts(items=[fact])), None, None)
            )
    return {
        f"fato:{i}": EvidenceSpan(
            span_id=f"fato:{i}",
            chunk_id="",
            norm_id=fact.norm_id or "",
            article=article or "",
            kind="fact",
            label="",
            parent_id=None,
            text=text,
            related_norm_ids=(fact.target_norm,) if fact.target_norm else (),
            paragraph=paragraph,
        )
        for i, (fact, text, article, paragraph) in enumerate(entries, 1)
    }


def segment_chunk(chunk: RetrievedChunk, norm_id: str) -> list[EvidenceSpan]:
    root = f"{norm_id}:art{chunk.article_number}"
    result = [
        EvidenceSpan(
            root,
            chunk.id,
            norm_id,
            chunk.article_number,
            "article",
            chunk.article_number,
            None,
            chunk.content,
            sector=chunk.sector,
        )
    ]
    markers = []
    for pattern, kind, level in (
        (_PARAGRAPH_LINE, "paragraph", 1),
        (_SINGLE_PARAGRAPH_LINE, "paragraph", 1),
        (_INCISO_LINE, "inciso", 2),
        (_ALINEA_LINE, "alinea", 3),
    ):
        for match in pattern.finditer(chunk.content):
            label = match[1] if pattern != _SINGLE_PARAGRAPH_LINE else "unico"
            if kind == "inciso":
                label = label.replace("|", "I").replace("l", "I")
                if not _ROMAN.fullmatch(label):
                    continue
            markers.append((match.start(), level, kind, label))
    markers = [(0, 1, "caput", "caput"), *sorted(markers)]
    # An alinea nests under the nearest open container. OCR-misread or restarting labels
    # repeat an address: the repetition gets an ordinal suffix and every span sharing the
    # label is marked ambiguous, so it stays quotable but never names a subdivision.
    stack = []
    occurrences = {}
    planned = []
    for i, (start, level, kind, label) in enumerate(markers):
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else root
        suffix = {
            "caput": "caput",
            "paragraph": f"p{label}",
            "inciso": f"inc{label}",
            "alinea": f"al{label}",
        }[kind]
        address = f"{parent}:{suffix}"
        occurrences[address] = occurrences.get(address, 0) + 1
        span_id = address if occurrences[address] == 1 else f"{address}~{occurrences[address]}"
        end = next((m[0] for m in markers[i + 1 :] if m[1] <= level), len(chunk.content))
        planned.append((span_id, address, kind, label, parent, start, end))
        stack.append((level, span_id))
    for span_id, address, kind, label, parent, start, end in planned:
        result.append(
            EvidenceSpan(
                span_id,
                chunk.id,
                norm_id,
                chunk.article_number,
                kind,
                label,
                parent,
                chunk.content[start:end].strip(),
                ambiguous=occurrences[address] > 1
                or any(_inherited_ambiguity(parent, planned, occurrences)),
                sector=chunk.sector,
            )
        )
    return result


def _inherited_ambiguity(parent, planned, occurrences):
    """A child of an ambiguous container inherits its ambiguity."""
    by_id = {p[0]: p for p in planned}
    while parent in by_id:
        _, address, _, _, parent, _, _ = by_id[parent]
        yield occurrences[address] > 1


def segment_evidence(
    chunks: list[RetrievedChunk], references: list[NormativeReference]
) -> dict[str, EvidenceSpan]:
    eligible = {r.chunk_id: r.norm_id for r in references}
    result = {}
    for chunk in sorted(chunks, key=lambda c: (c.rank, c.id)):
        if chunk.id not in eligible:
            continue
        for span in segment_chunk(chunk, eligible[chunk.id]):
            # A second text under the same address stays uncitable rather than
            # aborting generation; the first, best-ranked evidence keeps the address.
            result.setdefault(span.span_id, span)
    return result
