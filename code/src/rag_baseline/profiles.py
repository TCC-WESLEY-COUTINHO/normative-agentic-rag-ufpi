from dataclasses import dataclass
from pathlib import Path

from rag_baseline.config import BaselineSettings, CorpusSource


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class CorpusProfile:
    corpus_path: Path
    collection: str
    id_prefix: str
    norm_name: str
    sources: tuple[CorpusSource, ...] = ()


PROFILES = {
    "duas-regulacoes": CorpusProfile(
        corpus_path=Path("../evaluation/corpora/graduacao_setor_v2.json"),
        collection="ufpi_duas_regulacoes_setor",
        id_prefix="ufpi",
        norm_name="Normas de graduação e pós-graduação da UFPI",
        sources=(
            CorpusSource(
                path=Path("../evaluation/corpora/graduacao_setor_v2.json"),
                id_prefix="ufpi-177-2012",
                norm_name="Resolução nº 177/2012 CEPEX/UFPI",
            ),
            CorpusSource(
                path=Path("../evaluation/corpora/pos_graduacao_setor_v2.json"),
                id_prefix="ufpi-956-2025",
                norm_name="Resolução CEPEX/UFPI nº 956/2025",
            ),
            CorpusSource(
                path=Path("../evaluation/corpora/658_2024_temporal_v1.json"),
                id_prefix="ufpi-658-2024",
                norm_name="Resolução CEPEX/UFPI nº 658/2024",
            ),
            CorpusSource(
                path=Path("../evaluation/corpora/1056_2026_temporal_v1.json"),
                id_prefix="ufpi-1056-2026",
                norm_name="Resolução CEPEX/UFPI nº 1.056/2026",
            ),
        ),
    ),
    "graduacao-setor-v2": CorpusProfile(
        corpus_path=Path("../evaluation/corpora/graduacao_setor_v2.json"),
        collection="ufpi_graduacao_setor_v2",
        id_prefix="ufpi-177-2012",
        norm_name="Resolução nº 177/2012 CEPEX/UFPI",
    ),
    "pos-graduacao-setor-v2": CorpusProfile(
        corpus_path=Path("../evaluation/corpora/pos_graduacao_setor_v2.json"),
        collection="ufpi_pos_graduacao_setor_v2",
        id_prefix="ufpi-956-2025",
        norm_name="Resolução CEPEX/UFPI nº 956/2025",
    ),
    "graduacao": CorpusProfile(
        corpus_path=Path("scripts/chunks_v2.json"),
        collection="ufpi_graduacao_177_2012",
        id_prefix="ufpi-177-2012",
        norm_name="Resolução nº 177/2012 CEPEX/UFPI",
    ),
    "resolucao-956": CorpusProfile(
        corpus_path=Path("scripts/chunks_resolucao_956_2025_v1.json"),
        collection="ufpi_resolucao_956_2025",
        id_prefix="ufpi-956-2025",
        norm_name="Resolução CEPEX/UFPI nº 956/2025",
    ),
}


def profile_names() -> tuple[str, ...]:
    return tuple(PROFILES)


def apply_profile(settings: BaselineSettings, profile_name: str) -> BaselineSettings:
    try:
        profile = PROFILES[profile_name]
    except KeyError as exc:
        available = ", ".join(profile_names())
        raise ProfileError(
            f"Perfil de corpus desconhecido: {profile_name}. Disponíveis: {available}."
        ) from exc

    return settings.model_copy(
        update={
            "CORPUS_PATH": profile.corpus_path,
            "CHROMA_COLLECTION": profile.collection,
            "CORPUS_ID_PREFIX": profile.id_prefix,
            "CORPUS_NAME": profile.norm_name,
            "CORPUS_SOURCES": profile.sources,
        }
    )
