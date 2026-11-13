"""Controlled reproductions of the four frozen temporal failures (not an evaluation)."""

import argparse
import asyncio
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/src"))

from rag_baseline.api import _Runtime  # noqa: E402
from rag_baseline.config import BaselineSettings  # noqa: E402
from rag_baseline.corpus import build_embedding_text, load_corpus  # noqa: E402
from rag_baseline.incremental_index import snapshot_collection  # noqa: E402
from rag_baseline.models import RetrievedChunk  # noqa: E402
from rag_baseline.profiles import apply_profile  # noqa: E402
from rag_baseline.router import NormativeRouter, RouterDecision  # noqa: E402

F1_IDS = ["TEMP-POS-003", "TEMP-POS-004", "TEMP-GRAD-005", "TEMP-GRAD-001"]
ROUTE_CONTROLS = [
    ("CONTROL-POS", "Na pós-graduação, posso cancelar uma disciplina?", "pos_graduacao"),
    (
        "CONTROL-956",
        "Segundo a Resolução 956/2025, posso cancelar uma disciplina?",
        "pos_graduacao",
    ),
    ("CONTROL-GRAD", "Na graduação, posso cancelar uma disciplina?", "graduacao"),
    (
        "CONTROL-RGG",
        "Segundo o Regulamento Geral da Graduação, posso cancelar uma disciplina?",
        "graduacao",
    ),
    ("CONTROL-AMBIGUOUS", "Posso cancelar uma disciplina?", None),
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def original_rows():
    rows = {}
    for domain in ("pos", "grad"):
        path = ROOT / f"evaluation/results/temporal_{domain}_D_001/rows.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            rows[row["id"]] = row | {"original_path": path.relative_to(ROOT).as_posix()}
    return rows


def git(*args):
    return (
        subprocess.check_output(["git", "-c", "core.quotepath=false", *args], cwd=ROOT)
        .decode("utf-8")
        .strip()
    )


def source_hashes():
    paths = [ROOT / p for p in git("ls-files", "code/src/rag_baseline").splitlines()]
    paths.append(Path(__file__))
    return {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in paths}


class Capture:
    """Observe requests/content only; never persist headers, keys or reasoning fields."""

    def __init__(self, client):
        self.calls = []
        self.post = client._post
        client._post = self.record

    async def record(self, path, payload):
        entry = {"endpoint": path, "request": payload, "started_at": datetime.now(UTC).isoformat()}
        self.calls.append(entry)
        try:
            response = await self.post(path, payload)
        except Exception as exc:
            entry["error_type"] = type(exc).__name__
            raise
        entry.update(
            {k: response.get(k) for k in ("id", "model", "provider", "usage", "system_fingerprint")}
        )
        if path == "/chat/completions":
            choice = response.get("choices", [{}])[0]
            entry["raw_content"] = choice.get("message", {}).get("content")
            entry["finish_reason"] = choice.get("finish_reason")
        else:
            entry["embedding_response_sha256"] = digest(
                json.dumps(response.get("data"), sort_keys=True).encode()
            )
        return response


def setup():
    os.chdir(ROOT / "code")
    settings = apply_profile(BaselineSettings(), "duas-regulacoes")
    assert settings.RETRIEVAL_TOP_K == 5
    assert settings.LLM_TEMPERATURE == 0
    assert settings.LLM_MODEL == "qwen/qwen3-30b-a3b-instruct-2507"
    assert (settings.ROUTER_MODEL or settings.LLM_MODEL) == settings.LLM_MODEL
    assert settings.EMBEDDING_MODEL == "openai/text-embedding-3-small"
    assert settings.LLM_MAX_TOKENS == 800
    runtime = _Runtime(settings)
    service = runtime.service()
    assert runtime.store().count() == 507
    return settings, runtime, Capture(service.openrouter)


async def router_runs(runtime, capture, output, repetitions):
    originals = original_rows()
    cases = [
        (i, originals[i]["question"], originals[i]["expected_scope"], repetitions) for i in F1_IDS
    ]
    cases += [(i, q, scope, 1) for i, q, scope in ROUTE_CONTROLS]
    rows = []
    for case_id, question, expected, n in cases:
        for run in range(1, n + 1):
            capture.calls.clear()
            decision = await NormativeRouter(
                runtime.service().openrouter, model=runtime.settings.ROUTER_MODEL
            ).route(question)
            raw = capture.calls[-1].get("raw_content")
            try:
                parsed = RouterDecision.model_validate_json(raw).model_dump()
                validation_error = None
            except (ValueError, TypeError) as exc:
                parsed, validation_error = None, type(exc).__name__
            row = dict(
                case_id=case_id,
                question=question,
                run=run,
                expected_scope=expected,
                router_output=decision.model_dump(),
                parsed_output=parsed,
                validation_error=validation_error,
                calls=list(capture.calls),
            )
            rows.append(row)
            with (output / "rows.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        subset = rows[-n:]
        counts = Counter(r["router_output"]["scope"] or "esclarecer" for r in subset)
        print(json.dumps({"case_id": case_id, "counts": counts}, ensure_ascii=False), flush=True)
    summary = {}
    for case_id, _, expected, n in cases:
        subset = [r for r in rows if r["case_id"] == case_id]
        counts = Counter(r["router_output"]["scope"] or "esclarecer" for r in subset)
        summary[case_id] = dict(
            runs=n,
            counts=counts,
            route_stability_rate=max(counts.values()) / n,
            expected_route_rate=sum(
                r["router_output"]["scope"] == expected and r["validation_error"] is None
                for r in subset
            )
            / n,
        )
    save(output / "summary.json", summary)


async def retrieval_runs(runtime, capture, output):
    original = original_rows()["TEMP-GRAD-002"]
    question = original["question"]
    source = runtime.settings.CORPUS_SOURCES[0]
    target = next(
        c for c in load_corpus(source.path, id_prefix=source.id_prefix) if c.article_number == "68"
    )
    variants = {
        "original": question,
        "plus_graduation": question + " graduação",
        "plus_norm": question + " Resolução 177/2012",
        "plus_article": question + " artigo 68",
        "normative_wording": "O coordenador de estágio do curso será um docente efetivo escolhido entre os professores orientadores do estágio.",
        "without_temporal_wording": "Qual a redação do art. 68, §4º da Resolução 177/2012 no regulamento da graduação?",
    }
    save(
        output / "target.json",
        dict(
            chunk=target.model_dump(),
            embedding_text=build_embedding_text(target, norm_name=source.norm_name),
            representation_note="Reconstructed by the unchanged indexer; original embedding API receipt is unavailable.",
        ),
    )
    rows = []
    store = runtime.store()
    for name, query in variants.items():
        capture.calls.clear()
        embedding = (await runtime.service().openrouter.embed([query]))[0]
        calls = list(capture.calls)
        for sector in (None, "graduacao"):
            eligible = store.collection.get(
                where={"sector": sector} if sector else None, include=[]
            )["ids"]
            rankings = {}
            for k in (5, 10, 20, len(eligible)):
                chunks = store.query(embedding, top_k=k, sector=sector)
                rankings[str(k)] = [
                    dict(
                        rank=c.rank,
                        id=c.id,
                        norm_id=c.norm_id or c.id.split("-art-")[0],
                        article=c.article_number,
                        distance=c.distance,
                        excerpt=c.content[:220],
                    )
                    for c in chunks
                ]
            full = rankings[str(len(eligible))]
            found = next(r for r in full if r["id"] == target.id)
            row = dict(
                case_id="TEMP-GRAD-002",
                variant=name,
                query=query,
                sector=sector,
                target_id=target.id,
                target_rank=found["rank"],
                target_distance=found["distance"],
                eligible_count=len(eligible),
                target_eligible=target.id in eligible,
                rankings=rankings,
                calls=calls,
                production_top_k=5,
            )
            rows.append(row)
            print(
                json.dumps(
                    {k: row[k] for k in ("variant", "sector", "target_rank", "target_distance")}
                ),
                flush=True,
            )
    # Re-embed the unchanged query twice more to observe repeatability, not to select a run.
    repeats = []
    for repetition in range(2, 4):
        capture.calls.clear()
        embedding = (await runtime.service().openrouter.embed([question]))[0]
        repeats.append(
            dict(
                run=repetition,
                calls=list(capture.calls),
                rankings={
                    sector or "both": [
                        c.model_dump() for c in store.query(embedding, top_k=5, sector=sector)
                    ]
                    for sector in (None, "graduacao")
                },
            )
        )
    save(output / "rankings.json", rows)
    save(output / "repeats.json", repeats)
    save(
        output / "summary.json",
        [
            {
                k: row[k]
                for k in ("variant", "sector", "target_rank", "target_distance", "target_eligible")
            }
            for row in rows
        ],
    )


async def generation_runs(runtime, capture, output, repetitions, case_id):
    original = original_rows()[case_id]
    chunks = [RetrievedChunk(**c) for c in original["final_references"]]
    rows = []
    for run in range(1, repetitions + 1):
        capture.calls.clear()
        result = await runtime.service().generate(original["question"], chunks)
        row = dict(
            case_id=case_id,
            question=original["question"],
            run=run,
            mode="fixed_original_final_context",
            final_context_ids=[c.id for c in chunks],
            calls=list(capture.calls),
            answer=result.answer,
            service_result=result.model_dump(mode="json"),
            raw_equals_service=capture.calls[-1]["raw_content"] == result.answer,
        )
        if case_id == "TEMP-GRAD-001":
            row["boundary_replay"] = boundary_replay(original["question"], result)
        rows.append(row)
        with (output / "rows.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(
            json.dumps(dict(case_id=case_id, run=run, answer=result.answer), ensure_ascii=False),
            flush=True,
        )
    save(
        output / "summary.json",
        dict(
            runs=len(rows),
            unique_answers=len({r["answer"] for r in rows}),
            all_raw_equal_service=all(r["raw_equals_service"] for r in rows),
        ),
    )


def boundary_replay(question, result):
    """Pass one observed response through the real API/terminal without another LLM call."""
    from fastapi.testclient import TestClient
    from rich.console import Console

    from rag_baseline.api import create_app
    from rag_baseline.demo import _run_query

    class ObservedResponse:
        async def query(self, question, **kwargs):
            return result

    terminal, saved = io.StringIO(), io.StringIO()
    with TestClient(create_app(service=ObservedResponse())) as client:
        response = client.post("/query", json={"question": question, "sector": "graduacao"})
        response.raise_for_status()
        ok = _run_query(
            Console(file=terminal, width=120, color_system=None),
            client,
            question,
            verbose=False,
            sector="graduacao",
            output=saved,
        )
    terminal_record = json.loads(saved.getvalue())
    phrase = "designado dentre os docentes selecionados para atuação no respectivo curso independentemente de seu vínculo com a UFPI"

    def count(text):
        return " ".join(re.findall(r"\w+", text.casefold())).count(phrase.casefold())

    return dict(
        mode="same_observed_response_replayed_locally_no_extra_generation",
        api_answer=response.json()["answer"],
        terminal_saved_answer=terminal_record["answer"],
        terminal_rendered=terminal.getvalue(),
        terminal_ok=ok,
        all_answers_equal=result.answer == response.json()["answer"] == terminal_record["answer"],
        repeated_phrase=phrase,
        service_phrase_count=count(result.answer),
        terminal_phrase_count=count(terminal.getvalue()),
    )


async def pipeline_runs(runtime, capture, output):
    from rag_baseline.agentic_evaluation import RecordingStore

    service = runtime.service()
    recording = RecordingStore(runtime.store())
    service.vector_store = recording
    originals = original_rows()
    selected = [(case_id, "D") for case_id in F1_IDS + ["TEMP-GRAD-002", "TEMP-POS-001"]]
    selected.append(("TEMP-GRAD-002", "B"))
    for case_id, condition in selected:
        original = originals[case_id]
        capture.calls.clear()
        recording.last = []
        if condition == "D":
            result = await runtime.agentic().query(original["question"])
        else:
            result = await service.query(original["question"])
        pre = [c.model_dump() for c in recording.last]
        final = (result.version_filter or {}).get("final_references", pre)
        row = dict(
            case_id=case_id,
            condition=condition,
            question=original["question"],
            expected_scope=original["expected_scope"],
            expected_action=original["expected_action"],
            router_output=result.route,
            retrieved_ids=[r["id"] for r in pre],
            final_context_ids=[r["id"] for r in final],
            retrieved=pre,
            final_context=final,
            answer=result.answer,
            result=result.model_dump(mode="json"),
            calls=list(capture.calls),
        )
        with (output / "rows.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(
            json.dumps(
                dict(
                    case_id=case_id,
                    condition=condition,
                    scope=result.selected_scope,
                    clarification=result.needs_clarification,
                    final_ids=row["final_context_ids"],
                )
            ),
            flush=True,
        )


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase", choices=["preserve", "router", "retrieval", "generation", "pipeline"]
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument(
        "--case-id", choices=["TEMP-POS-001", "TEMP-GRAD-001"], default="TEMP-POS-001"
    )
    parser.add_argument("--original-generator", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    settings, runtime, capture = setup()
    if args.original_generator:
        from rag_baseline.experiment_v2 import PROMPT

        runtime.service().system_prompt = PROMPT
    before = snapshot_collection(runtime.store().collection)
    manifest = dict(
        status="running",
        phase=args.phase,
        started_at=datetime.now(UTC).isoformat(),
        git_commit=git("rev-parse", "HEAD"),
        git_status=git("status", "--short"),
        production_inputs_dirty=bool(
            git(
                "diff",
                "HEAD",
                "--name-only",
                "--",
                "code/src",
                "data",
                "evaluation/datasets",
                "evaluation/corpora",
            )
        ),
        source_sha256=source_hashes(),
        model=settings.LLM_MODEL,
        router_model=settings.ROUTER_MODEL or settings.LLM_MODEL,
        embedding=settings.EMBEDDING_MODEL,
        top_k=settings.RETRIEVAL_TOP_K,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        collection=settings.CHROMA_COLLECTION,
        index_sha256=before["sha256"],
        indexed_chunks=before["count"],
        generator_prompt_sha256=digest(runtime.service().system_prompt.encode("utf-8")),
        original_generator=args.original_generator,
        confirmatory=False,
    )
    save(output / "manifest.json", manifest)
    if args.phase == "preserve":
        protected = git(
            "ls-files", "evaluation", "data", "code/scripts", "code/uv.lock"
        ).splitlines()
        save(
            output / "preservation.json",
            {"index": before, "files": {p: digest((ROOT / p).read_bytes()) for p in protected}},
        )
        save(
            output / "original_cases.json",
            {
                k: v
                for k, v in original_rows().items()
                if k in F1_IDS + ["TEMP-GRAD-002", "TEMP-POS-001"]
            },
        )
    elif args.phase == "router":
        await router_runs(runtime, capture, output, args.repetitions)
    elif args.phase == "retrieval":
        await retrieval_runs(runtime, capture, output)
    elif args.phase == "generation":
        await generation_runs(runtime, capture, output, args.repetitions, args.case_id)
    elif args.phase == "pipeline":
        await pipeline_runs(runtime, capture, output)
    after = snapshot_collection(runtime.store().collection)
    assert before == after, "Index changed during read-only reproduction"
    manifest.update(
        status="completed",
        finished_at=datetime.now(UTC).isoformat(),
        index_unchanged=True,
        artifact_sha256={
            p.name: digest(p.read_bytes()) for p in output.iterdir() if p.name != "manifest.json"
        },
    )
    save(output / "manifest.json", manifest)


if __name__ == "__main__":
    asyncio.run(main())
