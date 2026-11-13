"""Freeze source and finite expectations before the single full probe run."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCES = [
    "code/src/rag_baseline/calculator.py",
    "code/src/rag_baseline/calculator_contracts.py",
    "code/src/rag_baseline/conversation_policy.py",
    "code/src/rag_baseline/conversation_graph.py",
    "code/src/schema/schema.py",
    "code/src/service/normative_transport.py",
    "code/tests/rag_baseline/test_calculator_tool_routing.py",
    "code/tests/rag_baseline/test_calculator_transport.py",
    "evaluation/datasets/tool_routing_calculator_v1.json",
    "evaluation/results/calculator_tool_routing_v1_001/local_probes.py",
]


if __name__ == "__main__":
    value = dict(
        version="1",
        frozen_at=datetime.now(UTC).isoformat(),
        kind="finite_engineering_protocol_no_legal_gold",
        external_io="Blocked socket connections and HTTP sends; exact in-process ASGI exception only",
        groups=[
            "arithmetic_addition",
            "arithmetic_division",
            "invalid_expression",
            "division_by_zero",
            "date_offset",
            "date_difference",
            "ambiguous_a_partir_de",
            "business_days_unsupported",
            "normative_mixed_question",
            "pending_calculator_and_continuation",
            "normative_answer_calculator_grounded_transform",
            "typed_invoke",
            "typed_stream",
            "concurrent_calculator_metadata_exact_and_date",
        ],
        expectations=dict(
            technical_cases=60,
            normative_false_routes=0,
            supported_calculator_false_routes=0,
            external_calls=0,
            memory_and_pending="Exact equality of stored model including persistence envelope/stamp",
            stream="One complete message and DONE, stream_tokens=True",
            concurrency="Distinct namespaces, calculator results, normative correlation and memory",
        ),
        hashes={path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in SOURCES},
    )
    with (OUT / "technical_protocol.json").open("xb") as target:
        target.write((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())
    print("Frozen", len(SOURCES), "hashes and", len(value["groups"]), "groups")
