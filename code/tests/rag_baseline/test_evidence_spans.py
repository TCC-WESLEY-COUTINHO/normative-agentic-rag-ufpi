import pytest

from rag_baseline.evidence_spans import segment_chunk, segment_evidence
from rag_baseline.models import RetrievedChunk
from rag_baseline.output_contracts import NormativeReference


def chunk(content, **updates):
    return RetrievedChunk(
        id="c1",
        content=content,
        source="Resolução 177/2012",
        article_number="68",
        article_label="Art. 68",
        original_index=0,
        distance=None,
        rank=1,
    ).model_copy(update=updates)


def reference(c):
    return NormativeReference(
        chunk_id=c.id,
        norm_id="ufpi-177-2012",
        source=c.source,
        article=c.article_number,
        display_text="Art. 68",
        temporal_role="eligible",
    )


def test_hierarchy_and_span_text():
    text = "Art. 68. Texto inicial do caput.\nI - Primeiro inciso do caput.\na) Primeira alínea.\nb) Segunda alínea.\n§ 1º Primeiro parágrafo.\nI - Inciso do parágrafo.\n§ 2º Segundo parágrafo.\nII - Outro inciso."
    spans = {s.span_id: s for s in segment_chunk(chunk(text), "ufpi-177-2012")}
    root = "ufpi-177-2012:art68"
    assert spans[root].text == text
    assert spans[root + ":caput"].text == text.split("\n§ 1º")[0]
    assert spans[root + ":p1"].text == "§ 1º Primeiro parágrafo.\nI - Inciso do parágrafo."
    assert spans[root + ":p2:incII"].parent_id == root + ":p2"
    assert spans[root + ":caput:incI:ala"].text == "a) Primeira alínea."
    assert spans[root + ":caput:incI:alb"].parent_id == root + ":caput:incI"
    with pytest.raises(AttributeError):
        spans[root].text = "alterado"


@pytest.mark.parametrize(
    "marker,label", [("$ 2º", "2"), ("S$ 1º", "1"), ("8 2º", "2"), ("Parágrafo único", "unico")]
)
def test_ocr_and_cross_reference(marker, label):
    spans = segment_chunk(
        chunk(
            f"Art. 68. Conforme § 9º e inciso V.\n{marker} Texto do parágrafo.\nl - Inciso inicial.\nII - Inciso seguinte."
        ),
        "ufpi-177-2012",
    )
    assert [s.label for s in spans if s.kind == "paragraph"] == [label]
    assert [s.label for s in spans if s.kind == "inciso"] == ["I", "II"]


def test_only_final_reference_ids_and_norm_identity_are_used():
    c = chunk("Art. 68. Texto normativo disponível.", norm_id="wrong")
    spans = segment_evidence([c, c.model_copy(update={"id": "excluded"})], [reference(c)])
    assert len(spans) == 2
    assert all(s.norm_id == "ufpi-177-2012" and s.chunk_id == "c1" for s in spans.values())
