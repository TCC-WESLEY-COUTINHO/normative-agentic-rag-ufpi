"""Reference disclosure using only typed identity and evidence."""

import streamlit.components.v1 as components
import test_tcc_ui as ui
from streamlit.testing.v1 import AppTest

from rag_baseline import ui_presentation
from schema import ChatMessage

controlled = ui.controlled


def references():
    base = ui.normative().normative_result.references[0]
    return [
        base.model_copy(
            update=dict(
                chunk_id=f"{norm}-{article}",
                norm_id=f"ufpi-{norm}",
                source=f"Resolução {norm.replace('-', '/')}",
                article=article,
                display_text="Opaque authorized display",
                temporal_role="eligible",
                evidence_text=("Texto preservado. " * 60 + "FIM COMPLETO")
                if article == "34"
                else f"Evidência {norm}/{article}",
            )
        )
        for norm, article in [
            ("956-2025", "34"),
            ("177-2012", "112"),
            ("956-2025", "35"),
            ("177-2012", "115"),
            ("956-2025", "38"),
        ]
    ]


def test_grouping_preserves_first_order_and_every_original_reference():
    refs = references()
    distinct_same_article = refs[0].model_copy(
        update={"chunk_id": "other-chunk", "evidence_text": "Outra evidência intacta."}
    )
    refs.extend([distinct_same_article, refs[0]])
    before = [ref.model_dump() for ref in refs]
    assert hasattr(ui_presentation, "group_references"), "Pure typed grouping helper is missing"
    grouped = ui_presentation.group_references(refs)
    assert [group.norm_id for group in grouped] == ["ufpi-956-2025", "ufpi-177-2012"]
    assert [group.label for group in grouped] == ["Resolução 956/2025", "Resolução 177/2012"]
    assert [len(group.references) for group in grouped] == [5, 2]
    assert list(grouped[0].references) == [refs[0], refs[2], refs[4], refs[5], refs[6]]
    assert all(
        got is want
        for got, want in zip(grouped[0].references, [refs[0], refs[2], refs[4], refs[5], refs[6]])
    )
    assert [ref.model_dump() for ref in refs] == before


def send_references(
    at, fake, answer="Resposta sem identificação normativa. Art. 999 da Resolução 123/2099."
):
    value = ui.normative().normative_result.model_copy(
        update={"references": references(), "answer": answer}
    )
    fake.events = [ChatMessage(type="ai", content=value.answer, normative_result=value)]
    ui.send(at)
    return value


def test_disclosure_holds_all_evidence_grouped_and_closed_without_widgets(controlled, monkeypatch):
    html_calls = []
    render = components.html
    monkeypatch.setattr(components, "html", lambda *a, **k: (html_calls.append(a), render(*a, **k)))
    at, fake = ui.start(controlled)
    value = send_references(at, fake)
    view = ui.sources(at)
    assert "Fontes normativas" in view.summary and "2 normas · 5 trechos" in view.summary
    assert not view.sources_open, "The source list starts collapsed to keep the answer on screen"
    assert view.norms == ["Resolução 956/2025", "Resolução 177/2012"]
    assert view.open_details == 0
    assert [(entry.norm, entry.title) for entry in view.entries] == [
        ("Resolução 956/2025", "Art. 34"),
        ("Resolução 956/2025", "Art. 35"),
        ("Resolução 956/2025", "Art. 38"),
        ("Resolução 177/2012", "Art. 112"),
        ("Resolução 177/2012", "Art. 115"),
    ]
    assert sorted(entry.text for entry in view.entries) == sorted(
        reference.evidence_text for reference in value.references
    )
    assert not at.chat_message[-1].button, "Opening a source must not need a server rerun"
    assert not at.expander and not at.checkbox
    assert "999" not in " ".join(entry.title for entry in view.entries)
    assert at.session_state.messages[-1].normative_result.references == value.references


def test_each_message_has_its_own_sources_and_a_new_conversation_has_none(controlled):
    at, fake = ui.start(controlled)
    send_references(at, fake)
    ui.send(at, "Outra pergunta")
    assert ui.sources(at, -1) is not None and ui.sources(at, 1) is not None
    at.sidebar.button[0].click().run(timeout=15)
    assert not at.chat_message


def test_installed_streamlit_rejects_nested_expanders():
    # Characterize the upstream limitation the proposed native composition avoids.
    at = AppTest.from_string(
        'import streamlit as st\nwith st.expander("outer"):\n    with st.expander("inner"):\n        st.write("evidence")'
    ).run(timeout=15)
    assert len(at.exception) == 1
    assert "Expanders may not be nested" in at.exception[0].message
