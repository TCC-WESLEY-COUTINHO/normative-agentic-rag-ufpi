import pytest

from rag_baseline.agentic import is_historical_question
from rag_baseline.models import RetrievedChunk
from rag_baseline.versioning import NormativeRegistry, VersionFilter

OLD = "§ 4º O coordenador será docente efetivo, com as atribuições de:"
NEW = (
    "§ 4º O coordenador será docente efetivo, ressalvados os programas especiais, "
    "independentemente de seu vínculo com a UFPI, com as atribuições de:"
)
BASE = "Art. 68. Organização.\n§ 1º Coordenação.\n" + OLD + "\na) coordenar;\nb) informar."


def amendment():
    return dict(
        target=dict(article="68", paragraph="4"),
        amended_by="ufpi-1056-2026",
        effective_text_source="ufpi-1056-2026",
        previous_text=OLD,
        effective_text=NEW,
        legal_basis=dict(source="Ato 1056", article="1", text="Altera art. 68 §4: " + NEW),
    )


def registry(**change):
    value = amendment()
    value.update(change)
    return NormativeRegistry(
        norms=[
            dict(
                norm_id="ufpi-177-2012",
                sector="graduacao",
                sources=["Base 177"],
                amendments=[value],
            ),
            dict(norm_id="ufpi-1056-2026", sector="graduacao", sources=["Ato 1056"]),
            dict(norm_id="ufpi-956-2025", sector="pos_graduacao", sources=["Atual 956"]),
            dict(
                norm_id="ufpi-658-2024",
                sector="pos_graduacao",
                sources=["Antiga 658"],
                status="revogada",
                superseded_by="ufpi-956-2025",
                legal_basis=dict(source="Atual 956", article="62, VI", text="Revoga 658."),
            ),
        ]
    )


def chunk(norm="177-2012", article="68", content=BASE, rank=1):
    sources = {
        "177-2012": "Base 177",
        "1056-2026": "Ato 1056",
        "658-2024": "Antiga 658",
        "956-2025": "Atual 956",
    }
    return RetrievedChunk(
        id=f"ufpi-{norm}-art-{article}-idx-000000",
        content=content,
        source=sources[norm],
        article_number=article,
        article_label=f"Art. {article}",
        original_index=0,
        sector="graduacao" if norm in ("177-2012", "1056-2026") else "pos_graduacao",
        rank=rank,
        distance=0.1,
    )


def test_amendment_masks_only_changed_text_and_preserves_other_provisions():
    original = chunk()
    other = chunk(article="69", content="Art. 69. Outra regra.", rank=2)
    kept, audit = VersionFilter(registry()).apply([original, other])
    assert len(kept) == 2
    assert OLD not in kept[0].content
    assert NEW in kept[0].content
    assert "§ 1º Coordenação." in kept[0].content
    assert "a) coordenar;\nb) informar." in kept[0].content
    assert "1056" in kept[0].content
    assert original.content == BASE
    assert kept[1].content == other.content
    assert not audit.removed_references
    assert len(audit.amended_references) == 1
    assert audit.amended_references[0].original_reference == original
    assert audit.amended_references[0].amendment.target.paragraph == "4"
    assert audit.norm_statuses["ufpi-177-2012"] != "revogada"


def test_amending_act_is_eligible_and_base_is_never_excluded():
    vf = VersionFilter(registry())
    assert vf.excluded_sources() == ["Antiga 658"]
    act = chunk("1056-2026", "1", "Art. 1. " + NEW)
    kept, _ = vf.apply([act, chunk(article="69", content="Art. 69. Outra regra.")])
    assert len(kept) == 2


def test_history_preserves_previous_paragraph_without_applying_amendment():
    kept, audit = VersionFilter(registry()).apply([chunk()], historical=True)
    assert kept[0].content == BASE
    assert not audit.amended_references
    assert audit.historical


def test_unmatched_previous_text_fails_closed_only_for_target_article():
    kept, audit = VersionFilter(registry()).apply(
        [
            chunk(content="Art. 68. Unexpected conversion."),
            chunk(article="69", content="Art. 69. Outra regra."),
        ]
    )
    assert [c.article_number for c in kept] == ["69"]
    assert audit.removed_references[0].reason == "amendment_unresolved"
    assert audit.removed_references[0].norm_id == "ufpi-177-2012"


def test_current_removes_658_and_retains_956():
    kept, audit = VersionFilter(registry()).apply(
        [
            chunk("658-2024", "3", "Art. 3. Antiga."),
            chunk("956-2025", "3", "Art. 3. Atual."),
        ]
    )
    assert [c.source for c in kept] == ["Atual 956"]
    assert audit.removed_references[0].superseded_by == "ufpi-956-2025"


def test_historical_658_remains_eligible_with_revocation_audit():
    kept, audit = VersionFilter(registry()).apply(
        [chunk("658-2024", "3", "Art. 3. Antiga.")], historical=True
    )
    assert len(kept) == 1
    assert audit.norm_statuses["ufpi-658-2024"] == "revogada"


def test_explicit_according_to_revoked_act_allows_history_but_current_wins():
    kwargs = dict(obsolete_norm_ids=["ufpi-658-2024"])
    assert is_historical_question("Segundo a 658/2024, quais eram as regras?", **kwargs)
    assert is_historical_question("Segundo a 658/2024, quais os requisitos?", **kwargs)
    assert not is_historical_question("Segundo a 658/2024, qual a regra atual?", **kwargs)
    assert not is_historical_question("Segundo a 177/2012, qual a regra?", **kwargs)


@pytest.mark.parametrize(
    "title",
    [
        "Resolução CEPEX/UFPI nº 658/2024",
        "Resolução CEPEX/UFPI n. 658/2024",
        "Resolução UFPI/CEPEX nº 658/2024",
    ],
)
def test_full_official_revoked_title_is_historical_with_current_precedence(title):
    kwargs = dict(obsolete_norm_ids=["ufpi-658-2024"])
    assert is_historical_question(f"Segundo a {title}, quais os requisitos?", **kwargs)
    assert not is_historical_question(f"Segundo a {title}, qual a regra atual?", **kwargs)


@pytest.mark.parametrize(
    "change",
    [
        dict(amended_by="missing"),
        dict(effective_text_source="ufpi-658-2024"),
        dict(previous_text=""),
        dict(effective_text=""),
    ],
)
def test_invalid_amendment_is_rejected(change):
    with pytest.raises(ValueError):
        registry(**change)


def test_new_corpus_metadata_is_preserved_without_changing_legacy_metadata():
    from rag_baseline.corpus import normalize_chunk
    from rag_baseline.vector_store import ChromaVectorStore

    legacy = dict(
        conteudo="Art. 1. Texto.",
        metadados=dict(fonte="Ato 1056", artigo_numero="1", setor="graduacao"),
    )
    previous = ChromaVectorStore._metadata(normalize_chunk(legacy, 0))
    assert "norm_id" not in previous and "normative_status" not in previous
    legacy["metadados"].update(norm_id="ufpi-1056-2026", normative_status="desconhecida")
    current = normalize_chunk(legacy, 0, id_prefix="ufpi-1056-2026")
    assert current.norm_id == "ufpi-1056-2026"
    assert ChromaVectorStore._metadata(current)["normative_status"] == "desconhecida"


def test_outdated_provision_metric_distinguishes_current_history_and_overlay():
    from rag_baseline.agentic_evaluation import version_metrics

    vf = VersionFilter(registry())
    target = dict(norm_id="ufpi-177-2012", article="68", paragraph="4")
    before = version_metrics([chunk()], vf, target_provision=target)
    assert before["outdated_provision_exposure"] == 1
    assert before["obsolete_context_n"] == 0
    assert before["compliance_violation"] == 1
    final, audit = vf.apply([chunk()])
    after = version_metrics(
        final, vf, target_provision=target, audit=audit, current_evidence={("ufpi-1056-2026", "1")}
    )
    assert after["outdated_provision_exposure"] == 0
    assert after["current_norm_hit_at_5"] == 1
    assert (
        version_metrics([chunk()], vf, historical=True, target_provision=target)[
            "outdated_provision_exposure"
        ]
        is None
    )
    assert version_metrics([], vf)["outdated_provision_exposure"] is None


def test_documentary_registry_records_real_two_types_without_revoking_base():
    records = {n.norm_id: n for n in NormativeRegistry.load().norms}
    assert records["ufpi-658-2024"].status == "revogada"
    assert records["ufpi-658-2024"].superseded_by == "ufpi-956-2025"
    base = records["ufpi-177-2012"]
    assert base.status != "revogada"
    assert len(base.amendments) == 1
    change = base.amendments[0]
    assert change.target.article == "68" and change.target.paragraph == "4"
    assert change.amended_by == "ufpi-1056-2026"
    assert "independentemente de seu vínculo com a UFPI" in change.effective_text
    assert "independentemente de seu vínculo com a UFPI" not in change.previous_text


def test_combined_profile_adds_only_two_new_corpora_with_existing_collection():
    from rag_baseline.config import BaselineSettings
    from rag_baseline.profiles import apply_profile

    settings = apply_profile(BaselineSettings(_env_file=None), "duas-regulacoes")
    assert settings.CHROMA_COLLECTION == "ufpi_duas_regulacoes_setor"
    assert {s.id_prefix for s in settings.CORPUS_SOURCES} == {
        "ufpi-177-2012",
        "ufpi-956-2025",
        "ufpi-658-2024",
        "ufpi-1056-2026",
    }


def test_real_graduation_corpus_keeps_every_article_and_only_updates_68_in_memory():
    from rag_baseline.corpus import load_corpus
    from rag_baseline.versioning import REGISTRY_PATH

    root = REGISTRY_PATH.parent.parent
    originals = load_corpus(root / "evaluation/corpora/graduacao_setor_v2.json")
    retrieved = [
        RetrievedChunk(**c.model_dump(), rank=i, distance=0.1) for i, c in enumerate(originals, 1)
    ]
    vf = VersionFilter(NormativeRegistry.load())
    final, audit = vf.apply(retrieved, top_k=len(retrieved))
    assert len(final) == len(originals) == 376
    assert not audit.removed_references
    assert len(audit.amended_references) == 1
    for original, current in zip(originals, final, strict=True):
        assert current.id == original.id
        if original.article_number != "68":
            assert current.content == original.content
        else:
            assert "independentemente de seu vínculo com a UFPI" in current.content
            assert "\n> * a)" in current.content and "\n> * g)" in current.content
    historical, audit = vf.apply(retrieved, historical=True, top_k=len(retrieved))
    assert [c.content for c in historical] == [c.content for c in originals]
    assert not audit.amended_references
