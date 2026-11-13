"""Explicit scientific runner for temporal invariants; normal pytest never calls providers.

Run from code/: python -m rag_baseline.temporal_evaluation --output <new-directory>
Add --live for the fixed, small provider smoke subset. Existing results are never replaced.
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from rag_baseline.agentic import AgenticRagService, classify_temporal_intent
from rag_baseline.config import BaselineSettings
from rag_baseline.corpus import load_corpus
from rag_baseline.experiment import CODE, ROOT, client_for
from rag_baseline.profiles import apply_profile
from rag_baseline.prompts import V2_SYSTEM_PROMPT
from rag_baseline.router import NormativeRouter
from rag_baseline.service import RagService
from rag_baseline.versioning import NormativeRegistry, VersionFilter

DATASET = ROOT / "evaluation/datasets/temporal_invariants_v1.json"


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


class ControlledClient:
    llm_model = "controlled_mock"

    def __init__(self, scope):
        self.scope = scope
        self.generation_calls = 0

    async def structured_chat(self, **kwargs):
        return json.dumps(
            dict(
                scope=self.scope,
                needs_clarification=self.scope is None,
                clarification_question="Qual nível?" if self.scope is None else None,
                reason_code={
                    None: "ambiguous_academic_level",
                    "graduacao": "explicit_graduacao",
                    "pos_graduacao": "explicit_pos",
                    "ambas": "cross_norm_comparison",
                }[self.scope],
            )
        )

    async def embed(self, texts):
        return [[1.0, 0.0]]

    async def chat(self, **kwargs):
        self.generation_calls += 1
        return "Resposta simulada; avaliação determinística restrita ao contexto e ao fluxo."


class ControlledStore:
    def __init__(self, chunks, *, bypass_prefilter=False):
        self.chunks = chunks
        self.bypass_prefilter = bypass_prefilter

    def count(self):
        return len(self.chunks) or 1

    def query(self, embedding, top_k, *, sector=None, excluded_sources=None):
        return [
            c
            for c in self.chunks
            if (sector is None or c.sector == sector)
            and (self.bypass_prefilter or c.source not in (excluded_sources or []))
        ][:top_k]


class RecordingStore:
    def __init__(self, store):
        self.store = store
        self.candidates = []

    def count(self):
        return self.store.count()

    def query(self, *args, **kwargs):
        self.candidates = self.store.query(*args, **kwargs)
        return self.candidates


def norm_id(chunk):
    return chunk["id"].split("-art-")[0]


def obsolete_chunk(chunk, registry):
    record = next((n for n in registry.norms if n.norm_id == norm_id(chunk)), None)
    return record is not None and record.status in ("revogada", "substituida")


def outdated_provision(chunk, registry):
    record = next((n for n in registry.norms if n.norm_id == norm_id(chunk)), None)
    return bool(
        record
        and any(
            chunk["article_number"] == a.target.article and a.previous_text in chunk["content"]
            for a in record.amendments
        )
    )


def reference_key(reference):
    return reference["source"], reference["article_number"], reference["content"]


def inspect_case(item, result, registry, *, live=False):
    audit = result.version_filter or {}
    final = audit.get("final_references", [])
    intent = classify_temporal_intent(item["question"], registry=registry)
    current = intent.mode not in ("historical", "comparison")
    refs = [r.model_dump() for r in result.references]
    action = (
        "clarify"
        if result.needs_clarification
        else "abstain"
        if result.generation_attempts == 0
        else "answer"
    )
    allowed = set(item["expected_norms_allowed"])
    blocked = set(item["expected_norms_blocked"])
    required = set(item["required_norms"])
    observed = {norm_id(c) for c in final}
    obsolete = sum(obsolete_chunk(c, registry) for c in final) if current else 0
    outdated = sum(outdated_provision(c, registry) for c in final) if current else 0
    historical_blocked = set(VersionFilter(registry).historical_exclusions(intent))
    eligible_final = [
        c
        for c in final
        if (
            not current or (not obsolete_chunk(c, registry) and not outdated_provision(c, registry))
        )
        and norm_id(c) not in historical_blocked
    ]
    eligible_n = len(eligible_final)
    eligible_keys = {reference_key(c) for c in eligible_final}
    eligible_refs = sum(reference_key(r) in eligible_keys for r in refs)
    amendment = item["expected_amendment_action"]
    candidate_target = any(
        norm_id(c) == norm.norm_id and c["article_number"] == a.target.article
        for c in audit.get("pre_filter_references", [])
        for norm in registry.norms
        for a in norm.amendments
    )
    if amendment == "applied":
        amendment_ok = bool(audit.get("amended_references")) and not outdated
    elif amendment == "unresolved":
        amendment_ok = (
            any(r["reason"] == "amendment_unresolved" for r in audit.get("removed_references", []))
            and action == "abstain"
        )
    elif amendment == "historical_preserved":
        amendment_ok = not audit.get("amended_references") and any(
            outdated_provision(c, registry) for c in final
        )
    else:
        amendment_ok = not audit.get("amended_references")
    failures = []
    if result.error:
        failures.append("PROVIDER")
    if result.selected_scope != item["domain"] or (
        result.needs_clarification != (item["expected_answer_action"] == "clarify")
    ):
        failures.append("ROUTER")
    if intent.mode != item["temporal_intent"]:
        failures.append("TEMPORAL_INTENT")
    if obsolete or (blocked & observed):
        failures.append("VERSION_FILTER")
    if not amendment_ok and not result.needs_clarification and not result.error:
        failures.append("RETRIEVAL" if live and not candidate_target else "AMENDMENT_APPLICATION")
    if required - observed and not result.needs_clarification and not result.error:
        failures.append("RETRIEVAL" if live else "CONTEXT_ASSEMBLY")
    if (
        intent.article
        and not intent.relation_query
        and item["expected_answer_action"] == "answer"
        and not result.needs_clarification
        and not result.error
        and not any(c["article_number"] == intent.article and norm_id(c) in allowed for c in final)
    ):
        failures.append("RETRIEVAL" if live else "CONTEXT_ASSEMBLY")
    if eligible_refs != len(refs):
        failures.append("REFERENCE")
    return dict(
        id=item["id"],
        question=item["question"],
        domain=item["domain"],
        evaluation_mode="live_provider" if live else "controlled_mock",
        expected=item,
        temporal_classification=intent.model_dump(),
        router_decision=result.route,
        selected_scope=result.selected_scope,
        filter_decisions=audit,
        final_context=final,
        references=refs,
        answer=result.answer,
        observed_answer_action=action,
        generation_attempts=result.generation_attempts,
        error=result.error,
        norms_outside_expected=sorted(observed - allowed),
        failure_layers=sorted(set(failures)),
        generation_semantic_review="required" if live and action == "answer" else "not_evaluated",
        measurements=dict(
            classification_correct=intent.mode == item["temporal_intent"],
            known_current_relation=current and item["known_relation"],
            current=current,
            final_n=len(final),
            obsolete_n=obsolete,
            outdated_n=outdated,
            final_eligible_n=eligible_n,
            reference_n=len(refs),
            reference_eligible_n=eligible_refs,
            historical_applicable=intent.needs_history and bool(required),
            historical_preserved=bool(required) and required <= observed,
            required_evidence_applicable=bool(required) and current,
            required_evidence_hit=bool(required) and required <= observed,
            amendment_applicable=amendment != "none" and candidate_target,
            amendment_correct=amendment_ok,
            isolation_applicable=amendment == "applied" and candidate_target,
            isolation_correct=bool(audit.get("amended_references"))
            and all(
                a["final_reference"]["content"].endswith(
                    a["original_reference"]["content"].replace(
                        a["amendment"]["previous_text"], a["amendment"]["effective_text"], 1
                    )
                )
                for a in audit.get("amended_references", [])
            ),
            insufficient_applicable=item["expected_answer_action"] == "abstain",
            abstained=action == "abstain",
            answer_action_correct=action == item["expected_answer_action"],
        ),
    )


def summarize(rows):
    def ratio(numerator, denominator):
        return dict(
            numerator=numerator,
            denominator=denominator,
            value=numerator / denominator if denominator else None,
        )

    measures = [r["measurements"] for r in rows]
    known = [m for m in measures if m["known_current_relation"]]
    historical = [m for m in measures if m["historical_applicable"]]
    current = [m for m in measures if m["required_evidence_applicable"]]
    amendments = [m for m in measures if m["amendment_applicable"]]
    isolation = [m for m in measures if m["isolation_applicable"]]
    insufficient = [m for m in measures if m["insufficient_applicable"]]
    return dict(
        n=len(rows),
        legal_gold=False,
        generation_semantics_automatically_scored=False,
        metrics=dict(
            temporal_classification_accuracy=ratio(
                sum(m["classification_correct"] for m in measures), len(rows)
            ),
            obsolete_context_exposure_rate=ratio(
                sum(m["obsolete_n"] for m in known), sum(m["final_n"] for m in known)
            ),
            current_norm_hit_rate=ratio(
                sum(m["required_evidence_hit"] for m in current), len(current)
            ),
            compliance_violation_rate=ratio(
                sum(bool(m["obsolete_n"] or m["outdated_n"]) for m in known), len(known)
            ),
            historical_preservation_rate=ratio(
                sum(m["historical_preserved"] for m in historical), len(historical)
            ),
            amendment_application_accuracy=ratio(
                sum(m["amendment_correct"] for m in amendments), len(amendments)
            ),
            amendment_isolation_accuracy=ratio(
                sum(m["isolation_correct"] for m in isolation), len(isolation)
            ),
            final_context_eligibility_rate=ratio(
                sum(m["final_eligible_n"] for m in measures), sum(m["final_n"] for m in measures)
            ),
            reference_eligibility_rate=ratio(
                sum(m["reference_eligible_n"] for m in measures),
                sum(m["reference_n"] for m in measures),
            ),
            insufficient_evidence_abstention_rate=ratio(
                sum(m["abstained"] for m in insufficient), len(insufficient)
            ),
            expected_answer_action_accuracy=ratio(
                sum(m["answer_action_correct"] for m in measures), len(rows)
            ),
        ),
        failures_by_layer={
            layer: sum(layer in r["failure_layers"] for r in rows)
            for layer in sorted({v for r in rows for v in r["failure_layers"]})
        },
    )


async def run(output, *, live=False, manual=False):
    from rag_baseline.models import RetrievedChunk
    from rag_baseline.vector_store import ChromaVectorStore

    output.mkdir(parents=True, exist_ok=True)
    if any((output / name).exists() for name in ("manifest.json", "cases.jsonl", "summary.json")):
        raise ValueError("Resultados já existem; use destino novo.")
    registry = NormativeRegistry.load()
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    items = [q for q in dataset["items"] if not live or q["live_smoke"]]
    settings = apply_profile(BaselineSettings(_env_file=CODE / ".env"), "duas-regulacoes")
    if settings.RETRIEVAL_TOP_K != 5 or settings.LLM_TEMPERATURE != 0:
        raise ValueError("Configuração difere do snapshot: top_k=5, temperatura=0.")
    corpora = {
        s.id_prefix: load_corpus((CODE / s.path).resolve(), id_prefix=s.id_prefix)
        for s in settings.CORPUS_SOURCES
    }
    remote = client_for(settings) if live else None
    real_store = (
        ChromaVectorStore(CODE / settings.CHROMA_PERSIST_DIR, settings.CHROMA_COLLECTION)
        if live
        else None
    )
    rows = []
    with (output / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for item in items:
            client = remote if live else ControlledClient(item["domain"])
            candidates = []
            for rank, source in enumerate(item["candidates"], 1):
                original = next(
                    c for c in corpora[source["norm_id"]] if c.article_number == source["article"]
                )
                chunk = RetrievedChunk(**original.model_dump(), rank=rank, distance=0.1)
                if item["broken_amendment"] and chunk.article_number == "68":
                    chunk = chunk.model_copy(update={"content": "Art. 68. Conversão incompleta."})
                candidates.append(chunk)
            store = RecordingStore(
                real_store
                if live
                else ControlledStore(
                    candidates, bypass_prefilter=item.get("bypass_prefilter", False)
                )
            )
            service = RagService(
                openrouter=client,
                vector_store=store,
                top_k=settings.RETRIEVAL_TOP_K,
                embedding_model=settings.EMBEDDING_MODEL,
                llm_model=settings.LLM_MODEL if live else "controlled_mock",
                system_prompt=V2_SYSTEM_PROMPT,
            )
            result = await AgenticRagService(
                service,
                NormativeRouter(client, model=settings.ROUTER_MODEL),
                VersionFilter(registry),
            ).query(item["question"], scope=item["domain"] if manual else item["manual_scope"])
            row = inspect_case(item, result, registry, live=live)
            row["scope_condition"] = "manual_known_domain" if manual else "dataset_scope"
            row["retrieval_candidates"] = [c.model_dump() for c in store.candidates]
            row["controlled_input_candidates"] = (
                None if live else [c.model_dump() for c in candidates]
            )
            rows.append(row)
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            print(
                json.dumps(
                    dict(
                        id=item["id"],
                        action=row["observed_answer_action"],
                        failures=row["failure_layers"],
                    )
                ),
                flush=True,
            )
    write_json(output / "summary.json", summarize(rows))
    pairs = []
    for pair in sorted({q["pair"] for q in items if q["pair"]}):
        members = [r for r in rows if r["expected"]["pair"] == pair]
        if len(members) == 2:
            signatures = [[reference_key(c) for c in r["final_context"]] for r in members]
            pairs.append(
                dict(
                    pair=pair,
                    case_ids=[r["id"] for r in members],
                    different_final_context=signatures[0] != signatures[1],
                    final_ids=[[c["id"] for c in r["final_context"]] for r in members],
                )
            )
    write_json(output / "comparison.json", dict(pairs=pairs))
    source_paths = [
        DATASET,
        ROOT / "data/normative_registry.json",
        Path(__file__),
        *[
            CODE / "src/rag_baseline" / name
            for name in ("agentic.py", "versioning.py", "router.py", "prompts.py", "config.py")
        ],
    ]
    write_json(
        output / "manifest.json",
        dict(
            schema_version="1.0",
            created_at=datetime.now(UTC).isoformat(),
            mode="live_provider" if live else "controlled_mock",
            scope_condition="manual_known_domain" if manual else "dataset_scope",
            n=len(rows),
            git_head=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            routing_mode="intent_v1",
            top_k=settings.RETRIEVAL_TOP_K,
            temperature=settings.LLM_TEMPERATURE,
            embedding_model=settings.EMBEDDING_MODEL,
            llm_model=settings.LLM_MODEL,
            source_hashes={
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in source_paths
            },
            provider_receipts=remote.receipts if live else [],
            limitations=[
                "Technical regression, not legally validated gold.",
                "Controlled routing and generation are mocked; semantic answer accuracy is not measured.",
                "Unknown status does not certify applicability on a calendar date.",
                "No retrieval tuning or general legal-validity claims.",
            ],
        ),
    )


def reanalyze(source, output):
    """Recompute technical metrics from preserved traces without another provider request."""
    from rag_baseline.models import QueryResult

    output.mkdir(parents=True, exist_ok=False)
    registry = NormativeRegistry.load()
    rows = []
    for line in (source / "cases.jsonl").read_text(encoding="utf-8").splitlines():
        original = json.loads(line)
        result = QueryResult(
            answer=original["answer"],
            references=original["references"],
            llm_model="preserved_trace",
            embedding_model="preserved_trace",
            route=original["router_decision"],
            selected_scope=original["selected_scope"],
            needs_clarification=original["observed_answer_action"] == "clarify",
            version_filter=original["filter_decisions"],
            error=original["error"],
            generation_attempts=original["generation_attempts"],
        )
        row = inspect_case(
            original["expected"],
            result,
            registry,
            live=original["evaluation_mode"] == "live_provider",
        )
        row.update(
            original_failure_layers=original["failure_layers"],
            retrieval_candidates=original.get("retrieval_candidates", []),
            scope_condition=original.get("scope_condition", "dataset_scope"),
        )
        rows.append(row)
    with (output / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_json(output / "summary.json", summarize(rows))
    write_json(
        output / "manifest.json",
        dict(
            mode="offline_reanalysis",
            source=str(source.relative_to(ROOT)),
            source_cases_sha256=hashlib.sha256((source / "cases.jsonl").read_bytes()).hexdigest(),
            evaluator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            provider_calls=0,
            n=len(rows),
            interpretation="Attribution/denominator correction only; answers and contexts unchanged.",
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--manual-smoke", action="store_true")
    parser.add_argument("--reanalyze", type=Path)
    args = parser.parse_args()
    if args.reanalyze:
        reanalyze(args.reanalyze.resolve(), args.output.resolve())
    else:
        if args.manual_smoke and not args.live:
            parser.error("--manual-smoke exige --live")
        asyncio.run(run(args.output.resolve(), live=args.live, manual=args.manual_smoke))


if __name__ == "__main__":
    main()
