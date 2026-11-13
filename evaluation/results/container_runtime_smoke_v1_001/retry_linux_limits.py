"""Diagnose the default descriptor ceiling and retry only the two affected test runs."""

import json
import linux_verification as verification
from operations import IMAGE, OUT, decision, run, write

result = run(
    "linux_descriptor_limit_default",
    [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        IMAGE,
        "python",
        "-c",
        "import json,resource; print(json.dumps(dict(nofile=resource.getrlimit(resource.RLIMIT_NOFILE))))",
    ],
    check=True,
)
limits = json.loads(result.stdout)
write(
    "linux_descriptor_limits.json",
    {
        "default": limits,
        "test_override": [65536, 65536],
        "scope": "Only transient regression test containers; no daemon, production Compose, image or application change.",
    },
)
print(result.stdout, flush=True)
original = verification.run


def bounded_test(name, args, **kwargs):
    assert args[:2] == ["docker", "run"]
    return original(
        name, args[:2] + ["--ulimit", "nofile=65536:65536"] + args[2:], **kwargs
    )


verification.run = bounded_test
decision(
    "regression_descriptor_limit",
    "Set nofile=65536 only on the two transient regression containers affected by FD exhaustion.",
    "Default measured in linux_descriptor_limits.json; original failures preserved. No product/daemon setting changed and no scientific behavior tuned.",
)
results = json.loads((OUT / "linux_suite_exit_codes.json").read_text())
for name, selection in [("rag_baseline", ["tests/rag_baseline"]), ("full", ["tests"])]:
    results[name] = verification.test("linux_tests_" + name, selection)
write("linux_suite_exit_codes.json", results)
raise SystemExit(int(any(results.values())))
