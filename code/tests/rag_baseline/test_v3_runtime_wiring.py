import pytest

from rag_baseline.api import _Runtime, resolve_settings
from rag_baseline.config import BaselineSettings


def test_defaults_select_v3_4_generation_and_canonical_corpus():
    settings = BaselineSettings(_env_file=None)
    assert settings.GENERATION_MODE == "cited_v3"
    assert settings.CORPUS_PROFILE == "duas-regulacoes-v4"
    assert resolve_settings(settings).CHROMA_COLLECTION == "ufpi_duas_regulacoes_setor_v4"


def test_v2_generation_and_corpus_remain_explicitly_configurable():
    settings = BaselineSettings(
        _env_file=None, GENERATION_MODE="free_text_v2", CORPUS_PROFILE="duas-regulacoes"
    )
    assert settings.GENERATION_MODE == "free_text_v2"
    assert settings.CORPUS_PROFILE == "duas-regulacoes"
    assert resolve_settings(settings).CHROMA_COLLECTION == "ufpi_duas_regulacoes_setor"


def test_corpus_profile_selects_the_repaired_collection():
    settings = BaselineSettings(_env_file=None, CORPUS_PROFILE="duas-regulacoes-v3")
    assert resolve_settings(settings).CHROMA_COLLECTION == "ufpi_duas_regulacoes_setor_v3"


def test_unknown_generation_mode_is_rejected():
    with pytest.raises(ValueError):
        BaselineSettings(_env_file=None, GENERATION_MODE="free_text_v9")


@pytest.mark.parametrize("mode", ["free_text_v2", "cited_v3"])
def test_api_runtime_service_uses_the_configured_mode(mode, monkeypatch):
    # No real HTTP client: an unclosed one leaks file descriptors across the suite.
    monkeypatch.setattr("rag_baseline.api.OpenRouterClient", lambda **kwargs: object())
    settings = BaselineSettings(_env_file=None, OPENROUTER_API_KEY="k", GENERATION_MODE=mode)
    built = _Runtime(settings)
    built._store = object()
    assert built.service().generation_mode == mode
