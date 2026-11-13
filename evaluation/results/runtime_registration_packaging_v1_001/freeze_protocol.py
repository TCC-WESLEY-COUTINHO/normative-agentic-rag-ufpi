"""Freeze the declared local integration experiment before its single full run."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCES = [
    "code/src/rag_baseline/integrated_runtime.py",
    "code/src/agents/agents.py",
    "code/src/schema/schema.py",
    "code/src/service/service.py",
    "code/tests/rag_baseline/test_integrated_runtime.py",
    "code/tests/rag_baseline/test_runtime_packaging.py",
    "code/tests/rag_baseline/test_typed_normative_transport.py",
    "code/docker/Dockerfile.service",
    "code/docker/Dockerfile.app",
    "code/compose.yaml",
    "code/compose.prod.yaml",
    "code/.env.example",
    "code/.dockerignore",
    ".dockerignore",
    "code/docs/integrated-runtime.md",
    "evaluation/results/runtime_registration_packaging_v1_001/local_probes.py",
    "evaluation/results/runtime_registration_packaging_v1_001/runtime_audit.json",
    "evaluation/results/runtime_registration_packaging_v1_001/packaging_audit.json",
]


if __name__ == "__main__":
    groups = [
        "runtime_startup",
        "info",
        "health",
        "direct_invoke",
        "calculator_invoke",
        "normative_invoke",
        "normative_stream",
        "clarification_multiturn",
        "grounded_followup",
        "domain_switch",
        "cross_user_isolation",
        "missing_index",
        "invalid_registry",
        "missing_provider_config",
        "shutdown_close",
    ]
    protocol = dict(
        version="1",
        frozen_at=datetime.now(UTC).isoformat(),
        kind="finite_local_engineering_protocol",
        groups=groups,
        external_io="Socket/HTTP forbidden except exact in-process ASGI transport; controlled core provider",
        expected=dict(
            valid_builds=2,
            configured_failure_rejections=3,
            startup_external_calls=0,
            application_savers=5,
            provider_resources=2,
            owned_chroma_resources=2,
            packaging_declarations=11,
            default_agent="chatbot_ufpi_v2",
            legacy_ids=4,
            agent_id="chatbot_ufpi_integrated_v1",
            default_changed=False,
            docker_build="not_run: docker_cli_not_found",
            container_smoke="not_run: docker_cli_not_found",
        ),
        hash_policy="No source/harness/expectation changes after freeze; journal each observation immediately",
        hashes={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES},
    )
    with (OUT / "technical_protocol.json").open("xb") as target:
        target.write((json.dumps(protocol, ensure_ascii=False, indent=2) + "\n").encode())
    print("Frozen", len(groups), "groups and", len(SOURCES), "hashes")
