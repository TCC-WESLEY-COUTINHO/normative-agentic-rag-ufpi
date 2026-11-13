"""Audit authorized preservation, typed corpus identity and executed test evidence."""

import ast
import collections
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
BASE = "729975154f1098447b984219c8abf2fd16bf18c5"
EXPECTED = {
    "code/src/rag_baseline/agentic.py",
    "code/src/rag_baseline/normative_output.py",
    "code/src/rag_baseline/output_contracts.py",
    "code/src/rag_baseline/router.py",
    "code/src/streamlit_app.py",
    "code/tests/rag_baseline/test_normative_output.py",
    "code/tests/rag_baseline/test_retrieval_strategies.py",
    "code/tests/rag_baseline/test_terminal_scope.py",
}


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def write(name, value):
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main():
    before = read("preservation_before.json")
    changed = []
    for name, digest in before.items():
        current = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        if current != digest:
            changed.append({"path": name, "before": digest, "after": current})
    assert {r["path"] for r in changed} == EXPECTED
    index_before, index_after = read("index_before.json"), read("index_after.json")
    assert index_before == index_after and index_after["count"] == 507
    protected = {}
    for relative, allowed in {
        "code/src/rag_baseline/router.py": {"ROUTER_PROMPT"},
        "code/src/rag_baseline/output_contracts.py": {"NormativeReference"},
        "code/src/streamlit_app.py": {"render_references"},
        "code/src/rag_baseline/agentic.py": {"build_graph"},
    }.items():
        previous = subprocess.check_output(
            ["git", "show", BASE + ":" + relative], cwd=ROOT
        ).decode("utf-8")
        current = (ROOT / relative).read_text(encoding="utf-8")

        def nodes(source):
            result = {}
            for n in ast.parse(source).body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    result[n.name] = ast.dump(n, include_attributes=False)
                elif isinstance(n, ast.Assign):
                    for target in n.targets:
                        if isinstance(target, ast.Name):
                            result[target.id] = ast.dump(n, include_attributes=False)
            return result

        old, new = nodes(previous), nodes(current)
        unchanged = [key for key in old if key not in allowed]
        assert all(old[key] == new[key] for key in unchanged)
        protected[relative] = {
            "authorized_nodes": sorted(allowed),
            "other_named_nodes_identical": unchanged,
        }
    write(
        "preservation.json",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "initial_files": len(before),
            "identical": len(before) - len(changed),
            "authorized_changes": changed,
            "protected_named_nodes": protected,
            "router_v1_algorithm_schema_identical": True,
            "router_v1_prompt_changed": "two policy lines and one example; real subtype ambiguity reproduced; specific RED; user section51",
            "router_v2_and_all_other_initial_files_identical": True,
            "index": {
                "count": 507,
                "before_after_identical": True,
                "sha256": index_after["sha256"],
            },
            "note": "Working-file SHA256 baseline; scoped new evidence attributes do not normalize any original file.",
        },
    )
    rows = [
        json.loads(line)
        for line in (OUT / "execution_log.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    write(
        "test_results.json",
        {
            "runs": [r for r in rows if r["event"] == "check"],
            "overlapping_selections_not_additive": True,
        },
    )
    groups = collections.defaultdict(collections.Counter)
    tree = ET.parse(OUT / "full_final_router_contract.junit.xml")
    for case in tree.iter("testcase"):
        cls = case.attrib["classname"]
        result = (
            "skipped"
            if case.find("skipped") is not None
            else "failed"
            if case.find("failure") is not None or case.find("error") is not None
            else "passed"
        )
        groups[".".join(cls.split(".")[:2])][result] += 1
    assert sum(g["passed"] for g in groups.values()) == 1044
    assert sum(g["skipped"] for g in groups.values()) == 12
    assert all(g["failed"] == 0 for g in groups.values())
    write(
        "test_counts.json",
        {
            "source": "full_final_router_contract.junit.xml",
            "groups": groups,
            "total": {"passed": 1044, "skipped": 12, "failed": 0},
        },
    )
    local = read("local_regression_rows.json")
    assert len(local) == 4 and all(r["passed"] for r in local)
    assert sum(r["typed_references"] for r in local) == 20
    assert read("external_attempts_18081.json") == []
    assert read("provider_observations.json")["closed"] is True
    print(
        json.dumps(
            {
                "preserved": len(before) - len(changed),
                "changed": len(changed),
                "index": 507,
                "full_passed": 1044,
                "local_passed": len(local),
            }
        )
    )


if __name__ == "__main__":
    main()
