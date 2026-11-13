"""Integrity of the frozen A''-J v2 backend sources (stdlib only).

generate: reads the frozen manifest of code/src (raw SHA-256 recorded when v2 was frozen),
          checks that every backend file still has exactly those bytes, and writes a manifest of
          line-ending-normalized hashes (CRLF -> LF), valid on Windows and Linux checkouts.
verify:   used inside the image build; fails if any backend file differs from that manifest or
          if a file exists that the manifest does not list.

Backend = code/src without the interface (streamlit_app.py, client/, chat_ui/, static/), plus the
normative registry and the corpora read at runtime or reindexed by `rag_baseline.index`.
"""

import hashlib
import json
import sys
from pathlib import Path

UI_ONLY = (
    "code/src/streamlit_app.py",
    "code/src/client/",
    "code/src/chat_ui/",
    "code/src/static/",
)
RUNTIME_DATA = (
    "data/normative_registry.json",
    "evaluation/corpora/graduacao_setor_v2.json",
    "evaluation/corpora/pos_graduacao_setor_v2.json",
    "evaluation/corpora/1056_2026_temporal_v1.json",
    "evaluation/corpora/658_2024_temporal_v1.json",
)


def normalized_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def backend_file(rel: str) -> bool:
    return (
        rel.startswith("code/src/")
        and not rel.startswith(UI_ONLY)
        and "__pycache__" not in rel
    )


def generate(root: Path, frozen_manifest: Path, out: Path) -> None:
    entries = {}
    for line in frozen_manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(maxsplit=1)
        rel = rel.lstrip("*")
        if not backend_file(rel):
            continue
        raw = hashlib.sha256((root / rel).read_bytes()).hexdigest()
        if raw != digest:
            sys.exit(f"frozen bytes differ: {rel}")
        entries[rel] = normalized_sha256(root / rel)
    on_disk = {
        p.relative_to(root).as_posix()
        for p in (root / "code/src").rglob("*")
        if p.is_file() and backend_file(p.relative_to(root).as_posix())
    }
    extra = sorted(on_disk - set(entries))
    if extra:
        sys.exit(f"backend files outside the frozen manifest: {extra}")
    for rel in RUNTIME_DATA:
        entries[rel] = normalized_sha256(root / rel)
    payload = {
        "architecture": "A''-J v2",
        "frozen_code_src_manifest_sha256": hashlib.sha256(
            frozen_manifest.read_bytes()
        ).hexdigest(),
        "normalization": "CRLF->LF",
        "files": dict(sorted(entries.items())),
    }
    out.write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"{len(entries)} files written to {out}")


def verify(root: Path, manifest: Path) -> None:
    files = json.loads(manifest.read_text(encoding="utf-8"))["files"]
    bad = [
        rel for rel, digest in files.items() if normalized_sha256(root / rel) != digest
    ]
    present = {
        p.relative_to(root).as_posix()
        for p in (root / "code/src").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    extra = sorted(present - set(files))
    if bad or extra:
        sys.exit(
            f"backend sources differ from the frozen v2 manifest: changed={bad} extra={extra}"
        )
    print(f"frozen v2 backend sources verified: {len(files)} files")


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "generate":
        generate(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
    elif mode == "verify":
        verify(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        sys.exit(
            "usage: frozen_sources.py generate ROOT FROZEN_MANIFEST OUT | verify ROOT MANIFEST"
        )
