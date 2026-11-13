"""Complete only the test environment: Git, fixture assets and legacy app cwd."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import linux_verification as verification
from operations import IMAGE, OUT, ROOT, decision, run, write

base = Path(json.loads((OUT / "temporary_workspace.json").read_text())["path"])
context = base / "test-context"
context.mkdir()
(context / "Dockerfile").write_text(
    f"FROM {IMAGE}\nRUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*\n"
)
(context / "legacy_app_cwd.py").write_text(
    'import pytest\nfrom pathlib import Path\n@pytest.fixture(autouse=True)\ndef legacy_app_cwd(request, monkeypatch):\n    if request.node.path.parent.name == "app":\n        monkeypatch.chdir(Path("/app/code/tests/app"))\n'
)
helper = "normative-agentic-rag-ufpi:runtime-smoke-test-tools"
run(
    "test_tools_image_build",
    [
        "docker",
        "build",
        "--pull=false",
        "-f",
        str(context / "Dockerfile"),
        "-t",
        helper,
        str(context),
    ],
    check=True,
)
original = verification.run


def complete_context(name, args, **kwargs):
    assert args[:2] == ["docker", "run"]
    index = args.index(IMAGE)
    args[index] = helper
    extra = [
        "--ulimit",
        "nofile=65536:65536",
        "--mount",
        f"type=bind,src={context},dst=/test-context,readonly",
        "--mount",
        f"type=bind,src={ROOT / '.git'},dst=/app/.git,readonly",
        "--mount",
        f"type=bind,src={ROOT / 'code/scripts/chunks_v2.json'},dst=/app/code/scripts/chunks_v2.json,readonly",
        "--mount",
        f"type=bind,src={ROOT / 'code/scripts/chunks_resolucao_956_2025_v1.json'},dst=/app/code/scripts/chunks_resolucao_956_2025_v1.json,readonly",
        "-e",
        "GIT_CONFIG_COUNT=1",
        "-e",
        "GIT_CONFIG_KEY_0=safe.directory",
        "-e",
        "GIT_CONFIG_VALUE_0=/app",
        "-e",
        "PYTHONPYCACHEPREFIX=/tmp/isolated-pycache",
    ]
    args = [
        a.replace(
            "PYTHONPATH=/test-deps:/app/code/src",
            "PYTHONPATH=/test-context:/test-deps:/app/code/src",
        )
        for a in args
    ]
    args = args[:2] + extra + args[2:] + ["-p", "legacy_app_cwd"]
    return original(name, args, **kwargs)


verification.run = complete_context
decision(
    "complete_test_context",
    "Use auxiliary local test-tools image adding Git only, bind two existing corpus fixtures and .git read-only, use test-only cwd fixture for legacy AppTest and isolate bytecode caches.",
    "Remaining failures were missing test-only files/Git and legacy relative UI test paths, not service packaging. Production image and source unchanged; no new science or UI implementation.",
)
results = json.loads((OUT / "linux_suite_exit_codes.json").read_text())
with ThreadPoolExecutor(max_workers=2) as pool:
    jobs = {
        name: pool.submit(verification.test, "linux_tests_" + name, selection)
        for name, selection in [
            ("rag_baseline", ["tests/rag_baseline"]),
            ("full", ["tests"]),
        ]
    }
    for name, future in jobs.items():
        results[name] = future.result()
write("linux_suite_exit_codes.json", results)
write(
    "linux_final_test_context.json",
    {
        "base_runtime_image": IMAGE,
        "test_tools_image": helper,
        "git_only_added_to_test_image": True,
        "nofile": [65536, 65536],
        "legacy_app_cwd_fixture": True,
        "pycache_prefix": "/tmp/isolated-pycache",
        "fixture_mounts_readonly": [
            "code/scripts/chunks_v2.json",
            "code/scripts/chunks_resolucao_956_2025_v1.json",
            ".git",
        ],
        "production_image_unchanged": True,
    },
)
raise SystemExit(int(any(results.values())))
