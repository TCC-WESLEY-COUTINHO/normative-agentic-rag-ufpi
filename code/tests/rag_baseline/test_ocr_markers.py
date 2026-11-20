import json
from pathlib import Path

import pytest

from rag_baseline.ocr_markers import (
    CORPUS_DIR,
    TARGETS,
    build_corrected_corpora,
    repair_markers,
)

REPO = Path(__file__).resolve().parents[3]


def lines(text):
    corrected, changes = repair_markers(text)
    return corrected.splitlines(), changes


@pytest.mark.parametrize(
    "before,after",
    [
        ("- $ 1º O Plano deverá conter:", "- § 1º O Plano deverá conter:"),
        ("- S$ 2º O prazo será contado.", "- § 2º O prazo será contado."),
        ("- 8 3º A comissão decidirá.", "- § 3º A comissão decidirá."),
        ("- S 4º A coordenação publicará.", "- § 4º A coordenação publicará."),
        ("$ 4º O coordenador de estágio.", "§ 4º O coordenador de estágio."),
    ],
)
def test_paragraph_sign(before, after):
    corrected, changes = lines(before)
    assert corrected == [after]
    assert [c["rule"] for c in changes] == ["paragraph_sign"]


def test_list_numbering_and_ordinary_numbers_are_not_paragraphs():
    text = "8. Os documentos exigidos.\n- 8 dias úteis para recurso.\nSegundo o art. 8."
    assert repair_markers(text) == (text, [])


def test_transliteration_follows_the_sequence():
    text = "Art. 9.\n- | -primeiro;\n- Il -segundo;\n- Ill -terceiro;\n- IV -quarto;"
    corrected, changes = lines(text)
    assert corrected[1:] == [
        "- I -primeiro;",
        "- II -segundo;",
        "- III -terceiro;",
        "- IV -quarto;",
    ]
    assert {c["rule"] for c in changes} == {"inciso_transliteration"}


def test_dropped_stroke_is_repaired_only_by_sequence():
    # Res. 658/2024, art. 58: the official text layer reads I, II, III, IV.
    text = "- $ 1º O Plano deverá conter:\n- | -dados;\n- Il -dados do componente;\n- Il -objetivos;\n- IV -objetivos do Estágio;"
    corrected, changes = lines(text)
    assert corrected[1:] == [
        "- I -dados;",
        "- II -dados do componente;",
        "- III -objetivos;",
        "- IV -objetivos do Estágio;",
    ]
    assert [c["rule"] for c in changes if c["line"] == 3] == ["inciso_transliteration"]
    assert [c["rule"] for c in changes if c["line"] == 4] == ["inciso_sequence"]


def test_lists_restart_at_one_inside_each_group():
    # Res. 956/2025, art. 33: the glued "IlCPF" is confirmed by the III that follows it.
    text = "- a) Brasileiros:\n2. | -Identidade;\n3. IlCPF;\n4. Ill -certificado;\n- b) Estrangeiros:\n12. | -Passaporte;\n13. Il -Visto;"
    corrected, changes = lines(text)
    assert corrected == [
        "- a) Brasileiros:",
        "2. I -Identidade;",
        "3. II - CPF;",
        "4. III -certificado;",
        "- b) Estrangeiros:",
        "12. I -Passaporte;",
        "13. II -Visto;",
    ]
    assert "inciso_glued" in {c["rule"] for c in changes}


def test_sequence_never_shortens_a_reading():
    # Pós, art. with a missing II line: "Ill" is III and the following IV agrees with it.
    text = "- | -primeiro;\n- Ill -descumprimento dos prazos;\n- IV -reprovação."
    corrected, changes = lines(text)
    assert corrected == ["- I -primeiro;", "- III -descumprimento dos prazos;", "- IV -reprovação."]
    assert ("sequence_break", False) in [(c["rule"], c["changed"]) for c in changes]


def test_split_glyph_is_resolved_by_the_following_numeral():
    # Res. 658/2024 (official text layer): "I|l" is II because the next item is III.
    text = "- | -propor;\n- I|l -propor aos órgãos;\n- Ill -propor para aprovação;"
    corrected, changes = lines(text)
    assert corrected == [
        "- I -propor;",
        "- II -propor aos órgãos;",
        "- III -propor para aprovação;",
    ]
    assert [c["rule"] for c in changes if c["line"] == 2] == ["inciso_sequence"]


def test_last_item_out_of_sequence_keeps_its_reading_and_is_flagged():
    text = "- | -primeiro;\n- Ill -último;"
    corrected, changes = lines(text)
    assert corrected == ["- I -primeiro;", "- III -último;"]
    assert ("sequence_break", False) in [(c["rule"], c["changed"]) for c in changes]


@pytest.mark.parametrize(
    "text,expected",
    [
        # Res. 956/2025, art. 21: digit one read for the stroke.
        ("- I -reprovação;\n- 11 -reprovação em duas;\n- III -descumprimento;",
         ["- I -reprovação;", "- II -reprovação em duas;", "- III -descumprimento;"]),
        # Res. 956/2025, art. 26.
        ("- I -prova;\n- II -entrevista;\n- 111 -análise;\n- IV -outras etapas.",
         ["- I -prova;", "- II -entrevista;", "- III -análise;", "- IV -outras etapas."]),
        # Res. 956/2025, art. 12: split glyph glued to a lowercase word.
        ("- VII -formalizar;\n- ViIllcriar e designar;\n- IX -encaminhar.",
         ["- VII -formalizar;", "- VIII - criar e designar;", "- IX -encaminhar."]),
        # Res. 956/2025, art. 34: dash lost before an article.
        ("22. I — a língua;\n23. I1a análise e o registro;\n24. III — são aceitos.",
         ["22. I — a língua;", "23. II - a análise e o registro;", "24. III — são aceitos."]),
    ],
)  # fmt: skip
def test_new_glyphs_are_repaired_only_when_the_sequence_confirms(text, expected):
    assert lines(text)[0] == expected


@pytest.mark.parametrize(
    "text",
    [
        "- 11 -primeira linha sem sequência.",
        "Vida acadêmica do discente.",
        "- I -primeiro;\n- Vida acadêmica;\n- III -terceiro;",
        "- I -primeiro;\n11\n3\n(três), nas disciplinas;",
    ],
)
def test_new_glyphs_without_sequence_confirmation_are_untouched(text):
    corrected, changes = repair_markers(text)
    assert corrected == text
    assert not [c for c in changes if c["changed"]]


@pytest.mark.parametrize(
    "before,after",
    [
        ("observados os incisos |, Il e Ill.", "observados os incisos I, II e III."),
        ("nos termos do inciso |.", "nos termos do inciso I."),
        ("(Inciso ll), os requisitos", "(Inciso II), os requisitos"),
        ("conforme Art. 8º, inciso |, alínea 'c';", "conforme Art. 8º, inciso I, alínea 'c';"),
    ],
)
def test_inline_inciso_references(before, after):
    corrected, changes = repair_markers(before)
    assert corrected == after
    assert [c["rule"] for c in changes] == ["inline_reference"]


def test_valid_numeral_out_of_sequence_is_flagged_not_rewritten():
    text = "- I -primeiro;\n- III -terceiro;"
    corrected, changes = lines(text)
    assert corrected == text.splitlines()
    assert [(c["rule"], c["changed"]) for c in changes] == [("sequence_break", False)]


def test_clean_text_and_prose_are_untouched():
    text = (
        "Art. 68. O estágio envolve:\nI - Coordenadoria;\nII - orientador;\n"
        "§ 1º A Coordenadoria tem atribuições:\na) viabilizar;\nIlha de texto não é inciso."
    )
    assert repair_markers(text) == (text, [])


def test_corrected_corpora_are_reproducible_and_structure_preserving():
    corrected, log = build_corrected_corpora(CORPUS_DIR)
    for source, target in TARGETS.items():
        original = json.loads((CORPUS_DIR / source).read_text(encoding="utf-8"))
        published = (CORPUS_DIR / target).read_text(encoding="utf-8")
        assert published == corrected[target]
        rebuilt = json.loads(published)
        assert len(rebuilt) == len(original)
        for before, after in zip(original, rebuilt, strict=True):
            assert {k: v for k, v in before.items() if k != "conteudo"} == {
                k: v for k, v in after.items() if k != "conteudo"
            }
            assert len(before["conteudo"].splitlines()) == len(after["conteudo"].splitlines())
    assert json.loads((CORPUS_DIR / "ocr_marker_corrections_v1.json").read_text("utf-8")) == log


def test_graduation_corpus_needs_no_marker_repair():
    items = json.loads((CORPUS_DIR / "graduacao_setor_v2.json").read_text(encoding="utf-8"))
    assert all(not [c for c in repair_markers(i["conteudo"])[1] if c["changed"]] for i in items)


def test_v3_profile_loads_the_same_chunks_with_repaired_markers(monkeypatch):
    from rag_baseline.config import BaselineSettings
    from rag_baseline.corpus import load_corpus
    from rag_baseline.profiles import apply_profile

    monkeypatch.chdir(REPO / "code")
    v2 = apply_profile(BaselineSettings(), "duas-regulacoes")
    v3 = apply_profile(BaselineSettings(), "duas-regulacoes-v3")
    assert v3.CHROMA_COLLECTION != v2.CHROMA_COLLECTION
    changed = 0
    for old, new in zip(v2.CORPUS_SOURCES, v3.CORPUS_SOURCES, strict=True):
        assert old.id_prefix == new.id_prefix
        before = load_corpus(old.path, id_prefix=old.id_prefix)
        after = load_corpus(new.path, id_prefix=new.id_prefix)
        assert [c.id for c in before] == [c.id for c in after]
        for b, a in zip(before, after, strict=True):
            assert b.model_dump(exclude={"content"}) == a.model_dump(exclude={"content"})
            changed += b.content != a.content
    assert changed > 0
