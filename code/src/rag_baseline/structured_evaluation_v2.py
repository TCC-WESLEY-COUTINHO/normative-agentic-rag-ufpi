"""Controlled V2 generation on the exact 44 V1 inputs; no retrieval or extra API.

Prepare freezes inputs, code, configuration and annotation rules. Run refuses
overwrite or drift. An invalid run must be retained and fully restarted with a
new run ID, never resumed selectively. Semantic labels require explicit review.
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from rag_baseline.content_locators import POLICY_VERSION, ContentLocatorPolicy
from rag_baseline.generation_evaluation import settings_for
from rag_baseline.grounding import TemporalGroundingContext
from rag_baseline.models import RetrievedChunk
from rag_baseline.normative_output import allowed_temporal_facts, normative_references
from rag_baseline.output_contracts import GenerationAudit
from rag_baseline.prompts import V2_SYSTEM_PROMPT
from rag_baseline.service import RagService
from rag_baseline.structured_evaluation import jsonl, rate

ROOT = Path(__file__).resolve().parents[3]
V1 = ROOT / "evaluation/results/structured_normative_output_v1_001"
CONTEXTS = ROOT / "evaluation/results/temporal_generation_grounding_v1_001/frozen_contexts.json"
OUTPUT = ROOT / "evaluation/results/structured_normative_output_v2_001"


def now():
    return datetime.now(UTC).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def append(path, value):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")


def event(output, phase, action, operation, result, artifacts=(), commit=None):
    path = output / "execution_log.jsonl"
    step = len(path.read_text("utf-8").splitlines()) + 1
    append(
        path,
        dict(
            timestamp=now(),
            step_id=f"EX-V2-{step:03d}",
            phase=phase,
            action=action,
            command_or_operation=operation,
            result=result,
            artifact=list(artifacts),
            commit=commit,
        ),
    )


def verify_hashes(root, hashes):
    for name, expected in hashes.items():
        if sha(root / name) != expected:
            raise ValueError(f"Frozen input/code changed: {name}")


def summarize(rows, known_chronology):
    for row in rows:
        for stage in ("raw", "final"):
            if any(
                not isinstance(row[stage][field], bool)
                for field in (
                    "unsupported_locator",
                    "unsupported_chronology",
                    "temporal_contradiction",
                )
            ):
                raise ValueError("Explicit reviewed annotations required")
        if row["guard_action"] == "fallback" and row["completed"]:
            raise ValueError("Primary completion excludes all fallbacks")
    metrics = {}
    n = len(rows)
    for stage in ("raw", "final"):
        for name, field in (
            ("ULER", "unsupported_locator"),
            ("UCER", "unsupported_chronology"),
            ("TCR", "temporal_contradiction"),
        ):
            metrics[f"{stage}_{name}"] = rate(sum(r[stage][field] for r in rows), n)
    mentions = [m for r in rows for m in r["supported_locator_mentions"]]
    rejected = sum(m["guard_rejected"] for m in mentions)
    activated = [r for r in rows if r["guard_action"] != "accepted"]
    metrics.update(
        official_reference_response=rate(
            sum(r["official_reference_invalid_entries"] > 0 for r in rows), n
        ),
        official_reference_entry=rate(
            sum(r["official_reference_invalid_entries"] for r in rows),
            sum(r["official_reference_entries"] for r in rows),
        ),
        SLAR=rate(len(mentions) - rejected, len(mentions)),
        SLFRR=rate(rejected, len(mentions)),
        guard_detected_UCER=rate(
            sum(r["raw"]["unsupported_chronology"] and r["chronology_detected"] for r in rows), n
        ),
        known_chronology_detection_recall=rate(
            sum(r["detected"] for r in known_chronology), len(known_chronology)
        ),
        guard_activation=rate(len(activated), n),
        regeneration_success=rate(
            sum(r["guard_action"] == "regenerated" for r in rows), len(activated)
        ),
        fallback=rate(sum(r["guard_action"] == "fallback" for r in rows), n),
        answer_completion=rate(sum(r["completed"] for r in rows), n),
        guard_false_positive=rate(sum(r["guard_false_positive"] for r in rows), n),
    )
    return metrics


def config(settings):
    return dict(
        llm_model=settings.LLM_MODEL,
        embedding_model=settings.EMBEDDING_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        top_k=settings.RETRIEVAL_TOP_K,
        base_url=settings.OPENROUTER_BASE_URL,
    )


def verify_v1_source():
    baseline = json.loads((V1 / "manifest.json").read_text("utf-8"))
    if sha(CONTEXTS) != baseline["source_hashes"]["frozen_contexts.json"]:
        raise ValueError("Frozen contexts differ from the historical V1 manifest")


def prepare(output):
    verify_v1_source()
    initial = json.loads((output / "initial_audit.json").read_text("utf-8"))
    baseline = json.loads((V1 / "manifest.json").read_text("utf-8"))
    settings = settings_for()
    if config(settings) != baseline["settings"]:
        raise ValueError("V1 configuration must remain identical")
    previous = {r["id"]: r for r in jsonl(V1 / "raw_generations.jsonl")}
    frozen = json.loads(CONTEXTS.read_text("utf-8"))
    inputs = []
    for case in frozen:
        grounding = TemporalGroundingContext.model_validate(
            previous[case["id"]]["temporal_grounding"]
        )
        chunks = [RetrievedChunk.model_validate(c) for c in case["raw_context"]]
        references = normative_references(chunks, grounding)
        _, locators = ContentLocatorPolicy.for_generation(
            case["question"], grounding, references, chunks
        )
        inputs.append(
            dict(
                **case,
                grounding=grounding.model_dump(mode="json"),
                official_references=[r.model_dump() for r in references],
                allowed_content_locators=[locator.model_dump() for locator in locators],
                allowed_temporal_facts=allowed_temporal_facts(grounding).model_dump(),
            )
        )
    expected = [10, 1, 10, 1, 10, 1, 1, 10]
    if [c["repetitions"] for c in inputs] != expected:
        raise ValueError("Exact V1 repetitions required")
    save(output / "frozen_inputs.json", inputs)
    protocol = dict(
        schema_version="2.0",
        frozen_at=now(),
        frozen_before_provider_calls=True,
        annotation_status="provisional_technical_not_independent_legal_gold",
        unit="44 first-attempt queries; identical A=10 B=1 C=10 D=1 E=10 F=1 G=1 H=10",
        official_reference_rule="Only application-rendered NormativeReference entries, not legacy full evidence excerpts. Exact final evidence, deterministic dedup/order and V1 article/source display ceiling.",
        locator_rule="Scoped norm/article/subdivision authorized by explicit query bound to final evidence, amendment target, known-relation proof or explicitly validated structural evidence. Raw chunk/provider text never authorizes subdivision. Article does not imply caput.",
        locator_mention_unit="First raw body only: each ARTICLE regex occurrence and each subdivision occurrence is a locator unit. Overlap (art. N, Roman) is counted once, as the composite subdivision; separate article and explicit paragraph tokens count separately. Norm identifiers alone are not SLAR units. Include only structurally supported occurrences in SLAR/SLFRR. Annotator checks normalized binding and spans. Retry mentions are recorded separately and excluded from these primary denominators.",
        supported_acceptance_rule="Accepted locator means no locator violation at that mention; an unrelated chronology/TCR violation may still trigger regeneration/fallback. SLFRR counts supported mentions rejected specifically for locator policy.",
        ULER_rule="Final complete rendered answer contains any unallowed norm/article/subdivision, including caput. Inspect body and official display separately; no requirement that the locator be bibliographic.",
        chronology_rule="Affirmative unsupported publication/effectivity/retroactivity, immediate effects, entry into force, publication-relative temporal limits, or other invented temporal scope. Negative efficacy after publication still asserts an unsupported boundary. Norm identifier years and query-supported historical framing are not chronology. Inspect beyond regex findings.",
        known_chronology_set=[
            dict(id="A_grad_historical", repetition=9),
            *[dict(id="E_validity", repetition=i) for i in (3, 6, 7, 9, 10)],
        ],
        known_recall_rule="Correct direct chronology-category findings / six previously annotated V1 raw instances; unrelated locator findings do not count. This is instance recall on the known set, not general linguistic recall.",
        temporal_rule="Inspect unknown-current certification, historical denial/current framing, direction or total-repeal errors, comparison roles and temporal contradictions; unsupported chronology alone is counted under UCER, not automatically under TCR (same distinction as V1). Past constructions remain past when scoped by the query or local framing; record ambiguities.",
        false_positive_rule="Semantically permitted first raw answer causes guard activation solely through findings unsupported by the reviewed frozen policy; denominator all 44 queries. Record erroneous individual findings in additional detail even when another real violation makes the whole rejection correct.",
        completion_rule="Primary completion requires a non-fallback body that answers the question substantively; a conservative unknown-status answer answers G. A correct deterministic relation in a fallback does not count. Guard acceptance alone is insufficient. Record content-denial/irrelevance independently.",
        regeneration_rule="At most one retry, identical system prompt, user prompt prefix, evidence, grounding, locators, references and facts; append only findings/rewrite request. Preserve first raw and retry separately.",
        denominators="All primary query rates use 44 if all generations succeed; official entry rate uses all displayed entries; SLAR/SLFRR use reviewed supported first-raw locator occurrences; retry success uses activated queries; known recall uses exactly six. Zero denominator => null.",
        no_tuning="After the first real call, do not change prompt, guard, parser, policy, retry, fallback, criteria, cases or contexts. A genuine invalidating infrastructure bug requires retained invalid run and full restart with a new run ID.",
        limitations=[
            "bounded parser and Portuguese patterns",
            "preliminary technical annotation",
            "eight questions with concentrated repetitions",
            "temperature zero does not imply determinism or independent samples",
            "no general legal correctness or global validity certification",
        ],
    )
    save(output / "annotation_protocol.json", protocol)
    paths = list((ROOT / "code/src/rag_baseline").glob("*.py"))
    paths += list((ROOT / "code/tests/rag_baseline").glob("test_*v2.py"))
    paths += [
        CONTEXTS,
        ROOT / "data/normative_registry.json",
        output / "frozen_inputs.json",
        output / "annotation_protocol.json",
    ]
    paths += [p for p in V1.rglob("*") if p.is_file()]
    hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    save(
        output / "manifest.json",
        dict(
            schema_version="2.0",
            branch=branch,
            initial_head=initial["initial_head"],
            initial_branch=initial["initial_branch"],
            initial_status=initial["initial_status"],
            experimental_head=head,
            settings=config(settings),
            guard_version=GenerationAudit.model_fields["guard_version"].default,
            policy_version=POLICY_VERSION,
            query_set_hash=digest([(c["id"], c["question"], c["repetitions"]) for c in inputs]),
            context_hash=digest([c["raw_context"] for c in inputs]),
            grounding_hash=digest([c["grounding"] for c in inputs]),
            code_hashes={k: v for k, v in hashes.items() if k.startswith("code/")},
            frozen_hashes=hashes,
            prepared_at=now(),
            start_timestamp=None,
            end_timestamp=None,
            number_of_provider_calls=0,
            queries=44,
            maximum_provider_calls=88,
            maximum_regenerations=1,
            source_results=V1.relative_to(ROOT).as_posix(),
            retrieval_calls=0,
            embedding_calls=0,
            router_calls=0,
            version_filter_calls=0,
            reindexing=False,
            execution_status="prepared",
        ),
    )
    event(
        output,
        "freeze",
        "Protocolo, 44 entradas e código congelados",
        "structured_evaluation_v2 --stage prepare",
        dict(queries=44, provider_calls=0, code_hashes=len(paths)),
        ["manifest.json", "frozen_inputs.json", "annotation_protocol.json"],
        head,
    )


class Recorder:
    def __init__(self, delegate, output, case, repetition, frozen_hashes):
        self.delegate, self.output = delegate, output
        self.case, self.repetition = case, repetition
        self.frozen_hashes = frozen_hashes
        self.calls, self.responses = [], []

    async def chat(self, **payload):
        verify_hashes(ROOT, self.frozen_hashes)
        self.calls.append(payload)
        attempt, started, timestamp = len(self.calls), time.perf_counter(), now()
        receipt_count = len(self.delegate.receipts)
        event(
            self.output,
            "provider",
            "Generation call started",
            "OpenRouter chat/completions",
            dict(case_id=self.case["id"], repetition=self.repetition, attempt=attempt),
        )
        error = None
        try:
            answer = await self.delegate.chat(**payload)
            self.responses.append(answer)
            append(
                self.output / "provider_attempts.jsonl",
                dict(
                    case_id=self.case["id"],
                    repetition=self.repetition,
                    attempt=attempt,
                    timestamp=now(),
                    raw_answer=answer,
                    prompt_sha256={
                        key: hashlib.sha256(value.encode()).hexdigest()
                        for key, value in payload.items()
                    },
                ),
            )
            return answer
        except BaseException as exc:
            error = type(exc).__name__
            raise
        finally:
            receipt = (
                self.delegate.receipts[-1] if len(self.delegate.receipts) > receipt_count else {}
            )
            usage = receipt.get("usage")
            append(
                self.output / "provider_calls.jsonl",
                dict(
                    case_id=self.case["id"],
                    repetition=self.repetition,
                    attempt=attempt,
                    timestamp=timestamp,
                    model=self.delegate.llm_model,
                    success=error is None,
                    error=error,
                    token_usage=usage,
                    latency_seconds=time.perf_counter() - started,
                    cost_unit=dict(currency="USD", value=usage.get("cost"))
                    if usage and usage.get("cost") is not None
                    else None,
                    receipt_id=receipt.get("id"),
                ),
            )


async def run(output):
    from rag_baseline.experiment import client_for

    manifest = json.loads((output / "manifest.json").read_text("utf-8"))
    verify_hashes(ROOT, manifest["frozen_hashes"])
    settings = settings_for()
    if config(settings) != manifest["settings"] or manifest["execution_status"] != "prepared":
        raise ValueError("Configuration drift or run already started")
    if not settings.api_key_value():
        raise ValueError("Provider credential is not configured")
    names = (
        "raw_generations.jsonl",
        "guard_results.jsonl",
        "final_outputs.jsonl",
        "provider_calls.jsonl",
        "provider_attempts.jsonl",
    )
    if any((output / n).exists() for n in names):
        raise ValueError("Refusing overwrite/resume; retain invalid run and use a new run ID")
    streams = {
        n: (output / n).open("x", encoding="utf-8")
        for n in names
        if n not in {"provider_calls.jsonl", "provider_attempts.jsonl"}
    }
    (output / "provider_calls.jsonl").touch(exist_ok=False)
    (output / "provider_attempts.jsonl").touch(exist_ok=False)

    def write(name, value):
        streams[name].write(json.dumps(value, ensure_ascii=False) + "\n")
        streams[name].flush()

    manifest.update(start_timestamp=now(), execution_status="running")
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    inputs = json.loads((output / "frozen_inputs.json").read_text("utf-8"))
    semaphore, completed = asyncio.Semaphore(2), 0

    async def one(case, repetition):
        nonlocal completed
        async with semaphore:
            capture = Recorder(
                client_for(settings), output, case, repetition, manifest["frozen_hashes"]
            )
            grounding = TemporalGroundingContext.model_validate(case["grounding"])
            chunks = [RetrievedChunk.model_validate(c) for c in case["raw_context"]]
            result = await RagService(
                openrouter=capture,
                vector_store=None,
                top_k=settings.RETRIEVAL_TOP_K,
                embedding_model=settings.EMBEDDING_MODEL,
                llm_model=settings.LLM_MODEL,
                system_prompt=V2_SYSTEM_PROMPT,
            ).generate(
                case["question"],
                chunks,
                context_notice=case["context_notice"],
                temporal_grounding=grounding,
            )
            audit = result.output_audit.model_dump(mode="json")
            assert audit["allowed_content_locators"] == case["allowed_content_locators"]
            assert [r.model_dump() for r in result.references] == case["references"]
            assert [r.model_dump() for r in result.normative_output.references] == case[
                "official_references"
            ]
            assert (
                result.normative_output.allowed_temporal_facts.model_dump()
                == case["allowed_temporal_facts"]
            )
            assert len(capture.calls) <= 2
            if len(capture.calls) == 2:
                assert capture.calls[0]["system_prompt"] == capture.calls[1]["system_prompt"]
                assert capture.calls[1]["user_prompt"].startswith(capture.calls[0]["user_prompt"])
            key = dict(id=case["id"], repetition=repetition)
            write(
                "raw_generations.jsonl",
                dict(
                    **key,
                    question=case["question"],
                    raw_answer=audit["raw_answer"],
                    raw_guard_violations=audit["guard_violations"],
                    regenerated_answer=audit["regenerated_answer"],
                    allowed_content_locators=audit["allowed_content_locators"],
                    official_references=case["official_references"],
                    allowed_temporal_facts=case["allowed_temporal_facts"],
                    temporal_grounding=case["grounding"],
                    prompt_sha256=[
                        {k: hashlib.sha256(v.encode()).hexdigest() for k, v in c.items()}
                        for c in capture.calls
                    ],
                    provider_receipts=capture.delegate.receipts,
                ),
            )
            write(
                "guard_results.jsonl", dict(**key, audit=audit, provider_calls=len(capture.calls))
            )
            write(
                "final_outputs.jsonl",
                dict(
                    **key,
                    result=result.model_dump(mode="json"),
                    fallback=audit["guard_action"] == "fallback",
                ),
            )
            if audit["regeneration_error"]:
                raise ValueError("Provider failure invalidates this controlled run")
            completed += 1
            if completed % 4 == 0 or completed == 44:
                print(json.dumps(dict(completed=completed, total=44)), flush=True)

    try:
        async with asyncio.TaskGroup() as group:
            for case in inputs:
                for repetition in range(1, case["repetitions"] + 1):
                    group.create_task(one(case, repetition))
        verify_hashes(ROOT, manifest["frozen_hashes"])
        manifest["execution_status"] = "complete"
    except BaseException:
        manifest["execution_status"] = "invalid_do_not_resume"
        raise
    finally:
        for stream in streams.values():
            stream.close()
        manifest.update(
            end_timestamp=now(),
            number_of_provider_calls=len(jsonl(output / "provider_calls.jsonl")),
            completed_queries=completed,
        )
        (output / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        event(
            output,
            "experiment",
            "Controlled run ended",
            "structured_evaluation_v2 --stage run",
            dict(
                status=manifest["execution_status"],
                queries=completed,
                provider_calls=manifest["number_of_provider_calls"],
            ),
            names,
            manifest["experimental_head"],
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("prepare", "run"), required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare(args.output.resolve())
    else:
        asyncio.run(run(args.output.resolve()))


if __name__ == "__main__":
    main()
