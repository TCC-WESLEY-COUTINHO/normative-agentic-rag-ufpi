"""Read-only recovery of Case B checkpoints; unrelated conversation text is not exported."""

import json
import sqlite3
import sys
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from core.settings import settings

db = Path(settings.SQLITE_DB_PATH).resolve()
connection = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
rows = connection.execute(
    "SELECT thread_id, checkpoint_id, type, checkpoint FROM checkpoints "
    "WHERE instr(checkpoint, CAST(? AS BLOB)) > 0 ORDER BY checkpoint_id DESC LIMIT 120",
    ("coordenador",),
).fetchall()
serializer = JsonPlusSerializer()
found, seen = [], set()
for thread, checkpoint, kind, blob in rows:
    state = serializer.loads_typed((kind, blob)).get("channel_values", {})
    question = state.get("current_question", "")
    if "coordenador" not in question.lower() or "estágio" not in question.lower():
        continue
    result = state.get("normative_result")
    if not result:
        continue
    correlation = str(result.correlation_id)
    if correlation in seen:
        continue
    seen.add(correlation)
    memory = state.get("conversation_memory")
    restored = memory.restore_result() if memory else None
    private_audit = (
        restored.internal_audit
        if restored and str(restored.correlation_id) == correlation
        else None
    )
    found.append(
        dict(
            thread_id=thread,
            checkpoint_id=checkpoint,
            question=question,
            correlation_id=correlation,
            status=result.status,
            core_status=result.core_status,
            internal_generation_audit_available=bool(result.internal_audit),
            matching_private_envelope_audit=private_audit.model_dump(mode="json")
            if private_audit
            else None,
            result=result.model_dump(mode="json"),
        )
    )
connection.close()
Path(sys.argv[1]).write_text(
    json.dumps(dict(read_only=True, relevant_cases=found), ensure_ascii=False, indent=2) + "\n",
    "utf-8",
)
print(json.dumps([dict(question=r["question"], core_status=r["core_status"]) for r in found]))
