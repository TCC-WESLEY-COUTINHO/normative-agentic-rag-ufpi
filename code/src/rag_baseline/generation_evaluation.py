"""Fixed-context temporal-generation experiment; external calls require explicit stages."""

import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path

from rag_baseline.agentic import AgenticRagService
from rag_baseline.config import BaselineSettings
from rag_baseline.experiment import CODE, ROOT, client_for
from rag_baseline.models import RetrievedChunk
from rag_baseline.prompts import V2_SYSTEM_PROMPT
from rag_baseline.router import NormativeRouter
from rag_baseline.service import RagService
from rag_baseline.versioning import NormativeRegistry, VersionAudit, VersionFilter

DATASET = ROOT / "evaluation/datasets/temporal_generation_grounding_v1.json"
PREVIOUS = ROOT / "evaluation/results/agentic_temporal_hardening_v1_001"


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


class FixedStore:
    def __init__(self, chunks):
        self.chunks = chunks

    def count(self):
        return len(self.chunks)

    def query(self, *args, **kwargs):
        return self.chunks


class CaptureClient:
    def __init__(self, delegate=None):
        self.delegate = delegate
        self.prompt = None
        self.prompts = []
        self.llm_model = delegate.llm_model if delegate else "capture"

    async def embed(self, texts):
        return [[0.0]]

    async def chat(self, **payload):
        self.prompt = payload
        self.prompts.append(payload)
        return await self.delegate.chat(**payload) if self.delegate else "capture"


class CaptureService(RagService):
    async def generate(self, *args, **kwargs):
        self.context_notice = kwargs.get("context_notice")
        return await super().generate(*args, **kwargs)


def settings_for():
    settings = BaselineSettings(_env_file=CODE / ".env")
    if settings.LLM_TEMPERATURE != 0 or settings.RETRIEVAL_TOP_K != 5:
        raise ValueError("O protocolo preserva temperatura 0 e top-k 5.")
    return settings


async def prepare(output):
    if output.exists() or DATASET.exists():
        raise ValueError("Preparação exige destinos novos.")
    output.mkdir(parents=True)
    settings = settings_for()
    sources = {}
    for folder in ("smoke_manual_001", "controlled_001"):
        sources[folder] = {
            r["id"]: r
            for r in (
                json.loads(line)
                for line in (PREVIOUS / folder / "cases.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            )
        }
    definitions = [
        ("A_grad_historical", "smoke_manual_001", "G3_historical", 10, None),
        ("B_grad_current", "smoke_manual_001", "G1_current", 1, None),
        ("C_post_historical", "smoke_manual_001", "P2_historical", 10, None),
        ("D_post_current", "smoke_manual_001", "P1_current", 1, None),
        ("E_validity", "smoke_manual_001", "P3_validity", 10, None),
        ("F_comparison", "controlled_001", "P4_comparison", 1, None),
        (
            "G_unknown",
            "controlled_001",
            "U1_unknown",
            1,
            "A Resolução 956/2025 ainda está vigente na pós-graduação?",
        ),
        (
            "H_citation",
            "smoke_manual_001",
            "P1_current",
            10,
            "Na pós-graduação da UFPI, com qual antecedência mínima a defesa de dissertação ou tese deve ser divulgada atualmente?",
        ),
    ]
    registry = NormativeRegistry.load()
    items, frozen = [], []
    for case_id, folder, original_id, repetitions, question in definitions:
        original = sources[folder][original_id]
        item = dict(
            id=case_id,
            question=question or original["question"],
            scope=original["domain"],
            repetitions=repetitions,
            source_trace=str((PREVIOUS / folder / "cases.jsonl").relative_to(ROOT)),
            source_case=original_id,
        )
        candidates = [RetrievedChunk.model_validate(c) for c in original["retrieval_candidates"]]
        remote = CaptureClient()
        service = CaptureService(
            openrouter=remote,
            vector_store=FixedStore(candidates),
            top_k=5,
            embedding_model=settings.EMBEDDING_MODEL,
            llm_model=settings.LLM_MODEL,
            system_prompt=V2_SYSTEM_PROMPT,
        )
        result = await AgenticRagService(
            service, NormativeRouter(remote), VersionFilter(registry)
        ).query(item["question"], scope=item["scope"])
        if result.generation_attempts != 1:
            raise ValueError("O caso congelado não alcançou geração.")
        if question is None:
            assert result.version_filter["final_references"] == original["final_context"]
        items.append(item)
        frozen.append(
            dict(
                **item,
                raw_context=result.version_filter["final_references"],
                temporal_state=result.version_filter,
                references=[r.model_dump() for r in result.references],
                context_notice=service.context_notice,
                before_prompt=remote.prompt,
            )
        )
    save(
        DATASET,
        dict(
            schema_version="1.0",
            status="technical_generation_regression_not_legal_gold",
            items=items,
        ),
    )
    save(output / "frozen_contexts.json", frozen)
    save(
        output / "manifest.json",
        dict(
            schema_version="1.0",
            initial_head="365d28a1d5b21ae27bd7220316aa5aa612ca608e",
            routing="manual_scope_fixed_context",
            retrieval_calls=0,
            reindexing=False,
            settings=dict(
                llm_model=settings.LLM_MODEL,
                embedding_model=settings.EMBEDDING_MODEL,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                top_k=settings.RETRIEVAL_TOP_K,
                base_url=settings.OPENROUTER_BASE_URL,
            ),
            dataset_sha256=dataset_sha256_crlf(DATASET),
            frozen_contexts_sha256=hashlib.sha256(
                (output / "frozen_contexts.json").read_bytes()
            ).hexdigest(),
            calls_per_phase=sum(q["repetitions"] for q in items),
            design="Same questions, final chunks, model and configuration; only temporal grounding changes.",
        ),
    )


def generation_record(answer, result, prompts):
    """Separate what the model produced from what the application returned.

    With a guard, `QueryResult.answer` is the composed final answer, not model output.
    """
    audit = result.output_audit if result else None
    action = audit.guard_action if audit else None
    fallback_reason = None
    if action == "fallback":
        fallback_reason = (
            "regeneration_error" if audit.regeneration_error else "second_guard_rejected"
        )
    return dict(
        prompt=prompts[0] if prompts else None,
        prompts=prompts,
        raw_answer=audit.raw_answer if audit else answer,
        regenerated_answer=audit.regenerated_answer if audit else None,
        final_answer=answer,
        guard_violations=[v.model_dump() for v in audit.guard_violations] if audit else None,
        second_guard_violations=(
            [v.model_dump() for v in audit.second_guard_violations] if audit else None
        ),
        regeneration_error=audit.regeneration_error if audit else None,
        guard_action=action,
        fallback_reason=fallback_reason,
    )


def dataset_sha256_crlf(path):
    """Hash the dataset in its explicit canonical CRLF representation."""
    canonical = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return hashlib.sha256(canonical).hexdigest()


async def run_phase(output, phase):
    frozen = json.loads((output / "frozen_contexts.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    settings = settings_for()
    assert dataset_sha256_crlf(DATASET) == manifest["dataset_sha256"]
    assert settings.LLM_MODEL == manifest["settings"]["llm_model"]
    assert settings.LLM_MAX_TOKENS == manifest["settings"]["max_tokens"]
    registry = NormativeRegistry.load()
    semaphore = asyncio.Semaphore(2)
    completed = 0
    with (output / f"{phase}.jsonl").open("x", encoding="utf-8") as stream:

        async def one(case, repetition):
            nonlocal completed
            async with semaphore:
                client = client_for(settings)
                capture = CaptureClient(client)
                chunks = [RetrievedChunk.model_validate(c) for c in case["raw_context"]]
                audit = VersionAudit.model_validate(case["temporal_state"])
                service = RagService(
                    openrouter=capture,
                    vector_store=None,
                    top_k=5,
                    embedding_model=settings.EMBEDDING_MODEL,
                    llm_model=settings.LLM_MODEL,
                    system_prompt=V2_SYSTEM_PROMPT,
                )
                started = time.perf_counter()
                error, answer, grounding, result = None, None, None, None
                try:
                    if phase == "before":
                        answer = await capture.chat(**case["before_prompt"])
                    else:
                        from rag_baseline.grounding import build_temporal_grounding

                        grounding = build_temporal_grounding(chunks, audit, registry)
                        result = await service.generate(
                            case["question"],
                            chunks,
                            context_notice=case["context_notice"],
                            temporal_grounding=grounding,
                        )
                        answer = result.answer
                        assert [r.model_dump() for r in result.references] == case["references"]
                except Exception as exc:
                    error = type(exc).__name__
                row = dict(
                    id=case["id"],
                    repetition=repetition,
                    phase=phase,
                    question=case["question"],
                    raw_context=case["raw_context"],
                    temporal_state=case["temporal_state"],
                    temporal_grounding=grounding.model_dump(mode="json") if grounding else None,
                    **generation_record(answer, result, capture.prompts),
                    references=case["references"],
                    error=error,
                    latency_seconds=time.perf_counter() - started,
                    provider_receipts=client.receipts,
                )
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
                completed += 1
                if completed % 4 == 0 or completed == manifest["calls_per_phase"]:
                    print(
                        json.dumps(
                            dict(
                                phase=phase, completed=completed, total=manifest["calls_per_phase"]
                            )
                        ),
                        flush=True,
                    )

        await asyncio.gather(
            *(
                one(case, repetition)
                for case in frozen
                for repetition in range(1, case["repetitions"] + 1)
            )
        )


def summarize_annotations(rows):
    """Aggregate explicit technical annotations, without treating them as legal gold."""
    subsets = {
        "TCR": (rows, "temporal_contradiction"),
        "HFA": ([r for r in rows if r["temporal_mode"] == "historical"], "historical_framing"),
        "CSC": ([r for r in rows if r["temporal_mode"] == "current"], "current_state_consistent"),
        "UOR": ([r for r in rows if r["has_unknown"]], "unknown_overclaim"),
        "TRC": ([r for r in rows if r["has_known_relation"]], "relation_consistent"),
        "CGVR": ([r for r in rows if r["has_normative_references"]], "granularity_violation"),
    }
    result = {}
    for metric, (applicable, field) in subsets.items():
        if any(not isinstance(r[field], bool) for r in applicable):
            raise ValueError("Métrica aplicável sem anotação explícita.")
        numerator = sum(r[field] for r in applicable)
        denominator = len(applicable)
        result[metric] = dict(
            numerator=numerator,
            denominator=denominator,
            value=numerator / denominator if denominator else None,
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("prepare", "before", "after"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(
        prepare(args.output.resolve())
        if args.stage == "prepare"
        else run_phase(args.output.resolve(), args.stage)
    )


if __name__ == "__main__":
    main()
