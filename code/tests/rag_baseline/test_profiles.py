from pathlib import Path

import pytest

from rag_baseline.config import BaselineSettings
from rag_baseline.profiles import ProfileError, apply_profile


def base_settings() -> BaselineSettings:
    return BaselineSettings(_env_file=None)


def test_resolucao_956_profile_is_isolated_from_graduation() -> None:
    graduation = apply_profile(base_settings(), "graduacao")
    resolution = apply_profile(base_settings(), "resolucao-956")

    assert graduation.CHROMA_COLLECTION == "ufpi_graduacao_177_2012"
    assert resolution.CHROMA_COLLECTION == "ufpi_resolucao_956_2025"
    assert resolution.CHROMA_COLLECTION != graduation.CHROMA_COLLECTION
    assert resolution.CORPUS_PATH == Path("scripts/chunks_resolucao_956_2025_v1.json")
    assert resolution.CORPUS_ID_PREFIX == "ufpi-956-2025"
    assert resolution.CORPUS_NAME == "Resolução CEPEX/UFPI nº 956/2025"


def test_unknown_profile_fails_clearly() -> None:
    with pytest.raises(ProfileError, match="Perfil de corpus desconhecido"):
        apply_profile(base_settings(), "inexistente")
