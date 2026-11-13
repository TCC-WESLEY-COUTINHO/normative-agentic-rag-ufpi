"""CLI for planning, offline characterization, sequential live execution and reports."""

import argparse
import csv
import hashlib
import json
import os
import subprocess
import time
from collections import Counter
from pathlib import Path
from uuid import uuid4

from . import __version__
from .catalog import SEED, build_plan, validate_plan
from .evaluate import (
    CATEGORY,
    DEFINITIONS,
    classify_response,
    cross_turn_findings,
    evaluate_turn,
    numeric,
    result,
    summarize,
)

TURN_FIELDS = "effective_question sector intention gate router temporal_intent strategy chunks version_filter raw_generation violations regeneration final_answer observed_final_answer references status core_status fallback_reason latency_ms tokens cost_usd correlation_id observed_correlation_id request_id response_request_id response_thread_id response_question conversation_action grounding output_audit generation_attempts error_code sse_ok".split()


def repository_root():
    return Path(__file__).resolve().parents[2]


def validate_output(path, root=None):
    root = Path(root or repository_root()).resolve()
    target = Path(path).expanduser().resolve()
    if target == root or target.is_relative_to(root):
        raise ValueError(
            "Output must be outside the repository, including evaluation/results"
        )
    # Also reject the main checkout when invoked from a linked worktree.
    try:
        common = subprocess.check_output(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        common = (root / common).resolve()
        main = common.parent if common.name == ".git" else None
        if main and (target == main or target.is_relative_to(main)):
            raise ValueError("Output must be outside all repository checkouts")
    except (OSError, subprocess.CalledProcessError):
        pass
    return target


def file_manifest(directory):
    directory = Path(directory)
    return {
        p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


def source_fingerprint(root):
    root = Path(root)
    paths = list(root.glob("evaluation/exploratory/*.py"))
    for package in ("agents", "core", "memory", "schema", "service", "rag_baseline"):
        paths.extend(root.glob("code/src/" + package + "/**/*.py"))
    registry = root / "data/normative_registry.json"
    if registry.is_file():
        paths.append(registry)
    manifest = {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(paths)
    }
    return dict(
        files=manifest,
        sha256=hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()
        ).hexdigest(),
    )


def imported_product_manifest():
    """Hash the actual imported package locations, independent of checkout layout."""
    import importlib

    manifest = {}
    for name in ("rag_baseline", "agents", "service", "schema", "core", "memory"):
        package = importlib.import_module(name)
        roots = list(getattr(package, "__path__", []))
        if not roots and getattr(package, "__file__", None):
            roots = [str(Path(package.__file__).parent)]
        for directory in roots:
            base = Path(directory)
            for path in sorted(base.rglob("*.py")):
                manifest[name + "/" + path.relative_to(base).as_posix()] = (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                )
    return manifest


def validate_preflight(configuration):
    from .service_observer import Budget

    budget = configuration.get("budget", {})
    Budget(
        budget.get("chat_limit", 0),
        budget.get("embedding_limit", 0),
        budget.get("usd_limit"),
        budget.get("max_tokens", 800),
    )
    manifest = configuration.get("product_manifest")
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError("Imported product manifest is empty")
    if any(
        not any(k.startswith(name + "/") for k in manifest)
        for name in ("rag_baseline", "agents", "service", "schema", "core", "memory")
    ):
        raise ValueError("Imported product manifest is incomplete")


def write_json(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def append_jsonl(path, value):
    with Path(path).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")


def read_jsonl(path):
    if not Path(path).exists():
        return []
    rows = []
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def git_version(root):
    def read(*args):
        try:
            return subprocess.check_output(
                ["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    status = read("status", "--porcelain")
    return dict(
        head=read("rev-parse", "HEAD"),
        branch=read("branch", "--show-current"),
        dirty=None if status is None else bool(status),
        state="unknown" if status is None else "known",
    )


def initialize(output, mode, max_tokens=800):
    from .pricing import pricing_snapshot

    output = validate_output(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "test_plan.json").exists() or (output / "runs.jsonl").exists():
        raise ValueError("Output already contains a plan/round; use a fresh directory")
    plan, cases = build_plan(repository_root())
    plan.update(
        executor_version=__version__,
        source=git_version(repository_root()),
        mode=mode,
        corpus=file_manifest(repository_root() / "evaluation/corpora"),
        source_fingerprint=source_fingerprint(repository_root()),
        pricing=pricing_snapshot(max_tokens),
    )
    write_json(output / "test_plan.json", plan)
    with (output / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for case in cases:
            stream.write(json.dumps(case, ensure_ascii=False) + "\n")
    return output, plan, cases


def empty_turn(case, run_id, reason=None):
    row = {k: None for k in TURN_FIELDS}
    row.update(
        run_id=run_id,
        case_id=case["case_id"],
        category=case["category"],
        seed=case["seed"],
        conversation_id=case["conversation_id"],
        turn=case["turn"],
        question=case["question"],
        duplicate_of=case.get("duplicate_of"),
        executed=False,
        not_run_reason=reason,
        unavailable_reason={k: "Not observed" for k in TURN_FIELDS},
    )
    return row


def parse_sse(lines):
    messages, data, done = [], [], False

    def dispatch():
        nonlocal done
        if not data:
            return
        payload = "\n".join(data)
        data.clear()
        if done:
            raise ValueError("SSE data after terminal event")
        if payload == "[DONE]":
            done = True
            return
        event = json.loads(payload)
        if not isinstance(event, dict):
            raise ValueError("Invalid SSE event")
        if event.get("type") == "error":
            raise ValueError("SSE error event")
        if event.get("type") == "message":
            message = event.get("content")
            if not isinstance(message, dict) or message.get("type") != "ai":
                raise ValueError("Unexpected authoritative message")
            typed = message.get("normative_result")
            if typed is not None:
                if not isinstance(typed, dict):
                    raise ValueError("Invalid normative transport")
                field = {
                    "ANSWER": "answer",
                    "CLARIFICATION": "clarification_question",
                    "ERROR": "safe_message",
                }.get(typed.get("status"))
                if (
                    field is None
                    or not isinstance(typed.get(field), str)
                    or typed[field] != message.get("content")
                ):
                    raise ValueError("Normative final content mismatch")
            derived = message.get("grounded_followup_result")
            if derived is not None and (
                not isinstance(derived, dict)
                or derived.get("content") != message.get("content")
            ):
                raise ValueError("Derived final content mismatch")
            messages.append(message)
        elif event.get("type") != "token":
            raise ValueError("Unknown SSE event")

    for line in lines:
        if line == "":
            dispatch()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
        elif line.startswith(":") or line.startswith(("event:", "id:", "retry:")):
            continue
        else:
            raise ValueError("Invalid SSE framing")
    dispatch()
    if (
        not done
        or len(messages) != 1
        or not isinstance(messages[0].get("content"), str)
    ):
        raise ValueError("SSE requires DONE and one authoritative final message")
    return messages[0]


def ui_body(question, thread, user):
    # StreamInput defaults used by client.astream(message, thread_id, user_id).
    from schema import StreamInput

    return StreamInput(message=question, thread_id=thread, user_id=user).model_dump(
        mode="json"
    )


def merge_observations(row, message, events):
    final = (
        message.get("normative_result") or message.get("grounded_followup_result") or {}
    )
    row.update(
        final_answer=message.get("content"),
        status=final.get("status", "DIRECT"),
        references=final.get("references"),
        sector=final.get("domain"),
        core_status=final.get("core_status"),
        strategy=final.get("retrieval_strategy"),
        correlation_id=final.get("correlation_id", final.get("source_correlation_id")),
        error_code=final.get("error_code", row.get("error_code")),
        temporal_status_text=final.get("temporal_status_text"),
    )
    matching = [e for e in events if e.get("request_id") == row["request_id"]]
    provider = []
    for event in matching:
        data, kind = event["data"], event["event"]
        # Echoed identity is evidence from the received request, never synthesized from expectations.
        if kind == "request":
            request = data["body"]
            row["response_question"] = request.get("message")
            if (
                event.get("case_id") != row["case_id"]
                or type(event.get("turn")) is not int
                or event["turn"] != row["turn"]
            ):
                row["response_request_id"] = "trace_identity_mismatch"
        if kind == "provider":
            provider.append(data)
        elif kind == "generation":
            audit = data.get("result", {}).get("output_audit") or {}
            row.update(
                effective_question=data.get("question"),
                chunks=data.get("chunks"),
                grounding=data.get("grounding"),
                output_audit=audit,
                raw_generation=audit.get("raw_answer"),
                violations=audit.get("guard_violations"),
                regeneration=audit.get("regenerated_answer"),
                generation_attempts=data.get("result", {}).get("generation_attempts"),
            )
        elif kind == "facade":
            observed = data.get("result", {})
            row.update(
                effective_question=row.get("effective_question")
                or data.get("question"),
                observed_correlation_id=observed.get("correlation_id"),
                internal_audit=observed.get("internal_audit"),
                clarification=data.get("clarification"),
            )
        elif kind == "router":
            row["router"] = data.get("result")
        elif kind == "core":
            core = data.get("result") or {}
            row.update(
                router=core.get("route") or row.get("router"),
                version_filter=core.get("version_filter") or row.get("version_filter"),
                routing_audit=core.get("routing"),
            )
        elif kind == "scope_gate":
            row["gate"] = (data.get("result") or {}).get("decision")
        elif kind == "temporal":
            row["temporal_intent"] = data.get("result")
        elif kind == "version_filter":
            value = data.get("result")
            row["version_filter"] = (
                value[1] if isinstance(value, list) and len(value) == 2 else value
            )
        elif kind == "graph":
            audit = data.get("audit") or {}
            row.update(
                conversation_action=audit.get("conversation_action"),
                intention=audit.get("action_reason_code"),
                graph_audit=audit,
                observed_final_answer=(data.get("final") or {}).get("content"),
            )
            row["gate"] = audit.get("scope_gate_decision") or row.get("gate")
            row["observed_correlation_id"] = audit.get("correlation_id") or row.get(
                "observed_correlation_id"
            )
    usages = [p.get("usage") for p in provider]
    if provider:
        row["tokens"] = {
            key: sum(u[key] for u in usages)
            if all(isinstance(u, dict) and type(u.get(key)) is int for u in usages)
            else None
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        }
        row["cost_usd"] = (
            sum(
                u["cost"]
                for u in usages
                if isinstance(u, dict) and numeric(u.get("cost"))
            )
            if all(
                (isinstance(u, dict) and numeric(u.get("cost")))
                or p.get("cost_estimated") is True
                for u, p in zip(usages, provider, strict=True)
            )
            else None
        )
    elif matching:
        row["tokens"], row["cost_usd"] = (
            dict(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            0.0,
        )
    from .service_observer import sanitize

    row["provider_calls"] = sanitize(provider)
    row["estimated_cost_usd"] = sum(
        p.get("accounted_cost_usd") or 0
        for p in provider
        if p.get("cost_estimated") is True
    )
    row["cost_estimated"] = any(p.get("cost_estimated") is True for p in provider)
    row["system_prompt_hashes"] = [
        m["content_hash"]
        for p in provider
        for m in p.get("parameters", {}).get("messages", [])
        if isinstance(m, dict)
        and m.get("role") in {"system", "developer"}
        and m.get("content_hash")
    ]
    if row.get("core_status") == "fallback":
        row["fallback_reason"] = (
            (row.get("output_audit") or {}).get("second_guard_violations")
            or (row.get("output_audit") or {}).get("regeneration_error")
            or "guard_fallback"
        )
    elif row.get("error_code"):
        row["fallback_reason"] = row["error_code"]
    row["unavailable_reason"] = {
        k: "Observer or contract did not expose this field"
        for k in TURN_FIELDS
        if row.get(k) is None
    }
    return row


def apply_budget_status(row, budget):
    """Stopping future requests does not invalidate a completed current turn."""
    if not budget.get("budget_stopped"):
        return None
    interrupted = budget.get("current_request_interrupted")
    if interrupted is True or (
        interrupted is None
        and (row.get("sse_ok") is not True or row.get("status") == "ERROR")
    ):
        row["harness_budget_stop"] = True
        row["error_code"] = "harness_budget_stop"
    return "harness_budget_stop:" + str(budget.get("stop_reason"))


def live(
    output,
    *,
    trace,
    base_url,
    timeout=120,
    image_id=None,
    candidate_head=None,
    max_tokens=800,
):
    if base_url.rstrip("/") != "http://127.0.0.1:18080":
        raise ValueError("Live endpoint must be the loopback observer at port 18080")
    trace = validate_output(trace)
    output, plan, cases = initialize(output, "live", max_tokens)
    run_id, stopped = str(uuid4()), None
    headers = {}
    if os.environ.get("EXPLORATORY_AUTH_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["EXPLORATORY_AUTH_TOKEN"]
    append_jsonl(
        output / "runs.jsonl",
        dict(
            run_id=run_id, event="started", mode="live", seed=SEED, version=__version__
        ),
    )
    try:
        import httpx

        with httpx.Client(
            base_url=base_url, timeout=timeout, headers=headers
        ) as client:
            try:
                response = client.get("/_exploratory/status")
                response.raise_for_status()
                configuration = response.json()
                validate_preflight(configuration)
                if configuration.get("pricing") != plan["pricing"]:
                    raise ValueError("Server and round frozen pricing differ")
                configuration["requested_image_id"] = image_id
                configuration["requested_candidate_head"] = candidate_head
                if (
                    configuration.get("protocol_version") != "1"
                    or configuration.get("temporary_state") is not True
                    or configuration.get("ready") is not True
                    or configuration.get("trace_name") != trace.name
                    or not trace.is_file()
                ):
                    raise ValueError("Observer/temporary state/trace handshake failed")
                if (
                    candidate_head
                    and configuration.get("candidate_head") != candidate_head
                ):
                    raise ValueError(
                        "Candidate HEAD differs from server identification"
                    )
                if image_id and configuration.get("image_id") != image_id:
                    raise ValueError("Image identification differs from server")
                budget = configuration["budget"]
                if (
                    budget.get("chat_requests")
                    or budget.get("embedding_requests")
                    or budget.get("budget_stopped")
                ):
                    raise ValueError(
                        "Service budget already used; a round requires a fresh process"
                    )
                append_jsonl(
                    output / "runs.jsonl",
                    dict(
                        run_id=run_id,
                        event="configuration",
                        configuration=configuration,
                    ),
                )
            except Exception as exc:
                stopped = "environment_preflight:" + type(exc).__name__
            threads = {c["conversation_id"]: str(uuid4()) for c in cases}
            user = str(uuid4())
            # Preserve logical names in the case catalog, map to unique real thread IDs for this run.
            append_jsonl(
                output / "runs.jsonl",
                dict(run_id=run_id, event="thread_map", thread_map=threads),
            )
            for case in cases:
                row = empty_turn(case, run_id, stopped)
                row["logical_conversation_id"] = case["conversation_id"]
                row["conversation_id"] = threads[case["conversation_id"]]
                request_id = str(uuid4())
                if stopped:
                    append_jsonl(output / "turns.jsonl", row)
                    continue
                started = time.perf_counter()
                row.update(executed=True, request_id=request_id, not_run_reason=None)
                try:
                    with client.stream(
                        "POST",
                        "/chatbot_ufpi_integrated_v1/stream",
                        json=ui_body(case["question"], row["conversation_id"], user),
                        headers={
                            "x-exploratory-case": case["case_id"],
                            "x-exploratory-turn": str(case["turn"]),
                            "x-exploratory-request": request_id,
                        },
                    ) as response:
                        response.raise_for_status()
                        if "text/event-stream" not in response.headers.get(
                            "content-type", ""
                        ):
                            raise ValueError("Expected SSE content type")
                        row.update(
                            response_request_id=response.headers.get(
                                "x-exploratory-request"
                            ),
                            response_thread_id=response.headers.get(
                                "x-exploratory-thread"
                            ),
                        )
                        message = parse_sse(response.iter_lines())
                    row["sse_ok"] = True
                    merge_observations(row, message, read_jsonl(trace))
                except Exception as exc:
                    row.update(
                        sse_ok=False,
                        error_code="TRANSPORT_ERROR",
                        transport_error=type(exc).__name__,
                        status="ERROR",
                    )
                    # Request errors are retained once; subsequent independent turns may resume.
                    merge_observations(row, {}, read_jsonl(trace))
                    row["status"] = "ERROR"
                row["latency_ms"] = (time.perf_counter() - started) * 1000
                try:
                    state = client.get("/_exploratory/status")
                    state.raise_for_status()
                    status = state.json()
                    if status["budget"]["budget_stopped"]:
                        stopped = apply_budget_status(row, status["budget"])
                    elif status.get("dropped_records"):
                        stopped = "observer_records_dropped"
                        row.update(cost_usd=None, tokens=None)
                        row["unavailable_reason"].update(
                            cost_usd="Observer dropped records",
                            tokens="Observer dropped records",
                        )
                    append_jsonl(
                        output / "runs.jsonl",
                        dict(
                            run_id=run_id,
                            event="budget",
                            case_id=case["case_id"],
                            budget=status["budget"],
                        ),
                    )
                except Exception as exc:
                    stopped = "observer_status_unavailable:" + type(exc).__name__
                row["unavailable_reason"] = {
                    k: v
                    for k, v in row.get("unavailable_reason", {}).items()
                    if row.get(k) is None
                }
                append_jsonl(output / "turns.jsonl", row)
    except Exception as exc:
        stopped = "environment:" + type(exc).__name__
        completed = {r["case_id"] for r in read_jsonl(output / "turns.jsonl")}
        for case in cases:
            if case["case_id"] not in completed:
                append_jsonl(output / "turns.jsonl", empty_turn(case, run_id, stopped))
        raise
    finally:
        append_jsonl(
            output / "runs.jsonl",
            dict(run_id=run_id, event="ended", stop_reason=stopped),
        )
        report(output)
    return output


def report(output):
    output = validate_output(output)
    plan = json.loads((output / "test_plan.json").read_text(encoding="utf-8"))
    cases = read_jsonl(output / "cases.jsonl")
    validate_plan(cases)
    observed = read_jsonl(output / "turns.jsonl")
    by_case = {}
    for row in observed:
        if row["case_id"] in by_case:
            raise ValueError(
                "Multiple executions for one case; selective reruns are not supported"
            )
        by_case[row["case_id"]] = row
    runs = read_jsonl(output / "runs.jsonl")
    threads = next(
        (r["thread_map"] for r in runs if r.get("event") == "thread_map"), {}
    )
    rows = []
    previous_turn = {}
    for case in cases:
        row = by_case.get(
            case["case_id"],
            empty_turn(case, None, "No execution record; interrupted or plan only"),
        )
        expected_case = {
            **case,
            "conversation_id": threads.get(
                case["conversation_id"], case["conversation_id"]
            ),
        }
        previous = previous_turn.get(row["conversation_id"], {})
        row["antecedent_available"] = (
            previous.get("executed") is True
            and previous.get("status") == "ANSWER"
            and previous.get("core_status") in {"accepted", "regenerated"}
            and bool(previous.get("references"))
            and not previous.get("harness_budget_stop")
        )
        if previous.get("harness_budget_stop") and case["expected"].get(
            "unequivocal_continuation"
        ):
            row.update(
                executed=False,
                harness_budget_stop=True,
                not_run_reason="harness_budget_stop: required antecedent unavailable",
            )
        row["checks"] = evaluate_turn(expected_case, row)
        previous_turn[row["conversation_id"]] = row
        rows.append(row)
    inconsistencies = cross_turn_findings(rows)
    for finding in inconsistencies:
        row = next(r for r in rows if r["case_id"] == finding["case_id"])
        row["checks"]["cross_turn_consistency"] = result("fail", finding)
    for row in rows:
        row["classification"] = classify_response(row)
    # Atomic replace keeps a complete turn table if reporting is interrupted.
    temporary = output / ".turns.tmp"
    with temporary.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(output / "turns.jsonl")
    metrics = summarize(rows)
    metrics["cross_turn_findings"] = inconsistencies
    budgets = [r["budget"] for r in runs if r.get("budget")]
    metrics["provider_budget"] = budgets[-1] if budgets else None
    probes = read_jsonl(output / "deterministic_probes.jsonl")
    metrics["deterministic_probes"] = dict(
        total=len(probes),
        **{
            v: sum(p.get("verdict") == v for p in probes)
            for v in ("pass", "fail", "unknown", "not_run")
        },
    )
    write_json(output / "metrics.json", metrics)
    incidence = {
        "first_generation_accepted",
        "regenerated_accepted",
        "fallback",
        "abstention",
        "infrastructure_error",
    }
    failures = []
    case_lookup = {c["case_id"]: c for c in cases}

    def failure_cause(row, name):
        exp = case_lookup[row["case_id"]]["expected"]
        if name == "generation_changed":
            return (
                "not_determined",
                "Raw generation differs from the composed final response; equality check does not establish a functional defect",
            )
        if (
            exp.get("unequivocal_continuation") is True
            and row.get("conversation_action") == "NORMATIVE_RAG"
            and name in {"continuity", "redundant_clarification", "expected_status"}
        ):
            return (
                "system_candidate",
                "Real conversation policy classified a predefined unequivocal continuation as an independent normative question",
            )
        if name == "task_completion" and row.get("status") == "ERROR":
            reason = (row.get("version_filter") or {}).get(
                "insufficient_reason"
            ) or row.get("error_code")
            return (
                "system_candidate",
                "No substantive completion; conservative core abstention/error: "
                + str(reason),
            )
        if row.get("evaluation_mode") == "deterministic" and name in {
            "expected_evidence",
            "reference",
            "expected_status",
            "routing",
            "clarification",
            "task_completion",
            "unsupported_claim",
        }:
            return (
                "harness",
                "Controlled provider/retrieval fixture mismatch; this offline result does not establish production answer or retrieval accuracy"
                if name != "unsupported_claim"
                else "Lexical heuristic compared application-composed temporal statements against chunk text; inspect structured grounding before treating as unsupported",
            )
        return (
            "system_candidate",
            "Observed contract mismatch; inspect the correlated turn and check detail",
        )

    for row in rows:
        for name, check in row["checks"].items():
            if name in {"first_generation_accepted", "regenerated_accepted"}:
                continue
            if (
                name in incidence
                and check["verdict"] != "pass"
                or name not in incidence
                and check["verdict"] != "fail"
            ):
                continue
            failures.append(
                dict(
                    case_id=row["case_id"],
                    conversation_id=row["conversation_id"],
                    turn=row["turn"],
                    category=CATEGORY[name],
                    check=name,
                    verdict=check["verdict"],
                    detail=json.dumps(check.get("detail"), ensure_ascii=False),
                    failure_origin=failure_cause(row, name)[0],
                    reason=failure_cause(row, name)[1],
                )
            )
    for probe in probes:
        if probe.get("verdict") != "fail":
            continue
        recorded = probe.get("turn") if isinstance(probe.get("turn"), dict) else {}
        name = probe.get("probe", "component")
        category = (
            "temporal"
            if "temporal" in name
            else "context_leak"
            if "namespace" in name
            else "transport"
            if "transport" in name or "SSE" in name
            else "routing"
            if "routing" in str(probe.get("dataset"))
            else "generation"
        )
        failures.append(
            dict(
                case_id="probe:"
                + str(probe.get("case_id", recorded.get("case_id", name))),
                conversation_id=recorded.get("conversation_id"),
                turn=recorded.get("turn"),
                category=category,
                check=name,
                verdict="fail",
                failure_origin=probe.get("failure_origin") or "not_determined",
                reason=probe["reason"],
                detail=json.dumps(
                    {
                        k: probe.get(k)
                        for k in (
                            "expected",
                            "observed",
                            "checks",
                            "observed_phases",
                            "retrieval_reached",
                            "expected_error",
                            "reason",
                            "failure_origin",
                            "failure_layers",
                        )
                    },
                    ensure_ascii=False,
                ),
            )
        )
    with (output / "failures.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "case_id",
                "conversation_id",
                "turn",
                "category",
                "check",
                "verdict",
                "detail",
                "failure_origin",
                "reason",
            ],
        )
        writer.writeheader()
        writer.writerows(failures)
    with (output / "coverage_matrix.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "category",
                "check",
                "planned",
                "pass",
                "fail",
                "unknown",
                "not_run",
            ],
        )
        writer.writeheader()
        for cat in sorted(plan["messages_by_category"]):
            group = [r for r in rows if r["category"] == cat]
            for name in DEFINITIONS:
                counts = Counter(r["checks"][name]["verdict"] for r in group)
                writer.writerow(
                    dict(
                        category=cat,
                        check=name,
                        planned=len(group),
                        **{
                            k: counts[k] for k in ("pass", "fail", "unknown", "not_run")
                        },
                    )
                )
    metrics["failure_causes"] = [
        dict(check=name, failure_origin=origin, count=count)
        for (name, origin), count in sorted(
            Counter((f["check"], f["failure_origin"]) for f in failures).items()
        )
    ]
    write_json(output / "metrics.json", metrics)
    executed = sum(r.get("executed") is True for r in rows)
    lines = [
        "# Exploratory battery",
        "",
        f"Executor {__version__}; source `{plan.get('source', {}).get('head')}`; mode `{plan.get('mode')}`; seed {SEED}.",
        "",
        f"Planned messages: {len(cases)}. Executed: {executed}. Not run: {len(cases) - executed}.",
        "",
        "Configuration and corpus hashes: test_plan.json and runs.jsonl. Dataset inventory, source hashes, labels and duplicate relationships: test_plan.json / cases.jsonl.",
        "",
        "## Coverage",
        "",
        "| Category | Messages |",
        "|---|---:|",
        *[
            f"| {cat} | {count} |"
            for cat, count in plan["messages_by_category"].items()
        ],
        "",
        "## Metrics",
        "",
        "Pass and fail alone form each denominator. Unknown and not_run are separate. Incidence metrics count occurrence as pass; generation_changed is diagnostic equality, not correctness.",
        "",
        "| Metric | Numerator | Denominator | Unknown | Not run |",
        "|---|---:|---:|---:|---:|",
    ]
    configuration = next(
        (r.get("configuration", {}) for r in runs if r.get("event") == "configuration"),
        {},
    )
    lines += [
        "",
        "Candidate image: "
        + str(configuration.get("image_id") or "unknown")
        + "; candidate HEAD: "
        + str(configuration.get("candidate_head") or "unknown")
        + "; imported product SHA-256: "
        + str(configuration.get("source_sha256") or "unknown")
        + ".",
    ]
    lines += [
        "",
        "Frozen round pricing: " + json.dumps(plan.get("pricing"), ensure_ascii=False),
    ]
    for name, metric in metrics["overall"].items():
        lines.append(
            f"| {name} | {metric.get('numerator')} | {metric.get('denominator')} | {metric.get('unknown', 0)} | {metric.get('not_run', 0)} |"
        )
    lines += ["", "## Datasets", "", "| Dataset | Items | Usage |", "|---|---:|---|"]
    lines += [
        f"| {d['dataset']} | {d['items']} | {d['use']} |" for d in plan["datasets"]
    ]
    not_run_reasons = Counter(
        r.get("not_run_reason") or "Not executed"
        for r in rows
        if r.get("executed") is not True
    )
    lines += [
        "",
        "## Finding causes",
        "",
        "| Check | Origin | Count |",
        "|---|---|---:|",
    ]
    lines += [
        f"| {r['check']} | {r['failure_origin']} | {r['count']} |"
        for r in metrics["failure_causes"]
    ]
    lines += [
        "",
        "Per-finding cause, expected/observed evidence and case IDs are preserved in failures.csv. Controlled fixture mismatches are descriptive; diagnostic raw/final differences are not accuracy findings.",
    ]
    lines += [
        "",
        "Execution omissions: " + json.dumps(not_run_reasons, ensure_ascii=False) + ".",
        "",
        "Observed provider budget: "
        + json.dumps(metrics["provider_budget"], ensure_ascii=False)
        + ".",
    ]
    lines += [
        "",
        "Latency p50/p95, costs per case, category metrics, independent-only descriptive subset and definitions: metrics.json.",
        "",
        "Offline component/operational probes: "
        + json.dumps(metrics["deterministic_probes"])
        + ". See deterministic_probes.jsonl when present.",
        "",
        "## Examples",
        "",
    ]
    for failure in failures[:12]:
        row = by_case.get(failure["case_id"], {})
        lines += [
            f"- {failure['case_id']} / {failure['check']}: {row.get('question') or failure['detail']}",
            f"  Final: {str(row.get('final_answer'))[:700]}",
        ]
    lines += [
        "",
        "## Limitations",
        "",
        "- The Streamlit interface itself is not driven. Live uses the actual HTTP/SSE API and UI request schema.",
        "- Candidate datasets overlap. duplicate_of rows are not independent evidence. Offline fake responses characterize contracts, not provider quality.",
        "- Lexical claims and temporal mismatches are candidates. Absence of a match does not certify grounding or legal correctness. Required facts remain unknown.",
        "- Cross-turn extraction compares deadlines, recipients, protocol and proof with excerpts and articles; it does not choose a legally correct procedure.",
        "- System instructions are hashed; private reasoning and credentials are excluded. Null means unavailable, not an absent pipeline stage.",
        "- Provider calls reserve twice the byte-bound prompt cost plus configured maximum completion cost under the frozen round tariffs, within a USD 1.00 cap. Real billing can differ; an excess is detected after the response and stops the round. Missing embedding cost uses its configured model's frozen token rate; chat without cost stops.",
        "- Startup and transport failures may prevent execution; not_run is never counted as pass. Observer record failures do not change application returns.",
        "",
        "## Recommendations",
        "",
        "Review failures.csv and correlated evidence before changing any policy or promoting candidate labels. Run the deterministic suite in the application environment before a controlled live round. Preserve the whole round; do not rerun selected cases.",
    ]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    reproduction = [
        "# Reproduction",
        "",
        "Use a fresh external output directory and the same source HEAD, corpus hashes, configuration and seed listed in test_plan.json. Replay complete conversations in order. Do not selectively rerun a recorded round.",
        "",
    ]
    seen = set()
    for failure in failures:
        key = (failure["conversation_id"], failure["check"])
        if key in seen:
            continue
        seen.add(key)
        if failure["case_id"].startswith("probe:"):
            reproduction += [
                f"## {failure['case_id']}: {failure['check']}",
                "",
                "Run the complete deterministic battery with a fresh external output directory; inspect the named probe in deterministic_probes.jsonl.",
                failure["detail"],
                "",
            ]
            continue
        history = [
            r
            for r in rows
            if r["conversation_id"] == failure["conversation_id"]
            and r["turn"] <= failure["turn"]
        ]
        reproduction += [
            f"## {failure['case_id']}: {failure['check']}",
            "",
            *[f"{i + 1}. {r['question']}" for i, r in enumerate(history)],
            "",
            f"Observed check: {failure['detail']}",
            "Expected: inspect the structured expected fields in cases.jsonl; compare the same turn, thread and correlation in turns.jsonl.",
            "",
        ]
    if not failures:
        reproduction += [
            "No automatically detected failure recorded. This does not imply all planned messages were executed or grounded."
        ]
    (output / "REPRODUCTION.md").write_text(
        "\n".join(reproduction) + "\n", encoding="utf-8"
    )
    return metrics


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for name in ("plan", "deterministic", "live", "report"):
        command = sub.add_parser(name)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--max-tokens", type=int, default=800)
        if name == "live":
            command.add_argument("--trace", type=Path, required=True)
            command.add_argument("--base-url", default="http://127.0.0.1:18080")
            command.add_argument("--timeout", type=float, default=120)
            command.add_argument("--image-id")
            command.add_argument("--candidate-head")
    args = parser.parse_args(argv)
    if args.mode == "report":
        report(args.output)
    elif args.mode == "live":
        live(
            args.output,
            trace=args.trace,
            base_url=args.base_url,
            timeout=args.timeout,
            image_id=args.image_id,
            candidate_head=args.candidate_head,
            max_tokens=args.max_tokens,
        )
    else:
        output, plan, cases = initialize(args.output, args.mode, args.max_tokens)
        error = None
        if args.mode == "deterministic":
            from .deterministic import run

            error = run(output, cases)
        else:
            (output / "runs.jsonl").touch(exist_ok=False)
        report(output)
        print(
            json.dumps(
                dict(
                    messages=plan["user_messages"],
                    categories=plan["messages_by_category"],
                    requests=plan["request_estimate"],
                ),
                ensure_ascii=False,
            )
        )
        if error:
            raise SystemExit("Deterministic environment failure: " + error)


if __name__ == "__main__":
    main()
