"""Frozen public rates and reproducible request-specific reservations; no network IO."""

import copy
import json
from decimal import Decimal

CHAT_MODEL = "qwen/qwen3-30b-a3b-instruct-2507"
EMBEDDING_MODEL = "openai/text-embedding-3-small"
PRICING = {
    "verified_at_utc": "2026-11-04T02:19:02Z",
    "safety_factor": 2,
    "models": {
        CHAT_MODEL: {
            "kind": "chat",
            "prompt_usd_per_token": "0.0000001",
            "completion_usd_per_token": "0.0000003",
            "source": "https://openrouter.ai/qwen/qwen3-30b-a3b-instruct-2507",
            "observed_table": "Nebius Token Factory: USD 0.10 input / 0.30 output per million; other listed input rates USD 0.09",
        },
        EMBEDDING_MODEL: {
            "kind": "embedding",
            "prompt_usd_per_token": "0.00000002",
            "source": "https://openrouter.ai/openai/text-embedding-3-small",
            "observed_table": "USD 0.02 per million input tokens",
        },
    },
    "guarantee": "Reservation bounds cost under the frozen tariffs, the stated byte/token bound and factor 2. A real provider may charge differently; an excess is detected after the response and stops further calls.",
}


def pricing_snapshot(max_tokens=800):
    if type(max_tokens) is not int or max_tokens < 1:
        raise ValueError("Round max_tokens must be a positive integer")
    return {
        **copy.deepcopy(PRICING),
        "default_max_tokens": max_tokens,
        "chat_formula": "2 * (message_utf8_bytes * prompt_rate + max_tokens * completion_rate)",
        "embedding_formula": "2 * input_utf8_bytes * prompt_rate",
    }


def utf8_size(value):
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def request_reservation(path, payload, max_tokens=800):
    model = payload.get("model")
    rate = PRICING["models"].get(model)
    kind = {"/chat/completions": "chat", "/embeddings": "embedding"}.get(path)
    if rate is None or rate["kind"] != kind:
        raise ValueError("unpriced_model")
    if kind == "chat":
        messages = payload.get("messages")
        if not isinstance(messages, list) or any(
            not isinstance(m, dict) for m in messages
        ):
            raise ValueError("invalid_messages")
        size = sum(utf8_size(m.get("content", "")) for m in messages)
        maximum = payload.get("max_tokens", max_tokens)
        if type(maximum) is not int or maximum < 1:
            raise ValueError("invalid_max_tokens")
        amount = 2 * (
            Decimal(size) * Decimal(rate["prompt_usd_per_token"])
            + Decimal(maximum) * Decimal(rate["completion_usd_per_token"])
        )
        source = "payload" if "max_tokens" in payload else "round_default"
    else:
        inputs = payload.get("input")
        if not isinstance(inputs, str | list):
            raise ValueError("invalid_embedding_input")
        size = (
            sum(utf8_size(x) for x in inputs)
            if isinstance(inputs, list)
            else utf8_size(inputs)
        )
        maximum, source = None, None
        amount = 2 * Decimal(size) * Decimal(rate["prompt_usd_per_token"])
    return dict(
        model=model,
        path=path,
        input_utf8_bytes=size,
        max_tokens=maximum,
        max_tokens_source=source,
        safety_factor=2,
        reserved_usd=float(amount),
        prompt_usd_per_token=rate["prompt_usd_per_token"],
        completion_usd_per_token=rate.get("completion_usd_per_token"),
    )
