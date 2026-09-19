from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.errors import NotFoundError

from rag_baseline.models import CorpusChunk, RetrievedChunk


class ChromaVectorStore:
    def __init__(self, persist_dir: str | Path, collection_name: str) -> None:
        self.persist_dir = Path(persist_dir)
        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self._get_or_create_collection()

    def _get_or_create_collection(self):
        return self.client.get_or_create_collection(
            name=self.collection_name,
            configuration={"hnsw": {"space": "cosine"}},
            embedding_function=None,
        )

    @staticmethod
    def _metadata(chunk: CorpusChunk) -> dict[str, str | int]:
        values: dict[str, Any] = chunk.model_dump(exclude_none=True)
        values.pop("id")
        values.pop("content")
        return values

    def upsert(self, chunks: list[CorpusChunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Cada chunk deve possuir exatamente um embedding.")
        if not chunks:
            return
        self.collection.upsert(
            ids=[chunk.id for chunk in chunks],
            documents=[chunk.content for chunk in chunks],
            metadatas=[self._metadata(chunk) for chunk in chunks],
            embeddings=embeddings,
        )

    def count(self) -> int:
        return self.collection.count()

    def reset(self) -> None:
        try:
            self.client.delete_collection(self.collection_name)
        except NotFoundError:
            pass
        self.collection = self._get_or_create_collection()

    def query(self, embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        if self.count() == 0:
            return []
        result = self.collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, self.count()),
            include=["documents", "metadatas", "distances"],
        )
        ids = result["ids"][0]
        documents = result["documents"][0] if result["documents"] else []
        metadatas = result["metadatas"][0] if result["metadatas"] else []
        distances = result["distances"][0] if result["distances"] else []

        retrieved: list[RetrievedChunk] = []
        for rank, (chunk_id, content, metadata, distance) in enumerate(
            zip(ids, documents, metadatas, distances, strict=True),
            start=1,
        ):
            retrieved.append(
                RetrievedChunk(
                    id=chunk_id,
                    content=content,
                    distance=float(distance),
                    rank=rank,
                    **metadata,
                )
            )
        return retrieved
