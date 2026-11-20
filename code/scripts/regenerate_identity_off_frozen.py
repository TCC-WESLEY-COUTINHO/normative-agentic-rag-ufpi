"""Capture the review replay using graph/policy sources read from the frozen tag.

Run from code/: uv run --frozen python scripts/regenerate_identity_off_frozen.py
The separate process loads frozen modules before importing the replay harness;
it never builds the expected result from the current conversation graph.
"""

import asyncio
import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path

TAG = "tcc2-cond-v3.4"
COMMIT = "1f6a03216267bbcff98123f8b3c215d3ca2deef9"
ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "code/tests/rag_baseline"
OUTPUT = TESTS / "fixtures/identity_off_frozen_v34.json"
MODULES = ("conversation_policy", "agent_graph", "conversation_graph")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def load_frozen_modules():
    import rag_baseline

    commit = git("rev-parse", f"{TAG}^{{commit}}").decode().strip()
    if commit != COMMIT:
        raise RuntimeError(f"{TAG} moved: expected {COMMIT}, found {commit}")
    sources = {}
    for short_name in MODULES:
        path = f"code/src/rag_baseline/{short_name}.py"
        source = git("show", f"{COMMIT}:{path}")
        sources[path] = hashlib.sha256(source).hexdigest()
        name = f"rag_baseline.{short_name}"
        module = types.ModuleType(name)
        module.__file__ = str(ROOT / path)
        sys.modules[name] = module
        setattr(rag_baseline, short_name, module)
        exec(compile(source, f"{TAG}:{path}", "exec"), module.__dict__)
    return rag_baseline.conversation_graph, rag_baseline.agent_graph, sources


async def main():
    sys.path[:0] = [str(ROOT / "code/src"), str(TESTS)]
    conversation, agent, sources = load_frozen_modules()
    from identity_frozen_reference import replay

    scenarios = {}
    for interpreted in (False, True):
        scenarios["interpreted" if interpreted else "base"] = await replay(
            conversation, agent.build_integrated_graph, interpreted=interpreted,
        )
    fixture = {
        "tag": TAG,
        "commit": COMMIT,
        "source_sha256": sources,
        "scenarios": scenarios,
    }
    OUTPUT.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {sum(map(len, scenarios.values()))} frozen turns to {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
