import pytest
from pathlib import Path
@pytest.fixture(autouse=True)
def legacy_app_cwd(request, monkeypatch):
    if request.node.path.parent.name == "app":
        monkeypatch.chdir(Path("/app/code/tests/app"))
