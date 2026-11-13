"""Inspectable final evidence and single bibliography through the actual TCC renderer."""

from collections import Counter

import test_tcc_ui as ui_cases

from rag_baseline.normative_output import compose_answer
from schema import ChatMessage

controlled = ui_cases.controlled


def test_one_source_region_and_exact_evidence_details_without_content_parsing(controlled):
    at, fake = ui_cases.start(controlled)
    source = ui_cases.normative().normative_result
    texts = ["Texto exato autorizado.\nArtigo 68: condições.", "Texto exato da subdivisão: § 1º."]
    refs = [
        reference.model_copy(update={"evidence_text": texts[index % 2]})
        for index, reference in enumerate(source.references[:2])
    ]
    refs.append(refs[0])
    body = "Resposta substantiva com art. 999 como teste de transporte."
    answer = compose_answer(source.temporal_status_text, body, refs)
    value = source.model_copy(update={"answer": answer, "references": refs})
    fake.events = [ChatMessage(type="ai", content=answer, normative_result=value)]
    ui_cases.send(at)
    view = ui_cases.sources(at)
    assert len(view.entries) == 3
    assert "Fontes:" not in at.chat_message[-1].markdown[0].value
    titles = "\n".join(entry.title for entry in view.entries)
    assert "Art. 68" in titles and "999" not in titles
    assert Counter(entry.text for entry in view.entries) == Counter([*texts, texts[0]])
    assert "§ 1º" in ui_cases.visible(at)
    assert not any(ref.chunk_id in ui_cases.visible(at) for ref in refs)
    at.run(timeout=15)
    again = ui_cases.sources(at)
    assert Counter(entry.text for entry in again.entries) == Counter([*texts, texts[0]])


def test_legacy_reference_without_text_is_explicit_and_does_not_claim_attribution(controlled):
    at, fake = ui_cases.start(controlled)
    fake.events = [ui_cases.normative()]
    ui_cases.send(at)
    view = ui_cases.sources(at)
    assert len(view.entries) == 3
    assert "Texto integral indisponível nesta resposta." in ui_cases.visible(at)
    assert "não indica qual trecho fundamenta" in view.hint
    assert "sustentam" not in ui_cases.visible(at)
    assert "vigente" not in ui_cases.visible(at)
