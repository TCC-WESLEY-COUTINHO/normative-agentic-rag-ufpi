"""Loopback service entry point with observational wrappers and provider budgets."""

import argparse
import asyncio
import contextvars
import dataclasses
import functools
import hashlib
import inspect
import json
import math
import os
import re
import shutil
import tempfile
import threading
import time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

CONTEXT = contextvars.ContextVar("exploratory_turn", default={})


class BudgetStop(RuntimeError):
    """Internal limit signal, mapped to the real provider error at the boundary."""


class Budget:
    def __init__(self, chat_limit, embedding_limit, usd_limit, max_tokens=800):
        if any(type(v) is not int or v < 0 for v in (chat_limit, embedding_limit)):
            raise ValueError("Request limits must be nonnegative integers")
        if (
            type(usd_limit) not in {int, float}
            or not math.isfinite(usd_limit)
            or usd_limit <= 0
            or usd_limit > 1
        ):
            raise ValueError("USD limit must be finite, positive and at most 1.00")
        self.chat_limit, self.embedding_limit, self.usd_limit = (
            chat_limit,
            embedding_limit,
            usd_limit,
        )
        self.chat_requests = self.embedding_requests = 0
        self.cost_usd = 0.0
        self.estimated_cost_usd = 0.0
        self.observed_cost_exact_usd = "0"
        self.estimated_cost_exact_usd = "0"
        self.last_cost_estimated = False
        self.last_cost_usd = None
        self.active_path = None
        self.reserved_usd = 0.0
        if type(max_tokens) is not int or max_tokens < 1:
            raise ValueError("Round max_tokens must be a positive integer")
        self.max_tokens = max_tokens
        self.active_model = None
        self.last_reservation = None
        self.current_request_interrupted = False
        self.budget_stopped = False
        self.cost_reliable = True
        self.stop_reason = None

    def stop(self, reason):
        self.budget_stopped, self.stop_reason = True, reason
        self.current_request_interrupted = True
        raise BudgetStop(reason)

    def before(self, path, payload):
        from .pricing import request_reservation

        self.current_request_interrupted = False
        self.last_reservation = None
        self.last_cost_estimated, self.last_cost_usd = False, None
        self.active_model, self.reserved_usd = None, 0.0
        if self.budget_stopped:
            self.stop(self.stop_reason)
        try:
            self.last_reservation = request_reservation(path, payload, self.max_tokens)
        except ValueError as exc:
            self.stop(str(exc))
        reserve = self.last_reservation["reserved_usd"]
        self.active_model = payload["model"]
        observed = max(
            Decimal(self.observed_cost_exact_usd), Decimal(str(self.cost_usd))
        )
        estimated = max(
            Decimal(self.estimated_cost_exact_usd),
            Decimal(str(self.estimated_cost_usd)),
        )
        if observed + estimated + Decimal(str(reserve)) > Decimal(str(self.usd_limit)):
            self.stop("reservation_exceeds_budget")
        self.active_path, self.reserved_usd = path, reserve
        self.last_cost_estimated, self.last_cost_usd = False, None
        if self.cost_usd + self.estimated_cost_usd >= self.usd_limit:
            self.stop("cost_limit")
        if path == "/embeddings":
            if self.embedding_requests >= self.embedding_limit:
                self.stop("embedding_request_limit")
            self.embedding_requests += 1
        elif path == "/chat/completions":
            if self.chat_requests >= self.chat_limit:
                self.stop("chat_request_limit")
            self.chat_requests += 1
        else:
            self.stop("unrecognized_provider_path")

    def after(self, response, path=None):
        path = path or self.active_path or "/chat/completions"
        usage = response.get("usage") if isinstance(response, dict) else None
        cost = usage.get("cost") if isinstance(usage, dict) else None
        estimated = False
        if cost is None and path == "/embeddings":
            tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
            if type(tokens) is not int or tokens < 0:
                self.cost_reliable = False
                self.stop("embedding_cost_and_tokens_missing")
            from .pricing import PRICING

            rate = PRICING["models"].get(self.active_model, {})
            if rate.get("kind") != "embedding":
                self.stop("unpriced_model")
            cost, estimated = (
                float(Decimal(tokens) * Decimal(rate["prompt_usd_per_token"])),
                True,
            )
        if type(cost) not in {int, float} or not math.isfinite(cost) or cost < 0:
            self.cost_reliable = False
            self.stop("missing_or_invalid_usage_cost")
        self.last_cost_estimated, self.last_cost_usd = estimated, cost
        if estimated:
            self.estimated_cost_exact_usd = str(
                Decimal(self.estimated_cost_exact_usd) + Decimal(str(cost))
            )
            self.estimated_cost_usd = float(self.estimated_cost_exact_usd)
        else:
            self.observed_cost_exact_usd = str(
                Decimal(self.observed_cost_exact_usd) + Decimal(str(cost))
            )
            self.cost_usd = float(self.observed_cost_exact_usd)
        reserve = (
            self.last_reservation["reserved_usd"] if self.last_reservation else 0.0
        )
        self.reserved_usd = 0.0
        if Decimal(str(cost)) > Decimal(str(reserve)):
            self.stop("response_exceeds_reservation")
        if self.cost_usd + self.estimated_cost_usd >= self.usd_limit:
            self.stop("cost_limit")
        if self.chat_requests >= self.chat_limit and self.chat_requests:
            self.budget_stopped, self.stop_reason = True, "chat_request_limit"
        if self.embedding_requests >= self.embedding_limit and self.embedding_requests:
            self.budget_stopped, self.stop_reason = True, "embedding_request_limit"

    def snapshot(self):
        return dict(vars(self))


def sanitize(value):
    """Serialize explicit diagnostics; never retain system instructions or reasoning."""
    if dataclasses.is_dataclass(value):
        value = dataclasses.asdict(value)
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        if value.get("role") in {"system", "developer", "user"}:
            if "content" not in value and "content_hash" in value:
                return {
                    k: value[k]
                    for k in ("role", "content_hash", "content_size")
                    if k in value
                }
            content = json.dumps(
                value.get("content"), ensure_ascii=False, sort_keys=True
            )
            return dict(
                role=value["role"],
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                content_size=len(content.encode()),
            )
        return {
            str(k): sanitize(v)
            for k, v in value.items()
            if not any(
                word in str(k).lower()
                for word in (
                    "authorization",
                    "api_key",
                    "secret",
                    "headers",
                    "reasoning",
                    "chain_of_thought",
                )
            )
            and str(k) not in {"system_prompt", "developer_prompt", "user_prompt"}
        }
    if isinstance(value, tuple | list):
        return [sanitize(v) for v in value]
    if value is None or type(value) in {str, int, float, bool}:
        return value
    return str(value)


class TraceWriter:
    def __init__(self, path):
        self.path, self.lock = Path(path), threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # A trace belongs to exactly one service process/round.
        with self.path.open("x", encoding="utf-8"):
            pass
        self.dropped_records = 0

    def record(self, event, data_factory):
        # Serialization, extraction and disk errors cannot change the application flow.
        try:
            data = data_factory() if callable(data_factory) else data_factory
            row = dict(
                event=event,
                time_ns=time.time_ns(),
                **CONTEXT.get(),
                data=sanitize(data),
            )
            encoded = json.dumps(row, ensure_ascii=False, allow_nan=False)
            with self.lock, self.path.open("a", encoding="utf-8") as stream:
                stream.write(encoded + "\n")
        except Exception:
            self.dropped_records += 1


def explicit_result(value):
    result = sanitize(value)
    if not isinstance(result, dict):
        result = {}
    # These model fields are intentionally excluded by the public serializers.
    for key in (
        "internal_audit",
        "output_audit",
        "generation_attempts",
        "response_kind",
    ):
        if hasattr(value, key):
            audit = getattr(value, key)
            if key == "internal_audit" and audit is not None:
                audit = {
                    name: getattr(audit, name) for name in type(audit).model_fields
                }
            result[key] = sanitize(audit)
    return result


def install_observers(writer, budget):
    from rag_baseline import agentic
    from rag_baseline.openrouter import OpenRouterClient, OpenRouterError
    from rag_baseline.router import NormativeRouter
    from rag_baseline.scope_gate import NormativeScopeGate
    from rag_baseline.service import RagService
    from rag_baseline.tool_facade import NormativeRagFacade
    from rag_baseline.versioning import VersionFilter

    original_post, lock = OpenRouterClient._post, asyncio.Lock()

    @functools.wraps(original_post)
    async def limited_post(self, path, payload):
        async with lock:
            started, response, error = time.perf_counter(), None, None
            provider_request_id, provider_called = str(uuid4()), False
            try:
                budget.before(path, payload)
                writer.record(
                    "provider_reservation",
                    lambda: dict(
                        provider_request_id=provider_request_id,
                        reservation=budget.last_reservation,
                        observed_cost_usd=budget.cost_usd,
                        estimated_cost_usd=budget.estimated_cost_usd,
                        usd_limit=budget.usd_limit,
                    ),
                )
                provider_called = True
                response = await original_post(self, path, payload)
                budget.after(response, path)
                return response
            except BudgetStop as exc:
                error = "budget_stopped"
                raise OpenRouterError(
                    "Exploratory provider budget stopped: " + str(exc)
                ) from exc
            except Exception as exc:
                error = type(exc).__name__
                # A failed HTTP call can still incur unreported cost. Stop conservatively.
                budget.cost_reliable = False
                budget.budget_stopped = True
                budget.stop_reason = "provider_failure_cost_unknown"
                raise
            finally:
                writer.record(
                    "provider",
                    lambda: dict(
                        provider_request_id=provider_request_id,
                        provider_called=provider_called,
                        path=path,
                        model=payload.get("model"),
                        parameters=payload,
                        latency_ms=(time.perf_counter() - started) * 1000,
                        response=response,
                        usage=response.get("usage") if response else None,
                        usage_cost_missing=not isinstance(
                            (response or {}).get("usage"), dict
                        )
                        or (response or {}).get("usage", {}).get("cost") is None,
                        error=error,
                        budget=budget.snapshot(),
                        cost_estimated=budget.last_cost_estimated,
                        accounted_cost_usd=budget.last_cost_usd,
                        reservation=budget.last_reservation,
                    ),
                )

    OpenRouterClient._post = limited_post

    def observe_async(cls, name, event, extract):
        native = getattr(cls, name)
        signature = inspect.signature(native)

        @functools.wraps(native)
        async def wrapper(*args, **kwargs):
            started = time.perf_counter()
            try:
                value = await native(*args, **kwargs)
            except Exception as exc:
                error_type = type(exc).__name__
                writer.record(
                    event,
                    lambda: dict(
                        error=error_type,
                        latency_ms=(time.perf_counter() - started) * 1000,
                    ),
                )
                raise
            writer.record(
                event,
                lambda: {
                    **extract(signature.bind(*args, **kwargs).arguments, value),
                    "latency_ms": (time.perf_counter() - started) * 1000,
                },
            )
            return value

        setattr(cls, name, wrapper)

    observe_async(
        RagService,
        "generate",
        "generation",
        lambda args, value: dict(
            question=args.get("question"),
            chunks=args.get("chunks"),
            grounding=args.get("temporal_grounding"),
            result=explicit_result(value),
        ),
    )
    observe_async(
        NormativeRagFacade,
        "query",
        "facade",
        lambda args, value: dict(
            question=args.get("question"),
            clarification=args.get("clarification"),
            result=explicit_result(value),
        ),
    )
    observe_async(
        NormativeRouter,
        "route",
        "router",
        lambda args, value: dict(
            question=args.get("question"),
            clarification=args.get("clarification"),
            result=value,
        ),
    )
    observe_async(
        NormativeScopeGate,
        "classify",
        "scope_gate",
        lambda args, value: dict(question=args.get("question"), result=value),
    )
    observe_async(
        agentic.AgenticRagService,
        "query",
        "core",
        lambda args, value: dict(
            question=args.get("question"), result=explicit_result(value)
        ),
    )

    native_filter = VersionFilter.apply

    @functools.wraps(native_filter)
    def apply_filter(*args, **kwargs):
        value = native_filter(*args, **kwargs)
        writer.record("version_filter", lambda: dict(result=value))
        return value

    VersionFilter.apply = apply_filter
    native_temporal = agentic.classify_temporal_intent

    @functools.wraps(native_temporal)
    def temporal(*args, **kwargs):
        value = native_temporal(*args, **kwargs)
        writer.record("temporal", lambda: dict(question=args[0], result=value))
        return value

    agentic.classify_temporal_intent = temporal


def observe_projection(service_module, writer):
    native = service_module.project_integrated_state

    @functools.wraps(native)
    def project(state):
        value = native(state)
        writer.record(
            "graph",
            lambda: dict(
                question=state.get("current_question"),
                audit=state.get("turn_audit"),
                result=explicit_result(state.get("normative_result")),
                final=value,
            ),
        )
        return value

    service_module.project_integrated_state = project


def safe_header(value):
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value)
        else None
    )


class CorrelationMiddleware:
    """Pure ASGI middleware: context remains active until the last SSE body is sent."""

    def __init__(self, app, writer, budget):
        self.app, self.writer, self.budget = app, writer, budget

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))

        def header(name):
            return safe_header(
                headers.get(name.encode(), b"").decode("ascii", "ignore")
            )

        request_id = header("x-exploratory-request") or str(uuid4())
        turn = header("x-exploratory-turn")
        metadata = dict(
            request_id=request_id,
            case_id=header("x-exploratory-case"),
            turn=int(turn) if turn and turn.isdecimal() else None,
        )
        token, body = CONTEXT.set(metadata), bytearray()
        started = time.perf_counter()

        async def receiving():
            message = await receive()
            if message["type"] == "http.request":
                body.extend(message.get("body", b""))
                if not message.get("more_body"):
                    try:
                        request = json.loads(body)
                        metadata.update(
                            conversation_id=request.get("thread_id"),
                            question=request.get("message"),
                            user_id=request.get("user_id"),
                        )
                        self.writer.record("request", lambda: dict(body=request))
                    except Exception:
                        pass
            return message

        async def sending(message):
            if message["type"] == "http.response.start":
                message = {
                    **message,
                    "headers": list(message.get("headers", []))
                    + [
                        (b"x-exploratory-request", request_id.encode()),
                        (
                            b"x-exploratory-thread",
                            (safe_header(metadata.get("conversation_id")) or "").encode(
                                "ascii"
                            ),
                        ),
                        (
                            b"x-exploratory-budget-stopped",
                            str(self.budget.budget_stopped).lower().encode(),
                        ),
                    ],
                }
            await send(message)

        try:
            await self.app(scope, receiving, sending)
        finally:
            self.writer.record(
                "request_end",
                lambda: dict(
                    latency_ms=(time.perf_counter() - started) * 1000,
                    budget=self.budget.snapshot(),
                ),
            )
            CONTEXT.reset(token)


def validate_runtime_paths(root, temporary_root, index, state, mounted_index):
    from .battery import validate_output

    temporary_root = validate_output(temporary_root, root)
    paths = [Path(p).resolve() for p in (index, state, mounted_index)]
    idx, db, mounted = paths
    if idx == mounted or idx.is_relative_to(mounted) or mounted.is_relative_to(idx):
        raise ValueError(
            "CHROMA_PERSIST_DIR must be a temporary copy, not the mounted index"
        )
    if not idx.is_relative_to(temporary_root) or not db.is_relative_to(temporary_root):
        raise ValueError("Index and SQLite state must be inside the temporary root")
    if idx == db or db.is_relative_to(idx):
        raise ValueError("SQLite state must be separate from the index")
    if not idx.is_dir() or not db.is_file():
        raise ValueError("Temporary index and SQLite copies must exist")
    if (
        idx.is_symlink()
        or db.is_symlink()
        or any(p.is_symlink() for p in idx.rglob("*"))
    ):
        raise ValueError("Temporary state cannot contain symlinks")
    # A mount located at the target index would defeat path-based isolation.
    mountinfo = Path("/proc/self/mountinfo")
    if mountinfo.exists():
        mounts = [
            line.split()[4].replace("\\040", " ")
            for line in mountinfo.read_text().splitlines()
        ]
        if any(idx == Path(p).resolve() for p in mounts):
            raise ValueError("Temporary index itself is a mount point")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--temporary-root", type=Path, required=True)
    parser.add_argument("--mounted-index", type=Path, required=True)
    parser.add_argument("--copy-state-from", type=Path, required=True)
    parser.add_argument("--max-chat", type=int, required=True)
    parser.add_argument("--max-embedding", type=int, required=True)
    parser.add_argument("--max-usd", type=float, required=True)
    parser.add_argument("--max-tokens", type=int, default=800)
    parser.add_argument("--image-id")
    parser.add_argument("--candidate-head")
    args = parser.parse_args(argv)
    from .battery import (
        file_manifest,
        repository_root,
        source_fingerprint,
        validate_output,
    )

    root = repository_root()
    temporary_root = validate_output(args.temporary_root, root)
    validate_output(args.trace, root)
    source_index = args.mounted_index.resolve()
    if temporary_root == source_index or temporary_root.is_relative_to(source_index):
        parser.error("Temporary root cannot be inside the mounted source index")
    if (
        args.trace.resolve() == source_index
        or args.trace.resolve().is_relative_to(source_index)
        or args.trace.resolve() == args.copy_state_from.resolve()
    ):
        parser.error("Trace cannot overwrite or be inside source state")
    if args.trace.exists():
        parser.error("Trace exists; use a fresh trace for a single round")
    temporary_root.mkdir(parents=True, exist_ok=True)
    # Copy before importing configuration/app; SQLite backup includes committed WAL data.
    import sqlite3

    with tempfile.TemporaryDirectory(prefix="exploratory-", dir=temporary_root) as work:
        index, state = Path(work) / "index", Path(work) / "state.sqlite"
        if not args.mounted_index.is_dir() or not args.copy_state_from.is_file():
            parser.error("Mounted index and source SQLite file must exist")
        if any(p.is_symlink() for p in args.mounted_index.rglob("*")):
            parser.error("Source index contains symlinks")
        shutil.copytree(args.mounted_index, index)
        source_uri = args.copy_state_from.resolve().as_uri() + "?mode=ro"
        with (
            sqlite3.connect(source_uri, uri=True) as source,
            sqlite3.connect(state) as target,
        ):
            source.backup(target)
        os.environ["CHROMA_PERSIST_DIR"], os.environ["SQLITE_DB_PATH"] = (
            str(index),
            str(state),
        )
        os.environ["DATABASE_TYPE"] = "sqlite"
        os.environ["LANGFUSE_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        os.environ["LANGSMITH_TRACING"] = "false"
        validate_runtime_paths(root, temporary_root, index, state, args.mounted_index)
        budget, writer = (
            Budget(args.max_chat, args.max_embedding, args.max_usd, args.max_tokens),
            TraceWriter(args.trace),
        )
        manifest = file_manifest(index)
        source_sha256 = source_fingerprint(root)["sha256"]
        install_observers(writer, budget)
        from service import service

        from .battery import git_version, imported_product_manifest

        product_manifest = imported_product_manifest()
        if not product_manifest:
            parser.error("Imported product manifest is empty")
        source_sha256 = hashlib.sha256(
            json.dumps(product_manifest, sort_keys=True).encode()
        ).hexdigest()

        if (
            str(service.settings.DATABASE_TYPE) != "sqlite"
            or Path(service.settings.SQLITE_DB_PATH).resolve() != state.resolve()
        ):
            parser.error(
                "Application state configuration does not point to the temporary SQLite copy"
            )
        from rag_baseline.config import BaselineSettings

        if Path(BaselineSettings().CHROMA_PERSIST_DIR).resolve() != index.resolve():
            parser.error(
                "Application index configuration does not point to the temporary copy"
            )
        observe_projection(service, writer)
        service.app.add_middleware(CorrelationMiddleware, writer=writer, budget=budget)

        @service.app.get("/_exploratory/status")
        async def status():
            from .pricing import pricing_snapshot

            return dict(
                protocol_version="1",
                budget=budget.snapshot(),
                corpus=manifest,
                temporary_state=True,
                trace_name=args.trace.name,
                source_sha256=source_sha256,
                product_manifest=product_manifest,
                source=git_version(root),
                image_id=args.image_id,
                candidate_head=args.candidate_head,
                pricing=pricing_snapshot(args.max_tokens),
                ready=service.get_agent_readiness("chatbot_ufpi_integrated_v1").get(
                    "ready"
                )
                is True,
                dropped_records=writer.dropped_records,
            )

        writer.record(
            "configuration",
            lambda: dict(
                budget=budget.snapshot(), corpus=manifest, temporary_state=True
            ),
        )
        import uvicorn

        uvicorn.run(service.app, host="127.0.0.1", port=18080, log_level="warning")


if __name__ == "__main__":
    main()
