"""Run existing unit/regression suites with the built image's Linux/Python dependencies."""

import json
import sys
import tomllib
from pathlib import Path
from operations import IMAGE, OUT, ROOT, run, write

BASE = Path(json.loads((OUT / "temporary_workspace.json").read_text())["path"])
DEPS = BASE / "test-deps"
PACKAGES = tomllib.loads((ROOT / "code/uv.lock").read_text())["package"]


def install():
    needed = ["pytest", "pytest-asyncio", "pytest-env"]
    versions = {p["name"]: p["version"] for p in PACKAGES if p["name"] in needed}
    args = [
        str(BASE / "audit-venv/bin/python"),
        str(BASE / "pip.pyz"),
        "--isolated",
        "install",
        "--target",
        str(DEPS),
    ] + [f"{p}=={versions[p]}" for p in needed]
    run("linux_test_dependencies", args, check=True)
    write("linux_test_dependency_versions.json", versions)


def test(name, selection):
    args = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--mount",
        f"type=bind,src={DEPS},dst=/test-deps,readonly",
        "--mount",
        f"type=bind,src={ROOT / 'code/src'},dst=/app/code/src,readonly",
        "--mount",
        f"type=bind,src={ROOT / 'code/tests'},dst=/app/code/tests,readonly",
        "--mount",
        f"type=bind,src={ROOT / 'code/docker'},dst=/app/code/docker,readonly",
        "--mount",
        f"type=bind,src={ROOT / 'code/compose.yaml'},dst=/app/code/compose.yaml,readonly",
        "--mount",
        f"type=bind,src={ROOT / 'code/compose.prod.yaml'},dst=/app/code/compose.prod.yaml,readonly",
        "--mount",
        f"type=bind,src={ROOT / 'code/pyproject.toml'},dst=/app/code/pyproject.toml,readonly",
        "--mount",
        f"type=bind,src={ROOT / 'code/langgraph.json'},dst=/app/code/langgraph.json,readonly",
        "--mount",
        f"type=bind,src={ROOT / 'evaluation'},dst=/app/evaluation,readonly",
        "--mount",
        f"type=bind,src={ROOT / 'data'},dst=/app/data,readonly",
        "-e",
        "PYTHONPATH=/test-deps:/app/code/src",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "-e",
        "ANONYMIZED_TELEMETRY=False",
        "-e",
        "OPENAI_API_KEY=controlled-not-a-real-credential",
        "-e",
        "LANGCHAIN_TRACING_V2=false",
        "-e",
        "LANGSMITH_TRACING=false",
        "-e",
        "LANGFUSE_TRACING=false",
        IMAGE,
        "python",
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "-q",
    ] + selection
    result = run(name, args, timeout=600)
    print(result.stdout[-5000:], flush=True)
    return result.returncode


if __name__ == "__main__":
    if sys.argv[1] == "install":
        install()
    elif sys.argv[1] == "red":
        raise SystemExit(
            test(
                "healthcheck_regression_red",
                ["tests/integration/test_service_container_healthcheck.py"],
            )
        )
    elif sys.argv[1] == "green":
        raise SystemExit(
            test(
                "healthcheck_regression_green",
                ["tests/integration/test_service_container_healthcheck.py"],
            )
        )
    elif sys.argv[1] == "suites":
        selections = {
            "runtime": [
                "tests/rag_baseline/test_integrated_runtime.py",
                "tests/rag_baseline/test_runtime_packaging.py",
            ],
            "calculator": ["tests/rag_baseline", "-k", "calculator"],
            "conversation": ["tests/rag_baseline", "-k", "conversation or memory"],
            "transport": ["tests/rag_baseline", "-k", "transport"],
            "rag_baseline": ["tests/rag_baseline"],
            "service_client": ["tests/service", "tests/client"],
            "full": ["tests"],
        }
        results = {
            name: test("linux_tests_" + name, selection)
            for name, selection in selections.items()
        }
        write("linux_suite_exit_codes.json", results)
        raise SystemExit(int(any(results.values())))
