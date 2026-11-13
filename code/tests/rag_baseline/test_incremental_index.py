import hashlib
import importlib
import json
import struct
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag_baseline.config import BaselineSettings, CorpusSource
from rag_baseline.vector_store import ChromaVectorStore


def test_snapshot_is_sorted_stable_and_hashes_existing_vectors_as_float32(tmp_path) -> None:
    # Losing or changing any stored field must change the snapshot, regardless of insertion order.
    module = importlib.import_module("rag_baseline.incremental_index")
    first = ChromaVectorStore(tmp_path / "chroma", "snapshot_first")
    second = ChromaVectorStore(tmp_path / "chroma", "snapshot_second")
    first.collection.add(
        ids=["b", "a"],
        documents=["Artigo B.", "Artigo A."],
        metadatas=[{"source": "Norma B", "norm_id": "2/2025"}, {"source": "Norma A"}],
        embeddings=[[0.25, 1.0], [1.0, 0.0]],
    )
    second.collection.add(
        ids=["a", "b"],
        documents=["Artigo A.", "Artigo B."],
        metadatas=[{"source": "Norma A"}, {"norm_id": "2/2025", "source": "Norma B"}],
        embeddings=[[1.0, 0.0], [0.25, 1.0]],
    )

    snapshot = module.snapshot_collection(first.collection)

    assert snapshot == module.snapshot_collection(second.collection)
    assert snapshot["count"] == 2
    assert snapshot["ids"] == ["a", "b"]
    assert snapshot["records"][0] == {
        "id": "a",
        "source": "Norma A",
        "norm_id": None,
        "document_sha256": hashlib.sha256(b"Artigo A.").hexdigest(),
        "metadata_json": '{"source":"Norma A"}',
        "metadata_sha256": hashlib.sha256(b'{"source":"Norma A"}').hexdigest(),
        "embedding_float32_sha256": hashlib.sha256(struct.pack("<2f", 1.0, 0.0)).hexdigest(),
        "embedding_dimensions": 2,
    }
    assert snapshot["records"][1]["norm_id"] == "2/2025"
    assert "Artigo A." not in json.dumps(snapshot)
    json.dumps(snapshot, allow_nan=False)
    first.collection.update(ids=["a"], embeddings=[[1.0, 0.5]])
    changed = module.snapshot_collection(first.collection)
    assert changed["sha256"] != snapshot["sha256"]
    assert (
        changed["records"][0]["embedding_float32_sha256"]
        != (snapshot["records"][0]["embedding_float32_sha256"])
    )


def write_corpus(path, articles=("Novo artigo um.", "Novo artigo dois.")) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "conteudo": content,
                    "metadados": {
                        "fonte": "Resolução Nova",
                        "setor": "pos_graduacao",
                        "artigo_numero": str(index + 1),
                        "artigo": f"Art. {index + 1}",
                    },
                }
                for index, content in enumerate(articles)
            ]
        ),
        encoding="utf-8",
    )


def settings_for(path, *, prefix="nova") -> BaselineSettings:
    return BaselineSettings(
        CORPUS_SOURCES=(CorpusSource(path=path, id_prefix=prefix, norm_name="Norma Nova"),),
        CHROMA_COLLECTION="incremental_test",
        CHROMA_PERSIST_DIR=path.parent / "chroma",
        _env_file=None,
    )


class OfflineEmbeddings:
    """Replace only the external API; collection persistence and corpus loading stay real."""

    def __init__(self, *, after_embed=None, vectors=None) -> None:
        self.requests = []
        self.after_embed = after_embed
        self.vectors = vectors

    async def embed(self, texts):
        self.requests.append(list(texts))
        if self.after_embed is not None:
            self.after_embed()
        if self.vectors is not None:
            return self.vectors
        return [[0.25, 1.5] for _ in texts]


def existing_store(tmp_path):
    store = ChromaVectorStore(tmp_path / "chroma", "incremental_test")
    store.collection.add(
        ids=["graduacao-original", "956-original"],
        documents=["Artigo da graduação preservado.", "Artigo da 956 preservado."],
        metadatas=[
            {"source": "Graduação", "sector": "graduacao"},
            {"source": "956/2025", "sector": "pos_graduacao", "norm_id": "956/2025"},
        ],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
    )
    return store


def new_metadata(article="1", index=0):
    return {
        "source": "Resolução Nova",
        "sector": "pos_graduacao",
        "article_number": article,
        "article_label": f"Art. {article}",
        "original_index": index,
    }


@pytest.mark.asyncio
async def test_adds_only_missing_chunks_preserving_every_existing_field(tmp_path) -> None:
    # Embedding every input or synchronizing the store would alter existing rows or spend API calls.
    module = importlib.import_module("rag_baseline.incremental_index")
    path = tmp_path / "new.json"
    write_corpus(path)
    store = existing_store(tmp_path)
    store.collection.add(
        ids=["nova-art-1-idx-000000"],
        documents=["Novo artigo um."],
        metadatas=[new_metadata()],
        embeddings=[[0.75, -0.5]],
    )
    before = module.snapshot_collection(store.collection)
    embeddings = OfflineEmbeddings()

    summary = await module.incremental_index(
        settings_for(path), openrouter=embeddings, vector_store=store
    )

    assert summary.before_snapshot == before
    assert summary.loaded_chunks == 2
    assert summary.added_chunks == 1
    assert summary.skipped_chunks == 1
    assert summary.indexed_chunks == 4
    assert summary.added_ids == ["nova-art-2-idx-000001"]
    assert summary.unchanged_ids == ["956-original", "graduacao-original", "nova-art-1-idx-000000"]
    assert embeddings.requests == [
        ["Setor: pos_graduacao\nNorma: Norma Nova\nArtigo: Art. 2\nConteúdo:\nNovo artigo dois."]
    ]
    after_by_id = {row["id"]: row for row in summary.after_snapshot["records"]}
    assert [after_by_id[row["id"]] for row in before["records"]] == before["records"]
    assert summary.after_snapshot == module.snapshot_collection(store.collection)


@pytest.mark.asyncio
async def test_idempotent_retry_never_requests_new_embeddings(tmp_path) -> None:
    module = importlib.import_module("rag_baseline.incremental_index")
    path = tmp_path / "new.json"
    write_corpus(path)
    store = existing_store(tmp_path)
    await module.incremental_index(
        settings_for(path), openrouter=OfflineEmbeddings(), vector_store=store
    )
    embeddings = OfflineEmbeddings()

    summary = await module.incremental_index(
        settings_for(path), openrouter=embeddings, vector_store=store
    )

    assert summary.added_ids == []
    assert summary.skipped_chunks == 2
    assert summary.before_snapshot == summary.after_snapshot
    assert embeddings.requests == []
    assert store.count() == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["document", "metadata"])
async def test_existing_id_collision_fails_before_embedding_or_any_addition(
    tmp_path, field
) -> None:
    module = importlib.import_module("rag_baseline.incremental_index")
    path = tmp_path / "new.json"
    write_corpus(path)
    store = existing_store(tmp_path)
    metadata = new_metadata("2", 1)
    if field == "metadata":
        metadata["source"] = "Outra norma"
    store.collection.add(
        ids=["nova-art-2-idx-000001"],
        documents=["Outro texto." if field == "document" else "Novo artigo dois."],
        metadatas=[metadata],
        embeddings=[[0.5, 0.5]],
    )
    before = module.snapshot_collection(store.collection)
    embeddings = OfflineEmbeddings()

    with pytest.raises(module.IndexingError, match="colisão"):
        await module.incremental_index(
            settings_for(path), openrouter=embeddings, vector_store=store
        )

    assert embeddings.requests == []
    assert module.snapshot_collection(store.collection) == before


@pytest.mark.asyncio
async def test_duplicate_input_ids_fail_before_embeddings_and_mutation(tmp_path) -> None:
    module = importlib.import_module("rag_baseline.incremental_index")
    path = tmp_path / "new.json"
    write_corpus(path)
    settings = settings_for(path)
    settings = settings.model_copy(update={"CORPUS_SOURCES": settings.CORPUS_SOURCES * 2})
    store = existing_store(tmp_path)
    before = module.snapshot_collection(store.collection)
    embeddings = OfflineEmbeddings()

    with pytest.raises(module.IndexingError, match="repetidos"):
        await module.incremental_index(settings, openrouter=embeddings, vector_store=store)

    assert module.snapshot_collection(store.collection) == before
    assert embeddings.requests == []


@pytest.mark.asyncio
async def test_refuses_implicit_default_corpus(tmp_path) -> None:
    module = importlib.import_module("rag_baseline.incremental_index")
    store = existing_store(tmp_path)
    embeddings = OfflineEmbeddings()
    settings = BaselineSettings(CORPUS_SOURCES=(), _env_file=None)

    with pytest.raises(module.IndexingError, match="CORPUS_SOURCES"):
        await module.incremental_index(settings, openrouter=embeddings, vector_store=store)

    assert store.count() == 2
    assert embeddings.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "vectors",
    [
        [[], []],
        [[1.0], [1.0]],
        [[1.0, 0.0], [1.0, 0.0, 0.5]],
        [[float("nan"), 0.0], [1.0, 0.0]],
        [[float("inf"), 0.0], [1.0, 0.0]],
        [[1e100, 0.0], [1.0, 0.0]],
    ],
)
async def test_invalid_embeddings_fail_before_any_collection_write(tmp_path, vectors) -> None:
    module = importlib.import_module("rag_baseline.incremental_index")
    path = tmp_path / "new.json"
    write_corpus(path)
    store = existing_store(tmp_path)
    before = module.snapshot_collection(store.collection)

    with pytest.raises(module.IndexingError, match="embedding"):
        await module.incremental_index(
            settings_for(path),
            openrouter=OfflineEmbeddings(vectors=vectors),
            vector_store=store,
        )

    assert module.snapshot_collection(store.collection) == before


@pytest.mark.asyncio
async def test_empty_collection_accepts_new_rows_and_produces_empty_before_snapshot(
    tmp_path,
) -> None:
    module = importlib.import_module("rag_baseline.incremental_index")
    path = tmp_path / "new.json"
    write_corpus(path)
    store = ChromaVectorStore(tmp_path / "chroma", "incremental_test")

    summary = await module.incremental_index(
        settings_for(path), openrouter=OfflineEmbeddings(), vector_store=store
    )

    assert summary.before_snapshot["count"] == 0
    assert summary.before_snapshot["records"] == []
    assert summary.before_snapshot["ids"] == []
    assert summary.before_snapshot["sha256"] == hashlib.sha256(b"[]").hexdigest()
    assert summary.added_ids == ["nova-art-1-idx-000000", "nova-art-2-idx-000001"]
    assert summary.indexed_chunks == 2


@pytest.mark.asyncio
async def test_collection_change_during_embedding_cancels_addition(tmp_path) -> None:
    module = importlib.import_module("rag_baseline.incremental_index")
    path = tmp_path / "new.json"
    write_corpus(path)
    store = existing_store(tmp_path)
    embeddings = OfflineEmbeddings(
        after_embed=lambda: store.collection.update(
            ids=["graduacao-original"], embeddings=[[0.25, 0.25]]
        )
    )

    with pytest.raises(module.IndexingError, match="mudou durante"):
        await module.incremental_index(
            settings_for(path), openrouter=embeddings, vector_store=store
        )

    assert set(store.collection.get()["ids"]) == {"graduacao-original", "956-original"}


@pytest.mark.asyncio
async def test_changed_prior_vector_after_addition_is_detected(tmp_path, monkeypatch) -> None:
    module = importlib.import_module("rag_baseline.incremental_index")
    path = tmp_path / "new.json"
    write_corpus(path)
    store = existing_store(tmp_path)
    original_add = type(store.collection).add

    def corrupted_add(collection, **kwargs):
        original_add(collection, **kwargs)
        collection.update(ids=["graduacao-original"], embeddings=[[0.25, 0.25]])

    monkeypatch.setattr(type(store.collection), "add", corrupted_add)

    with pytest.raises(module.IndexingError, match="anteriores foram alterados"):
        await module.incremental_index(
            settings_for(path), openrouter=OfflineEmbeddings(), vector_store=store
        )


@pytest.mark.asyncio
async def test_incomplete_addition_is_detected_by_count_and_ids(tmp_path, monkeypatch) -> None:
    module = importlib.import_module("rag_baseline.incremental_index")
    path = tmp_path / "new.json"
    write_corpus(path)
    store = existing_store(tmp_path)
    original_add = type(store.collection).add

    def incomplete_add(collection, **kwargs):
        original_add(collection, **{key: values[:1] for key, values in kwargs.items()})

    monkeypatch.setattr(type(store.collection), "add", incomplete_add)

    with pytest.raises(module.IndexingError, match="contagem ou os IDs"):
        await module.incremental_index(
            settings_for(path), openrouter=OfflineEmbeddings(), vector_store=store
        )


def test_cli_maps_only_explicit_sources_and_saves_safe_summary_and_receipts(
    tmp_path, monkeypatch, capsys
) -> None:
    module = importlib.import_module("rag_baseline.incremental_index")
    experiment = importlib.import_module("rag_baseline.experiment")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "cli-test-secret-do-not-export")
    monkeypatch.setenv("EMBEDDING_MODEL", "configured/embedding-model")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", "configured/chroma")
    output = tmp_path / "new-evidence"
    receipts = [
        {
            "endpoint": "/embeddings",
            "id": "provider-request-id",
            "model": "configured/embedding-model",
            "usage": {"prompt_tokens": 15, "total_tokens": 15},
        }
    ]
    client = SimpleNamespace(receipts=receipts)
    store = object()
    captured = {}
    snapshot = {"count": 0, "ids": [], "records": [], "sha256": "empty"}
    summary = module.IncrementalIndexSummary(
        loaded_chunks=2,
        added_chunks=2,
        skipped_chunks=0,
        indexed_chunks=2,
        added_ids=["new-1", "new-2"],
        unchanged_ids=[],
        before_snapshot=snapshot,
        after_snapshot=snapshot,
        collection="ufpi_duas_regulacoes_setor",
        embedding_model="configured/embedding-model",
        persist_dir=Path("configured/chroma"),
        elapsed_seconds=0.25,
    )

    def measured_client(settings):
        assert output.is_dir()
        captured["client_settings"] = settings
        return client

    def collection_store(persist_dir, collection_name):
        assert output.is_dir()
        captured["store_configuration"] = (persist_dir, collection_name)
        return store

    async def indexing(settings, *, openrouter, vector_store):
        assert openrouter is client
        assert vector_store is store
        captured["settings"] = settings
        return summary

    monkeypatch.setattr(experiment, "client_for", measured_client)
    monkeypatch.setattr(module, "ChromaVectorStore", collection_store)
    monkeypatch.setattr(module, "incremental_index", indexing)

    exit_code = module.main(
        [
            "--source",
            "new-658.json",
            "ufpi-658-2024",
            "Resolução 658/2024",
            "--source",
            "new-1056.json",
            "ufpi-1056-2026",
            "Resolução 1.056/2026",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    settings = captured["settings"]
    assert settings is captured["client_settings"]
    assert settings.EMBEDDING_MODEL == "configured/embedding-model"
    assert settings.CHROMA_COLLECTION == "ufpi_duas_regulacoes_setor"
    assert [source.model_dump(mode="json") for source in settings.CORPUS_SOURCES] == [
        {"path": "new-658.json", "id_prefix": "ufpi-658-2024", "norm_name": "Resolução 658/2024"},
        {
            "path": "new-1056.json",
            "id_prefix": "ufpi-1056-2026",
            "norm_name": "Resolução 1.056/2026",
        },
    ]
    assert captured["store_configuration"] == (
        Path("configured/chroma"),
        "ufpi_duas_regulacoes_setor",
    )
    assert json.loads((output / "summary.json").read_text(encoding="utf-8")) == json.loads(
        json.dumps(asdict(summary), default=str)
    )
    assert json.loads((output / "receipts.json").read_text(encoding="utf-8")) == receipts
    assert "cli-test-secret-do-not-export" not in "".join(
        path.read_text(encoding="utf-8") for path in output.iterdir()
    )
    assert "cli-test-secret-do-not-export" not in str(capsys.readouterr())


@pytest.mark.parametrize("existing_type", ["directory", "file"])
def test_cli_rejects_existing_output_before_opening_client_or_store(
    tmp_path, monkeypatch, capsys, existing_type
) -> None:
    module = importlib.import_module("rag_baseline.incremental_index")
    experiment = importlib.import_module("rag_baseline.experiment")
    output = tmp_path / "existing-output"
    if existing_type == "directory":
        output.mkdir()
        (output / "preserve.json").write_text("original evidence", encoding="utf-8")
    else:
        output.write_text("original evidence", encoding="utf-8")

    def forbidden_open(*args, **kwargs):
        pytest.fail("Existing output must be rejected before opening the client or collection")

    monkeypatch.setattr(experiment, "client_for", forbidden_open)
    monkeypatch.setattr(module, "ChromaVectorStore", forbidden_open)

    exit_code = module.main(
        [
            "--source",
            "new-658.json",
            "ufpi-658-2024",
            "Resolução 658/2024",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    assert "já existe" in capsys.readouterr().err
    preserved = output / "preserve.json" if existing_type == "directory" else output
    assert preserved.read_text(encoding="utf-8") == "original evidence"
