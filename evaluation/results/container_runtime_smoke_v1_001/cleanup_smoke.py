"""Remove only resources created by this operational validation."""

import json
import shutil
from pathlib import Path
from operations import OUT, decision, journal, run, write

base = Path(json.loads((OUT / "temporary_workspace.json").read_text())["path"])
resolved = base.resolve()
assert (
    resolved.parent == Path("/var/tmp")
    and resolved.name.startswith("normative-runtime-smoke-")
    and not base.is_symlink()
)
assert (base / "test-context/Dockerfile").is_file()
context = OUT / "test_tooling"
context.mkdir()
for name in ("Dockerfile", "legacy_app_cwd.py"):
    shutil.copyfile(base / "test-context" / name, context / name)
helper = "normative-agentic-rag-ufpi:runtime-smoke-test-tools"
run(
    "test_tool_git_version",
    ["docker", "run", "--rm", "--network", "none", helper, "git", "--version"],
    check=True,
)
run(
    "test_tools_image_metadata",
    ["docker", "image", "inspect", "--format", "{{json .Id}}", helper],
    check=True,
)
run("test_tools_image_remove", ["docker", "image", "rm", helper], check=True)
shutil.rmtree(resolved)
probe = Path("/tmp/normative-runtime-smoke-probe")
if probe.is_dir() and not probe.is_symlink():
    assert sorted(p.name for p in probe.iterdir()) == ["marker"]
    (probe / "marker").unlink()
    probe.rmdir()
run("docker_final_containers_all", ["docker", "ps", "-a", "--format", "{{.Names}}"])
run(
    "docker_primary_image_retained",
    [
        "docker",
        "image",
        "inspect",
        "--format",
        "{{json .Id}}",
        "normative-agentic-rag-ufpi:runtime-smoke",
    ],
    check=True,
)
write(
    "cleanup.json",
    {
        "temporary_workspace": str(resolved),
        "workspace_removed": not resolved.exists(),
        "auxiliary_test_tools_image_removed": True,
        "primary_runtime_image_retained": True,
        "smoke_containers_networks_removed": True,
        "user_containers_or_images_pruned": False,
        "sqlite_temporary_data_removed_after_evidence_capture": True,
        "host_index_untouched_by_cleanup": True,
    },
)
decision(
    "temporary_cleanup_complete",
    "Remove only the recorded /var/tmp workspace, owned marker directory and auxiliary test-tools image; retain primary build image and evidence.",
    "All verification has finished; SQLite/observations captured, no user data or existing hello-world image removed. No Docker/global filesystem prune.",
)
journal(
    "cleanup_complete", temporary_workspace_removed=True, primary_image_retained=True
)
