import html
import json
import re
import unicodedata

import pytest

from rag_baseline.content_locators import evidence_subdivisions
from rag_baseline.corpus_canonical import (
    _EMPHASIS,
    _ITALIC,
    _LINE_SYNTAX,
    _STRAY_ASTERISK,
    CORPUS_DIR,
    TARGETS,
    build_canonical_corpora,
    canonicalize,
)


@pytest.mark.parametrize(
    "before,after",
    [
        # Res. 177/2012, art. 68 (graduation markdown).
        (
            "**Art. 68. O estágio curricular obrigatório envolve:**\n1. I - Coordenadoria;",
            "Art. 68. O estágio curricular obrigatório envolve:\nI - Coordenadoria;",
        ),
        (
            "> § 1º A Coordenadoria tem como atribuições:\n> * a) viabilizar as condições;",
            "§ 1º A Coordenadoria tem como atribuições:\na) viabilizar as condições;",
        ),
        # Res. 956/2025 list syntax around repaired markers.
        (
            "- § 1º O Plano deverá conter:\n- I -dados do discente;",
            "§ 1º O Plano deverá conter:\nI - dados do discente;",
        ),
        (
            "2. I -Documento de identidade;\n- a) Para candidatos:",
            "I - Documento de identidade;\na) Para candidatos:",
        ),
        ("24. III — são aceitos atestados", "III - são aceitos atestados"),
        # LaTeX fractions from the PDF conversion.
        ("decorridos $\\frac{1}{3}$ (um terço) do período", "decorridos 1/3 (um terço) do período"),
        # Residual HTML entity and heading marks.
        ("Pesquisa &amp; Inovação", "Pesquisa & Inovação"),
        ("## CAPÍTULO II", "CAPÍTULO II"),
        ("texto    com   espaços", "texto com espaços"),
        # Res. 177/2012: markdown italics and a stray conversion asterisk.
        ("em outro *campus* desta instituição", "em outro campus desta instituição"),
        (
            "o *caput* do artigo e a matrícula *ex officio*",
            "o caput do artigo e a matrícula ex officio",
        ),
        ("constituindo-se sua diretriz primordial.*", "constituindo-se sua diretriz primordial."),
    ],
)
def test_canonicalize(before, after):
    assert canonicalize(before) == after


def test_prose_numbers_and_inline_marks_are_kept():
    text = "Art. 5. São 2. as vagas; o aluno com nota 7/10 e 3 * 2 créditos."
    assert canonicalize(text) == text


def words(text):
    text = unicodedata.normalize("NFC", text)
    return re.findall(r"[^\W\d_]+", text)


def numbers(text, *, source=False):
    text = re.sub(r"\\[a-z]+", " ", html.unescape(text))
    if source:
        text = _STRAY_ASTERISK.sub("", _ITALIC.sub(r"\1", _EMPHASIS.sub("", text)))
        lines = []
        for line in text.splitlines():
            line = line.strip()
            changed = True
            while changed:
                previous = line
                for _, pattern in _LINE_SYNTAX:
                    line = pattern.sub("", line, count=1)
                changed = line != previous
            lines.append(line)
        text = "\n".join(lines)
    return re.findall(r"\d+", text)


def test_corpora_keep_every_word_and_every_provision():
    published, log = build_canonical_corpora(CORPUS_DIR)
    assert log["entries"]
    for source, target in TARGETS.items():
        before = json.loads((CORPUS_DIR / source).read_text(encoding="utf-8"))
        after = json.loads(published[target])
        assert len(before) == len(after)
        for old, new in zip(before, after, strict=True):
            assert {k: v for k, v in old.items() if k not in ("conteudo", "metadados")} == {
                k: v for k, v in new.items() if k not in ("conteudo", "metadados")
            }
            # Metadata is identical except hierarchy names, which keep their words.
            names = {"titulo_nome", "capitulo_nome", "secao_nome", "subsecao_nome"}
            om, nm = old.get("metadados") or {}, new.get("metadados") or {}
            assert {k: v for k, v in om.items() if k not in names} == {
                k: v for k, v in nm.items() if k not in names
            }
            for k in names & om.keys():
                assert words(str(om[k])) == words(str(nm[k])) and "*" not in str(nm[k] or "")
            # The same words in the same order: only syntax is removed.
            # LaTeX command names and HTML entity names are syntax, not words of the norm.
            source_words = words(re.sub(r"\\[a-z]+", " ", html.unescape(old["conteudo"])))
            assert source_words == words(new["conteudo"])
            assert numbers(old["conteudo"], source=True) == numbers(new["conteudo"]), (
                f"numbers changed in {source}, provision {old.get('id')}"
            )
            # The same legal structure.
            assert evidence_subdivisions(old["conteudo"]) == evidence_subdivisions(new["conteudo"])
            for mark in ("*", "$\\frac", "&amp;"):
                assert mark not in new["conteudo"]
            assert not re.search(r"(?m)^\s*(?:>|[-*+]\s|#{1,6}\s)", new["conteudo"])


def test_preservation_check_rejects_a_changed_deadline(monkeypatch):
    build = build_canonical_corpora

    def changed_deadline(corpus_dir):
        published, log = build(corpus_dir)
        target = TARGETS["graduacao_setor_v2.json"]
        provisions = json.loads(published[target])
        provision = next(p for p in provisions if "30 (trinta) dias" in p["conteudo"])
        provision["conteudo"] = provision["conteudo"].replace(
            "30 (trinta) dias", "90 (trinta) dias", 1
        )
        published[target] = json.dumps(provisions, ensure_ascii=False)
        return published, log

    monkeypatch.setitem(globals(), "build_canonical_corpora", changed_deadline)
    with pytest.raises(AssertionError, match="numbers changed"):
        test_corpora_keep_every_word_and_every_provision()


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Art. 5. São 2. as vagas; nota 7/10 e 3 * 2 créditos.", ["5", "2", "7", "10", "3", "2"]),
        ("> - **24. III — prazo de 30 dias**", ["30"]),
        ("decorridos $\\frac{1}{3}$ do período", ["1", "3"]),
        ("30 dias para requerer; 90 dias para recorrer.", ["30", "90"]),
    ],
)
def test_source_numbers_ignore_only_conversion_syntax(text, expected):
    assert numbers(text, source=True) == expected


def test_canonical_corpora_are_published_and_reproducible():
    published, log = build_canonical_corpora(CORPUS_DIR)
    for target, text in published.items():
        assert (CORPUS_DIR / target).read_text(encoding="utf-8") == text
    assert json.loads((CORPUS_DIR / "canonical_text_log_v1.json").read_text("utf-8")) == log


def test_v4_profile_loads_the_same_chunks_as_v3(monkeypatch):
    from pathlib import Path

    from rag_baseline.config import BaselineSettings
    from rag_baseline.corpus import load_corpus
    from rag_baseline.profiles import apply_profile

    monkeypatch.chdir(Path(__file__).resolve().parents[2])
    v3 = apply_profile(BaselineSettings(), "duas-regulacoes-v3")
    v4 = apply_profile(BaselineSettings(), "duas-regulacoes-v4")
    assert v4.CHROMA_COLLECTION not in (v3.CHROMA_COLLECTION, "ufpi_duas_regulacoes_setor")
    for old, new in zip(v3.CORPUS_SOURCES, v4.CORPUS_SOURCES, strict=True):
        before = load_corpus(old.path, id_prefix=old.id_prefix)
        after = load_corpus(new.path, id_prefix=new.id_prefix)
        assert [c.id for c in before] == [c.id for c in after]
        assert [c.article_number for c in before] == [c.article_number for c in after]
