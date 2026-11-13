"""Provider accounting at `OpenRouterClient._post`, reusing the exploratory `Budget`.

Every request is reserved (worst case) before it is sent; the round stops once the
ceiling would be exceeded. There are no retries anywhere in this experiment.
"""

import asyncio
import contextlib
import functools
import time
from decimal import Decimal

from evaluation.exploratory.service_observer import Budget, BudgetStop

MAX_PROVIDER_FAILURES = 5

__all__ = ["Budget", "BudgetStop", "Ledger", "installed_budget"]


class Ledger:
    def __init__(self):
        self.calls = []
        self.context = {}

    def tagged(self, **tags):
        self.context = dict(tags)


@contextlib.contextmanager
def installed_budget(budget, ledger):
    from rag_baseline.openrouter import OpenRouterClient, OpenRouterError

    original, lock = OpenRouterClient._post, asyncio.Lock()

    @functools.wraps(original)
    async def limited(self, path, payload):
        async with lock:
            started, response, error = time.perf_counter(), None, None
            try:
                budget.before(path, payload)
                response = await original(self, path, payload)
                budget.after(response, path)
                return response
            except BudgetStop as exc:
                error = "budget_stopped:" + str(exc)
                raise OpenRouterError("Experiment budget stopped: " + str(exc)) from exc
            except Exception as exc:
                # The cost of a failed request is unknown: charge its full reservation as an
                # estimate and continue; a systemic failure still stops the round.
                error = type(exc).__name__
                reserved = (budget.last_reservation or {}).get("reserved_usd") or 0.0
                # after() rebuilds estimated_cost_usd from the exact string; update both.
                budget.estimated_cost_exact_usd = str(
                    Decimal(budget.estimated_cost_exact_usd) + Decimal(str(reserved))
                )
                budget.estimated_cost_usd = float(budget.estimated_cost_exact_usd)
                budget.provider_failures = getattr(budget, "provider_failures", 0) + 1
                if budget.provider_failures > MAX_PROVIDER_FAILURES:
                    budget.cost_reliable = False
                    budget.budget_stopped = True
                    budget.stop_reason = "repeated_provider_failures"
                raise
            finally:
                usage = (
                    (response or {}).get("usage")
                    if isinstance(response, dict)
                    else None
                )
                ledger.calls.append(
                    dict(
                        **ledger.context,
                        path=path,
                        model=payload.get("model"),
                        temperature=payload.get("temperature"),
                        max_tokens=payload.get("max_tokens"),
                        latency_ms=(time.perf_counter() - started) * 1000,
                        usage=usage,
                        provider=(response or {}).get("provider")
                        if isinstance(response, dict)
                        else None,
                        reserved_usd=(budget.last_reservation or {}).get(
                            "reserved_usd"
                        ),
                        accounted_cost_usd=budget.last_cost_usd,
                        cost_estimated=budget.last_cost_estimated,
                        cumulative_observed_usd=budget.cost_usd,
                        cumulative_estimated_usd=budget.estimated_cost_usd,
                        error=error,
                    )
                )

    OpenRouterClient._post = limited
    try:
        yield
    finally:
        OpenRouterClient._post = original
