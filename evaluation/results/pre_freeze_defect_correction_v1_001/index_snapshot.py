"""Existing canonical logical snapshot, without creating a missing collection."""

import json
import sys
from pathlib import Path
import chromadb
from chromadb.config import Settings
from rag_baseline.incremental_index import snapshot_collection

out = Path(__file__).resolve().parent
root = out.parents[2]
path = root / "code/.local/chroma"
assert (path / "chroma.sqlite3").is_file()
client = chromadb.PersistentClient(
    path=str(path), settings=Settings(anonymized_telemetry=False)
)
try:
    collection = client.get_collection(
        "ufpi_duas_regulacoes_setor", embedding_function=None
    )
    snapshot = snapshot_collection(collection)
    assert snapshot["count"] == 507
    (out / f"index_{sys.argv[1]}.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if len(sys.argv) > 2:
        sample = collection.get(limit=1, include=["embeddings"])["embeddings"][
            0
        ].tolist()
        Path(sys.argv[2]).write_text(json.dumps(sample), encoding="utf-8")
    print(json.dumps({k: snapshot[k] for k in ("count", "sha256")}))
finally:
    client._system.stop()
