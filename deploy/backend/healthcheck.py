"""Container healthcheck: the service answers, the integrated agent is ready (index loaded) and
the launcher reports the selected v3.4 configuration (including Jev with transition v2),
unless an unevaluated configuration
was explicitly allowed (PROTOTYPE_ALLOW_UNEVALUATED_CONFIG=true). Prints only status codes."""

import json
import os
import sys
import urllib.request

BASE = "http://127.0.0.1:8080"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=4) as response:
        return json.loads(response.read().decode("utf-8"))


try:
    health = get("/health")
    identity = get("/prototype/identity")
except Exception as exc:  # noqa: BLE001
    print(f"unhealthy: {type(exc).__name__}")
    sys.exit(1)

agent = health.get("integrated_agent") or {}
ok = (
    health.get("status") == "ok"
    and agent.get("ready") is True
    and (
        identity.get("evaluated_configuration") is True
        or os.getenv("PROTOTYPE_ALLOW_UNEVALUATED_CONFIG", "").lower() == "true"
    )
)
print(
    "healthy"
    if ok
    else f"unhealthy: ready={agent.get('ready')} reason={agent.get('reason_code')}"
)
sys.exit(0 if ok else 1)
