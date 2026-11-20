"""Paired execution of the conditions over the real integrated runtime.

Every run gets a fresh runtime and conversation. Only the question reaches the pipeline;
scoring keys are read after execution. Requests are reserved against a budget before they
are sent and nothing is retried. Output directories must live outside the repository.

Usage: python -m evaluation.adaptive_rag.run --output DIR --split DEV --usd 0.20

ADAPTIVE_RAG_ENV_FILE selects the credentials file (default: code/.env).
ADAPTIVE_RAG_INDEX_DIR selects the copied index directory
(default: .local/adaptive-rag-env/chroma_copy). Defaults are relative to the repository.
"""

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import time
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path

from .dataset import load
from .split import split

REPO = Path(__file__).resolve().parents[2]
INDEX_COPY = Path(
    os.environ.get("ADAPTIVE_RAG_INDEX_DIR", REPO / ".local/adaptive-rag-env/chroma_copy")
)
CREDENTIALS_ENV = Path(os.environ.get("ADAPTIVE_RAG_ENV_FILE", REPO / "code/.env"))
DATA_DIR = REPO / "data"
AGENT_ID = "chatbot_ufpi_integrated_v1"
# Chat completions are pinned to one provider, without fallback, so that every condition is
# served by the same deployment; a refusal is recorded as a failure, never rerouted.
PROVIDER_ROUTE = {"order": ["nebius"], "allow_fallbacks": False}
FROZEN = dict(
    LLM_MODEL="qwen/qwen3-30b-a3b-instruct-2507",
    LLM_TEMPERATURE=0,
    LLM_MAX_TOKENS=800,
    EMBEDDING_MODEL="openai/text-embedding-3-small",
    ROUTING_MODE="intent_v1",
    ROUTER_MODEL=None,
    CHROMA_COLLECTION="ufpi_duas_regulacoes_setor",
)


def _sha(data):
    data = data if isinstance(data, bytes) else (data or "").encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def settings_for(top_k):
    from rag_baseline.integrated_runtime import IntegratedRuntimeSettings
    from rag_baseline.profiles import apply_profile

    settings = apply_profile(
        IntegratedRuntimeSettings(_env_file=str(CREDENTIALS_ENV)), "duas-regulacoes"
    ).model_copy(
        update=dict(
            CHROMA_PERSIST_DIR=INDEX_COPY,
            RETRIEVAL_TOP_K=top_k,
            # The prototype identity replies are not part of the evaluated conversation graph.
            ASSISTANT_IDENTITY="off",
        )
    )
    for name, expected in FROZEN.items():
        if getattr(settings, name) != expected:
            raise RuntimeError(f"frozen parameter differs: {name}")
    return settings


def prepare_environment(settings):
    for name, value in (
        ("LANGFUSE_TRACING", "false"),
        ("LANGCHAIN_TRACING_V2", "false"),
        ("LANGSMITH_TRACING", "false"),
        ("DATABASE_TYPE", "sqlite"),
    ):
        os.environ[name] = value
    if not os.environ.get("OPENROUTER_API_KEY") and settings.api_key_value():
        os.environ["OPENROUTER_API_KEY"] = settings.api_key_value()


def code_identity():
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(REPO), *args], capture_output=True, check=True
        ).stdout

    untracked = git(
        "ls-files",
        "--others",
        "--exclude-standard",
        "code/src",
        "evaluation/adaptive_rag",
    )
    digest = hashlib.sha256(git("diff", "HEAD", "--", "code/src"))
    for name in sorted(untracked.decode().split()):
        digest.update(name.encode() + (REPO / name).read_bytes())
    return dict(
        git_commit=git("rev-parse", "HEAD").decode().strip(),
        working_tree_sha256=digest.hexdigest(),
    )


def corpus_identity():
    registry = (REPO / "data/normative_registry.json").read_bytes()
    index = (INDEX_COPY / "chroma.sqlite3").read_bytes()
    return dict(registry_sha256=_sha(registry), index_sqlite_sha256=_sha(index))


def purpose_of(path, payload):
    if path == "/embeddings":
        return "embedding"
    messages = payload.get("messages") or []
    user = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
    if payload.get("response_format"):
        schema = (payload["response_format"].get("json_schema") or {}).get(
            "schema"
        ) or {}
        properties = schema.get("properties", {})
        if "claims" in properties:
            return "claim_verification"
        if "personal_facts_needed" in properties:
            return "requirement_plan"
        if "associations" in properties:
            return "evidence_association"
        return "scope_gate" if "decision" in properties else "router"
    if "[AFIRMAÇÕES REPROVADAS]" in user or "[REQUISITOS NÃO CONTEMPLADOS]" in user:
        return "semantic_repair"
    if "[REGENERATION VIOLATIONS]" in user:
        return "regeneration"
    return "generation" if user.startswith("CONTEXTO NORMATIVO") else "chat_other"


def _plain(value):
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return json.loads(json.dumps(asdict(value), default=str))
    return json.loads(json.dumps(value, default=str))


class Tap:
    """Observes each provider call; prompts are kept by hash only."""

    def __init__(self):
        self.items = []

    def install(self):
        from rag_baseline.openrouter import OpenRouterClient

        original, tap = OpenRouterClient._post, self

        async def tapped(client, path, payload):
            entry = dict(purpose=purpose_of(path, payload), path=path)
            if path == "/chat/completions":
                payload = {**payload, "provider": PROVIDER_ROUTE}
            # Identity of what was asked, so equal prompts with different outputs can be
            # told apart from upstream differences (scope gate, retrieval, conversation).
            asked = payload.get("messages") or payload.get("input")
            entry["request_sha256"] = _sha(
                json.dumps(asked, ensure_ascii=False, sort_keys=True)
            )
            started = time.perf_counter()
            try:
                response = await original(client, path, payload)
                entry.update(
                    usage=response.get("usage"), provider=response.get("provider")
                )
                entry.update(_response_identity(path, response))
                return response
            except Exception as exc:
                # The client's messages carry only the HTTP status, never credentials.
                entry["error"] = f"{type(exc).__name__}: {exc}"[:120]
                raise
            finally:
                entry["latency_ms"] = (time.perf_counter() - started) * 1000
                tap.items.append(entry)

        OpenRouterClient._post = tapped
        return original


def _response_identity(path, response):
    """Hash of the output; embeddings rounded so float formatting does not count as change."""
    try:
        if path == "/embeddings":
            vector = [round(v, 6) for v in response["data"][0]["embedding"]]
            return dict(response_sha256=_sha(json.dumps(vector)))
        content = response["choices"][0]["message"]["content"]
        return dict(response_sha256=_sha(content), response_text=content[:4000])
    except (KeyError, IndexError, TypeError):
        return dict(response_sha256=None)


async def one_turn(graph, message, *, user_id, thread_id):
    from langchain_core.messages import HumanMessage
    from langchain_core.runnables import RunnableConfig

    from service.normative_transport import (
        conversation_identity,
        project_integrated_state,
    )

    identity = conversation_identity(user_id, AGENT_ID, thread_id)
    config = RunnableConfig(
        configurable=dict(
            thread_id=identity.storage_key(),
            model=None,
            user_id=user_id,
            agent_id=AGENT_ID,
        ),
        run_id=uuid.uuid4(),
    )
    state = await graph.ainvoke(
        {
            "messages": [HumanMessage(content=message)],
            "conversation_identity": identity,
        },
        config=config,
    )
    projected = project_integrated_state(state)
    result = state.get("normative_result")
    return dict(
        action=str(state.get("action")),
        final_text=projected.content,
        normative_result=_plain(result),
        internal_audit=_plain(getattr(result, "internal_audit", None))
        if result
        else None,
    )


async def run_one(qid, messages, condition, *, tap, workdir, identity, repeat=0):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    from rag_baseline.integrated_runtime import build_integrated_agent_runtime

    run_id, user_id, thread_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    traces, turns, error = [], [], None
    tap.items.clear()
    started = time.perf_counter()
    database = Path(workdir) / f"{run_id}.sqlite"
    try:  # setup failures are recorded for this run as well; nothing is retried
        settings = settings_for(condition.top_k)
        prepare_environment(settings)
        async with AsyncSqliteSaver.from_conn_string(str(database)) as saver:
            manager = build_integrated_agent_runtime(saver, settings=settings)
            built = await manager.__aenter__()
            try:
                if built.service.top_k != condition.top_k:
                    raise RuntimeError("top_k was not applied")
                built.facade._adaptive = condition.with_sink(traces.append)
                # Frozen conversation: every user turn is input data defined before the run.
                # No reply is generated from scoring data; a clarification is an outcome.
                for message in messages:
                    turns.append(
                        await one_turn(
                            built.graph, message, user_id=user_id, thread_id=thread_id
                        )
                    )
            finally:
                await manager.__aexit__(None, None, None)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
    database.unlink(missing_ok=True)
    return dict(
        experiment_id="adaptive_rag_2026-11-09",
        run_id=run_id,
        query_id=qid,
        configuration_id=condition.name,
        repeat=repeat,
        question_sha256=_sha(messages[-1]),
        **identity,
        turns=turns,
        user_turns=messages,
        adaptive_trace=traces[-1] if traces else None,
        provider_calls=list(tap.items),
        latency_seconds=time.perf_counter() - started,
        error=error,
        executed=error is None and bool(turns),
    )


class _PlainCondition:
    """Condition for code trees without the experimental modules (pure baseline)."""

    def __init__(self, name):
        self.name, self.top_k = name, 5

    def with_sink(self, sink):
        return None  # the baseline facade ignores the attribute when it is None


def _conditions():
    try:
        from rag_baseline.adaptive_contracts import CONDITIONS
    except ImportError:
        # Baseline and baseline-fix trees: only the unmodified pipeline exists. The
        # label (A, A1...) only names the code tree the run used.
        return _FallbackConditions()
    return CONDITIONS


class _FallbackConditions(dict):
    def __missing__(self, name):
        return _PlainCondition(name)


async def main(args):
    from rag_baseline.openrouter import OpenRouterClient

    CONDITIONS = _conditions()

    from .budget import Budget, Ledger, installed_budget

    output = args.output.resolve()
    if REPO in output.parents:
        raise SystemExit("results must stay outside the repository")
    prepare_environment(settings_for(5))
    output.mkdir(parents=True, exist_ok=False)
    workdir = output / "_state"
    workdir.mkdir()
    inputs, keys, manifest = load(REPO, DATA_DIR)
    division = split(keys)
    chosen = division[args.split][: args.limit] if args.limit else division[args.split]
    by_id = {i.qid: i for i in inputs}
    names = args.conditions.split(",")
    histories_raw = args.history.read_bytes() if args.history else b"{}"
    histories = json.loads(histories_raw)
    # Each case is a list of user turns fixed before the run.
    if args.conversations:
        conversations_raw = args.conversations.read_bytes()
        cases = {c["id"]: c["turns"] for c in json.loads(conversations_raw)["cases"]}
        chosen = list(cases)[: args.limit] if args.limit else list(cases)
        histories_raw += conversations_raw
    else:
        cases = {q: [*histories.get(q, []), by_id[q].question] for q in chosen}
    identity = dict(
        **code_identity(),
        corpus_version=corpus_identity(),
        model_id=FROZEN["LLM_MODEL"],
        embedding_model=FROZEN["EMBEDDING_MODEL"],
        provider_route=PROVIDER_ROUTE,
        history_sha256=_sha(histories_raw),
    )
    done = set()
    if args.resume_from:
        previous = json.loads(
            (args.resume_from.parent / "plan.json").read_text(encoding="utf-8")
        )
        if (
            previous["identity"] != identity
            or previous["evaluated"] != args.split
            or previous["manifest"] != manifest
        ):
            raise SystemExit("cannot resume: code, corpus, model or split differ")
        for line in args.resume_from.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            # Executed pairs and recorded failures are kept; failures are never retried.
            if row.get("executed") or row.get("error"):
                done.add(
                    (row["query_id"], row["configuration_id"], row.get("repeat", 0))
                )
    # Repetitions are interleaved (all cases of repeat 0, then 1...) and the condition
    # order rotates per case and per repeat, so drift in the provider is not confounded.
    plan = [
        (qid, name, repeat)
        for repeat in range(args.repeats)
        for index, qid in enumerate(chosen)
        for name in names[(index + repeat) % len(names) :]
        + names[: (index + repeat) % len(names)]
        if (qid, name, repeat) not in done
    ]
    (output / "plan.json").write_text(
        json.dumps(
            dict(
                split=division,
                evaluated=args.split,
                evidence_class="E2_exploratory",
                order=plan,
                resumed_from=str(args.resume_from) if args.resume_from else None,
                usd_limit=args.usd,
                identity=identity,
                manifest=manifest,
                histories=histories,
            ),
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    budget, ledger, tap = (
        Budget(8 * len(plan), 6 * len(plan), args.usd, 800),
        Ledger(),
        Tap(),
    )
    original = tap.install()
    results = output / "RUNS.jsonl"
    try:
        with installed_budget(budget, ledger):
            for qid, name, repeat in plan:
                if budget.budget_stopped:
                    row = dict(
                        query_id=qid,
                        configuration_id=name,
                        repeat=repeat,
                        executed=False,
                        not_run_reason=f"budget:{budget.stop_reason}",
                    )
                else:
                    ledger.tagged(qid=qid, config=name, repeat=repeat)
                    row = await run_one(
                        qid,
                        cases[qid],
                        CONDITIONS[name],
                        tap=tap,
                        workdir=workdir,
                        identity=identity,
                        repeat=repeat,
                    )
                with results.open("a", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(row, ensure_ascii=False, default=str) + "\n"
                    )
                print(
                    qid,
                    name,
                    repeat,
                    row.get("executed"),
                    round(budget.cost_usd, 5),
                    flush=True,
                )
    finally:
        OpenRouterClient._post = original
    (output / "budget.json").write_text(
        json.dumps(
            dict(budget=budget.snapshot(), ledger=ledger.calls), indent=1, default=str
        ),
        encoding="utf-8",
    )
    workdir.rmdir()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--split", choices=("DEV", "TEST"), required=True)
    parser.add_argument("--usd", type=float, required=True)
    parser.add_argument("--conditions", default="A,B,C,D,E,K10,S")
    parser.add_argument(
        "--history", type=Path, help="frozen prior turns per query id (JSON)"
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--conversations",
        type=Path,
        help="multi-turn cases {cases: [{id, turns, ...}]} replacing the split questions",
    )
    parser.add_argument("--resume-from", type=Path)
    asyncio.run(main(parser.parse_args()))
