"""Fixed-context structured-output experiment. Real API calls require --stage run.

Previous runs are read-only. No retrieval, embeddings, indexing or extra API calls.
Semantic annotations remain explicit provisional technical labels, not legal gold.
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from pathlib import Path

from rag_baseline.generation_evaluation import save, settings_for
from rag_baseline.grounding import build_temporal_grounding
from rag_baseline.models import RetrievedChunk
from rag_baseline.prompts import V2_SYSTEM_PROMPT
from rag_baseline.service import RagService
from rag_baseline.versioning import NormativeRegistry, VersionAudit

ROOT = Path(__file__).resolve().parents[3]
PREVIOUS = ROOT / "evaluation/results/temporal_generation_grounding_v1_001"
OUTPUT = ROOT / "evaluation/results/structured_normative_output_v1_001"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path):
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def rate(numerator, denominator):
    return dict(
        numerator=numerator,
        denominator=denominator,
        value=numerator / denominator if denominator else None,
    )


def summarize(rows):
    """Explicit per-answer annotations; completion is independent of guard acceptance."""
    metrics = {}
    for stage in ("raw", "final"):
        for name, field in (
            ("CGVR", "citation_violation"),
            ("UCER", "chronology_violation"),
            ("TCR", "temporal_contradiction"),
        ):
            if any(not isinstance(row[stage][field], bool) for row in rows):
                raise ValueError("Missing applicable technical annotation")
            metrics[f"{stage}_{name}"] = rate(sum(row[stage][field] for row in rows), len(rows))
    activated = [r for r in rows if r["guard_action"] in ("regenerated", "fallback")]
    metrics.update(
        official_reference_CGVR=rate(
            sum(r["official_reference_violation"] for r in rows), len(rows)
        ),
        guard_activation=rate(len(activated), len(rows)),
        regeneration_success=rate(
            sum(r["guard_action"] == "regenerated" for r in activated), len(activated)
        ),
        fallback=rate(sum(r["guard_action"] == "fallback" for r in rows), len(rows)),
        answer_completion=rate(sum(r["completed"] for r in rows), len(rows)),
    )
    return metrics


def prepare():
    previous = json.loads((PREVIOUS / "manifest.json").read_text("utf-8"))
    settings = settings_for()
    config = dict(
        llm_model=settings.LLM_MODEL,
        embedding_model=settings.EMBEDDING_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        top_k=settings.RETRIEVAL_TOP_K,
        base_url=settings.OPENROUTER_BASE_URL,
    )
    assert config == previous["settings"]
    protected = [
        "manifest.json",
        "frozen_contexts.json",
        "before.jsonl",
        "after.jsonl",
        "annotations.jsonl",
        "summary.json",
    ]
    save(
        OUTPUT / "manifest.json",
        dict(
            schema_version="1.0",
            initial_head="6aa833d40ec9568aa920947ec7b4cfd74fde6622",
            initial_branch="fix/temporal-generation-grounding-v1",
            initial_status="clean",
            work_branch="fix/structured-normative-output-v1",
            settings=config,
            source_results=PREVIOUS.relative_to(ROOT).as_posix(),
            source_hashes={name: sha(PREVIOUS / name) for name in protected},
            first_generation_count=44,
            maximum_provider_calls=88,
            repetitions={
                r["id"]: r["repetitions"]
                for r in json.loads((PREVIOUS / "frozen_contexts.json").read_text("utf-8"))
            },
            routing="manual_scope_fixed_final_context",
            retrieval_calls=0,
            embedding_calls=0,
            reindexing=False,
            maximum_regenerations=1,
            change="Deterministic reference/status composition plus answer_body instructions and bounded output guard.",
        ),
    )
    save(
        OUTPUT / "annotation_protocol.json",
        dict(
            status="provisional_technical_not_independently_validated",
            frozen_before_provider_calls=True,
            unit="one query; all 44 temporal cases",
            citation_rule="Any unvalidated subdivision, unknown article or norm locator in raw/final; broader than the previous bibliography-only CGVR. Old results are retained and also replayed under this protocol.",
            chronology_rule="Affirmative unsupported publication/effectivity/retroactivity/other date or scope claims. Norm identifier year alone is not chronology.",
            temporal_rule="Chronology, unknown/current certification, historical denial or current framing, incorrect relation/direction or comparison-role contradiction; inspect beyond guard matches.",
            completion_rule="Final body provides substantive normative content answering the query. A correct relation answers a validity query; conservative unknown-status answer answers the epistemic unknown query. Fallback and content-denial do not count.",
            official_reference_rule="Displayed NormativeReference entries only, checked against final evidence and ceiling. Legacy reference.content is a full evidence excerpt, not a bibliographic locator.",
            limitations=[
                "Bounded Portuguese guard patterns are not a semantic oracle.",
                "Preliminary technical annotation; no independent legal gold.",
                "Repeated generation at temperature zero is not an independent population sample.",
                "Fixed final contexts isolate generation; no retrieval/router quality inference.",
            ],
        ),
    )


class Capture:
    def __init__(self, delegate):
        self.delegate = delegate
        self.calls = []
        self.responses = []

    async def chat(self, **payload):
        self.calls.append(payload)
        answer = await self.delegate.chat(**payload)
        self.responses.append(answer)
        return answer


async def run():
    from rag_baseline.experiment import client_for

    manifest = json.loads((OUTPUT / "manifest.json").read_text("utf-8"))
    for name, expected in manifest["source_hashes"].items():
        assert sha(PREVIOUS / name) == expected
    settings = settings_for()
    assert (
        dict(
            llm_model=settings.LLM_MODEL,
            embedding_model=settings.EMBEDDING_MODEL,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            top_k=settings.RETRIEVAL_TOP_K,
            base_url=settings.OPENROUTER_BASE_URL,
        )
        == manifest["settings"]
    )
    frozen = json.loads((PREVIOUS / "frozen_contexts.json").read_text("utf-8"))
    old_after = {r["id"]: r for r in jsonl(PREVIOUS / "after.jsonl")}
    registry, semaphore = NormativeRegistry.load(), asyncio.Semaphore(2)
    streams = {
        name: (OUTPUT / name).open("x", encoding="utf-8")
        for name in ("raw_generations.jsonl", "guard_results.jsonl", "final_outputs.jsonl")
    }
    completed = 0

    def write(name, row):
        streams[name].write(json.dumps(row, ensure_ascii=False) + "\n")
        streams[name].flush()

    async def one(case, repetition):
        nonlocal completed
        async with semaphore:
            client = client_for(settings)
            capture = Capture(client)
            chunks = [RetrievedChunk.model_validate(c) for c in case["raw_context"]]
            grounding = build_temporal_grounding(
                chunks, VersionAudit.model_validate(case["temporal_state"]), registry
            )
            assert grounding.model_dump(mode="json") == old_after[case["id"]]["temporal_grounding"]
            service = RagService(
                openrouter=capture,
                vector_store=None,
                top_k=5,
                llm_model=settings.LLM_MODEL,
                embedding_model=settings.EMBEDDING_MODEL,
                system_prompt=V2_SYSTEM_PROMPT,
            )
            started = time.perf_counter()
            error, result = None, None
            try:
                result = await service.generate(
                    case["question"],
                    chunks,
                    context_notice=case["context_notice"],
                    temporal_grounding=grounding,
                )
                assert [r.model_dump() for r in result.references] == case["references"]
                assert len(capture.calls) <= 2
                if len(capture.calls) == 2:
                    assert capture.calls[1]["system_prompt"] == capture.calls[0]["system_prompt"]
                    assert capture.calls[1]["user_prompt"].startswith(
                        capture.calls[0]["user_prompt"]
                    )
            except Exception as exc:
                error = type(exc).__name__
            key = dict(id=case["id"], repetition=repetition)
            audit = result.output_audit.model_dump(mode="json") if result else None
            write(
                "raw_generations.jsonl",
                dict(
                    **key,
                    question=case["question"],
                    raw_answer=capture.responses[0] if capture.responses else None,
                    regenerated_answer=capture.responses[1] if len(capture.responses) > 1 else None,
                    context_source=manifest["source_results"] + "/frozen_contexts.json",
                    temporal_grounding=grounding.model_dump(mode="json"),
                    prompt_sha256=[
                        {k: hashlib.sha256(v.encode()).hexdigest() for k, v in call.items()}
                        for call in capture.calls
                    ],
                    provider_receipts=client.receipts,
                    latency_seconds=time.perf_counter() - started,
                    error=error,
                ),
            )
            write(
                "guard_results.jsonl",
                dict(**key, audit=audit, provider_calls=len(capture.calls), error=error),
            )
            write(
                "final_outputs.jsonl",
                dict(**key, result=result.model_dump(mode="json") if result else None, error=error),
            )
            completed += 1
            if completed % 4 == 0 or completed == 44:
                print(json.dumps(dict(completed=completed, total=44)), flush=True)

    try:
        await asyncio.gather(*(one(c, r) for c in frozen for r in range(1, c["repetitions"] + 1)))
    finally:
        for stream in streams.values():
            stream.close()
    sources = [
        "service.py",
        "models.py",
        "output_contracts.py",
        "normative_output.py",
        "structured_evaluation.py",
    ]
    save(
        OUTPUT / "execution.json",
        dict(
            implementation_head=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            source_hashes={name: sha(ROOT / "code/src/rag_baseline" / name) for name in sources},
            query_count=completed,
            provider_calls=sum(r["provider_calls"] for r in jsonl(OUTPUT / "guard_results.jsonl")),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("prepare", "run"), required=True)
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare()
    else:
        asyncio.run(run())


if __name__ == "__main__":
    main()
