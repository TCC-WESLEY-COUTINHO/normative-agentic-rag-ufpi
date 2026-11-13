"""Chroma candidate retrieval; structural lookup has no vector distance."""

from collections import Counter
from dataclasses import dataclass

from rag_baseline.models import RetrievedChunk
from rag_baseline.retrieval_policy import NormativeIdentityResolver


@dataclass(frozen=True)
class RetrievalCandidates:
    chunks: list[RetrievedChunk]
    candidate_count: int
    filters: dict
    identity_methods: dict[str, int]


def _eligible(resolver, chunk_id, metadata, norm_id, sector, excluded_sources):
    identity = resolver.resolve(chunk_id, metadata)
    return (
        identity
        if (
            identity.norm_id == norm_id
            and (sector is None or identity.sector == sector)
            and identity.source not in (excluded_sources or [])
        )
        else None
    )


class MetadataExactEngine:
    def __init__(self, collection, resolver: NormativeIdentityResolver):
        self.collection, self.resolver = collection, resolver

    def retrieve(self, norm_id, article, *, top_k, sector=None, excluded_sources=None):
        if top_k < 1:
            raise ValueError("top_k must be positive")
        where = {"article_number": article}
        rows = self.collection.get(where=where, include=["documents", "metadatas"])
        eligible = []
        methods = Counter()
        for chunk_id, metadata, document in zip(
            rows["ids"], rows["metadatas"], rows["documents"], strict=True
        ):
            identity = _eligible(
                self.resolver, chunk_id, metadata, norm_id, sector, excluded_sources
            )
            if identity:
                eligible.append((chunk_id, metadata, document))
                methods[identity.method] += 1
        eligible.sort(key=lambda row: (row[1]["original_index"], row[0]))
        chunks = [
            RetrievedChunk(id=chunk_id, content=document, **metadata, rank=rank, distance=None)
            for rank, (chunk_id, metadata, document) in enumerate(eligible[:top_k], 1)
        ]
        return RetrievalCandidates(
            chunks,
            len(eligible),
            dict(
                where=where,
                norm_id=norm_id,
                sector=sector,
                excluded_sources=list(excluded_sources or []),
            ),
            dict(methods),
        )


class FilteredVectorEngine:
    def __init__(self, service, resolver: NormativeIdentityResolver):
        self.service, self.resolver = service, resolver

    async def retrieve(
        self, question, norm_id, *, sector=None, excluded_sources=None, query_embedding=None
    ):
        collection = self.service.vector_store.collection
        rows = collection.get(include=["metadatas"])
        ids, methods = [], Counter()
        for chunk_id, metadata in zip(rows["ids"], rows["metadatas"], strict=True):
            identity = _eligible(
                self.resolver, chunk_id, metadata, norm_id, sector, excluded_sources
            )
            if identity:
                ids.append(chunk_id)
                methods[identity.method] += 1
        ids.sort()
        filters = dict(
            ids=ids, norm_id=norm_id, sector=sector, excluded_sources=list(excluded_sources or [])
        )
        if not ids:
            return RetrievalCandidates([], 0, filters, {})
        if query_embedding is None:
            query_embedding = (await self.service.openrouter.embed([question]))[0]
        rows = collection.query(
            query_embeddings=[query_embedding],
            ids=ids,
            n_results=min(self.service.top_k, len(ids)),
            include=["documents", "metadatas", "distances"],
        )
        chunks = [
            RetrievedChunk(
                id=chunk_id, content=document, **metadata, rank=rank, distance=float(distance)
            )
            for rank, (chunk_id, document, metadata, distance) in enumerate(
                zip(
                    rows["ids"][0],
                    rows["documents"][0],
                    rows["metadatas"][0],
                    rows["distances"][0],
                    strict=True,
                ),
                1,
            )
        ]
        return RetrievalCandidates(chunks, len(ids), filters, dict(methods))
