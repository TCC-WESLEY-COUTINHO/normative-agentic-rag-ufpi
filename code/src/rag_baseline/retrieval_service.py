"""Per-invocation retrieval injection into the unchanged normative graph."""

import json
from collections import Counter
from dataclasses import asdict, dataclass

from rag_baseline.lexical_retrieval import lexical_candidates
from rag_baseline.models import RetrievedChunk
from rag_baseline.retrieval_engines import FilteredVectorEngine, MetadataExactEngine
from rag_baseline.retrieval_policy import NormativeIdentityResolver, RetrievalStrategySelector
from rag_baseline.service import CorpusNotIndexedError
from rag_baseline.tool_contracts import RetrievalStrategy


@dataclass
class RetrievalExecution:
    strategy: RetrievalStrategy | None = None
    audit: dict | None = None


class RetrievalScopeConflict(ValueError):
    pass


def _candidate_audit(chunks, resolver):
    result = []
    for chunk in chunks:
        identity = resolver.resolve(chunk.id, chunk.model_dump())
        result.append(
            dict(
                id=chunk.id,
                norm_id=identity.norm_id,
                article=identity.article,
                source=identity.source,
                sector=identity.sector,
                rank=chunk.rank,
                distance=chunk.distance,
                identity_method=identity.method,
            )
        )
    return result


MAX_COMPLEMENTARY_CHUNKS = 2


def _as_chunk(candidate_id, document, metadata, rank):
    return RetrievedChunk(id=candidate_id, content=document, **metadata, rank=rank, distance=None)


class StrategyRagService:
    def __init__(self, service, version_filter, execution: RetrievalExecution):
        self._service, self._version_filter, self._execution = service, version_filter, execution

    def __getattr__(self, name):
        return getattr(self._service, name)

    async def retrieve(self, question, *, sector=None, excluded_sources=None, query_embedding=None):
        registry = self._version_filter.registry
        plan = RetrievalStrategySelector(registry).select(question, scope=sector or "ambas")
        resolver = NormativeIdentityResolver(registry)
        audit = dict(
            strategy=plan.strategy.value,
            parsed_reference=json.loads(json.dumps(asdict(plan.reference))),
            consistency=plan.consistency,
            routed_scope=sector or "ambas",
            executed=False,
            filter_applied=None,
            candidate_count=None,
            returned_count=0,
            identity_resolution_method={},
            returned_candidates=[],
        )
        self._execution.audit = audit
        if plan.consistency == "scope_conflict":
            raise RetrievalScopeConflict("Explicit norm conflicts with routed scope")
        self._execution.strategy = plan.strategy
        audit["executed"] = True
        if plan.strategy == RetrievalStrategy.DENSE_VECTOR:
            chunks = await self._service.retrieve(
                question,
                sector=sector,
                excluded_sources=excluded_sources,
                query_embedding=query_embedding,
            )
            chunks = self._with_lexical(
                chunks, question, plan, resolver, sector, excluded_sources, audit
            )
            audit["filter_applied"] = dict(
                sector=sector, excluded_sources=list(excluded_sources or [])
            )
            audit["returned_count"] = len(chunks)
            audit["returned_candidates"] = _candidate_audit(chunks, resolver)
            audit["identity_resolution_method"] = dict(
                Counter(resolver.resolve(c.id, c.model_dump()).method for c in chunks)
            )
            return chunks
        if self._service.vector_store.count() == 0:
            raise CorpusNotIndexedError("Normative corpus is not indexed")
        if plan.strategy == RetrievalStrategy.METADATA_EXACT:
            found = MetadataExactEngine(self._service.vector_store.collection, resolver).retrieve(
                plan.reference.norm_id,
                plan.reference.article,
                top_k=self._service.top_k,
                sector=sector,
                excluded_sources=excluded_sources,
            )
        else:
            found = await FilteredVectorEngine(self._service, resolver).retrieve(
                question,
                plan.reference.norm_id,
                sector=sector,
                excluded_sources=excluded_sources,
                query_embedding=query_embedding,
            )
        chunks = found.chunks
        if plan.strategy == RetrievalStrategy.METADATA_EXACT:
            chunks = self._with_amending_provision(
                chunks, plan, resolver, sector, excluded_sources, audit
            )
        else:
            chunks = self._with_lexical(
                chunks, question, plan, resolver, sector, excluded_sources, audit
            )
        audit.update(
            filter_applied=found.filters,
            candidate_count=found.candidate_count,
            returned_count=len(chunks),
            identity_resolution_method=found.identity_methods,
            returned_candidates=_candidate_audit(chunks, resolver),
        )
        return chunks

    def _with_lexical(self, chunks, question, plan, resolver, sector, excluded_sources, audit):
        """Add indexed articles the dense ranking missed; dense results keep their positions."""
        collection = getattr(getattr(self._service, "vector_store", None), "collection", None)
        if collection is None:
            return chunks
        norms = plan.reference.norm_ids
        present = {chunk.id for chunk in chunks}
        additions = []

        def add(eligible, limit):
            additions.extend(
                lexical_candidates(
                    collection,
                    question,
                    sector=sector,
                    excluded_sources=excluded_sources,
                    exclude_ids=present | {c.id for c in additions},
                    eligible=eligible,
                    limit=limit,
                )
            )

        def of_norm(norm):
            return lambda chunk_id, metadata: resolver.resolve(chunk_id, metadata).norm_id == norm

        try:
            if len(norms) > 1:
                # A question naming several norms needs evidence from each of them.
                for norm in norms:
                    if len(additions) >= MAX_COMPLEMENTARY_CHUNKS:
                        break
                    if not any(
                        resolver.resolve(c.id, c.model_dump()).norm_id == norm for c in chunks
                    ):
                        add(of_norm(norm), 1)
            room = MAX_COMPLEMENTARY_CHUNKS - len(additions)
            if room > 0:
                add(of_norm(norms[0]) if len(norms) == 1 else None, room)
        except Exception as exc:
            # The dense result stands on its own; a failed complement must not discard it.
            audit["lexical_error"] = type(exc).__name__
            return chunks
        audit["lexical_additions"] = [
            dict(id=c.id, score=round(c.score, 3), matched_terms=list(c.matched_terms))
            for c in additions
        ]
        return [
            *chunks,
            *(
                _as_chunk(c.id, c.document, c.metadata, len(chunks) + position)
                for position, c in enumerate(additions, 1)
            ),
        ]

    def _with_amending_provision(self, chunks, plan, resolver, sector, excluded_sources, audit):
        """A provision with a recorded amendment is read together with the amending article."""
        registry = self._version_filter.registry
        record = next((n for n in registry.norms if n.norm_id == plan.reference.norm_id), None)
        if record is None or not chunks:
            return chunks
        collection = self._service.vector_store.collection
        result = list(chunks)
        added = []
        for amendment in record.amendments:
            if amendment.target.article != plan.reference.article:
                continue
            rows = collection.get(
                where={"article_number": str(amendment.legal_basis.article)},
                include=["documents", "metadatas"],
            )
            for chunk_id, document, metadata in zip(
                rows["ids"], rows["documents"], rows["metadatas"], strict=True
            ):
                identity = resolver.resolve(chunk_id, metadata)
                if (
                    identity.norm_id == amendment.amended_by
                    and identity.source not in (excluded_sources or [])
                    and (sector is None or identity.sector == sector)
                    and chunk_id not in {c.id for c in result}
                ):
                    result.append(_as_chunk(chunk_id, document, metadata, len(result) + 1))
                    added.append(chunk_id)
        audit["amending_provisions_added"] = added
        return result
