"""The packaged registry must remain usable with the release corpus profile."""

import shlex
import shutil

from rag_baseline.config import BaselineSettings
from rag_baseline.profiles import apply_profile
from rag_baseline.versioning import REGISTRY_PATH, NormativeRegistry

ROOT = REGISTRY_PATH.parent.parent


def test_backend_assets_support_registry_and_v4_profile(tmp_path):
    (tmp_path / "code").mkdir()
    dockerfile = (ROOT / "deploy/backend/Dockerfile").read_text(encoding="utf-8")
    included = (ROOT / "deploy/backend/Dockerfile.dockerignore").read_text(
        encoding="utf-8"
    ).splitlines()
    for line in dockerfile.splitlines():
        if not line.startswith("COPY "):
            continue
        for source in shlex.split(line)[1:-1]:
            if not source.startswith(("data/", "evaluation/corpora/")):
                continue
            assert f"!{source}" in included
            target = tmp_path / source
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / source, target)

    registry = NormativeRegistry.load(tmp_path / "data/normative_registry.json")
    assert {norm.norm_id for norm in registry.norms} == {
        "ufpi-177-2012", "ufpi-956-2025", "ufpi-658-2024", "ufpi-1056-2026"
    }
    settings = apply_profile(BaselineSettings(_env_file=None), "duas-regulacoes-v4")
    assert settings.CHROMA_COLLECTION == "ufpi_duas_regulacoes_setor_v4"
    assert len(settings.CORPUS_SOURCES) == 4
    for source in settings.CORPUS_SOURCES:
        assert (tmp_path / "code" / source.path).is_file()
