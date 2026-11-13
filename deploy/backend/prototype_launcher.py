"""Demo launcher of the A''-J v2 prototype. Lives outside the frozen code/src tree.

It changes no decision of the pipeline. It only:
1. resolves the interpreter configuration with the frozen loader (interpreter_config) and refuses
   to start unless it is Jev with transition policy v2, the evaluated configuration. Setting
   PROTOTYPE_ALLOW_UNEVALUATED_CONFIG=true accepts other configurations (for example a local
   OpenAI-compatible model without Jev); the identity then reports evaluated_configuration=false;
2. logs a non-sensitive identity of the running version (no keys, no URLs with credentials);
3. adds a read-only GET /prototype/identity to the existing FastAPI application;
4. serves that same application with uvicorn.
"""

import json
import logging
import os
import sys
from urllib.parse import urlsplit

import uvicorn

logger = logging.getLogger("prototype")

ARCHITECTURE = "A''-J v2"

# Configuration evaluated in the TCC II (stages 7, 8, 12 and 14). Any difference makes the running
# configuration "unevaluated", which the launcher only accepts when explicitly allowed.
EVALUATED = {
    "interpreter_mode": "jev",
    "transition_policy": "v2",
    "routing_mode": "intent_v1",
    "retrieval_top_k": 5,
    "llm_model": "qwen/qwen3-30b-a3b-instruct-2507",
    "router_model": None,
    "embedding_model": "openai/text-embedding-3-small",
    "llm_temperature": 0.0,
    "llm_max_tokens": 800,
    "llm_endpoint_host": "openrouter.ai",
}


def resolve_identity() -> dict:
    from rag_baseline.conversation_interpretation.transition_v2 import POLICY_VERSION
    from rag_baseline.integrated_runtime import (
        AGENT_ID,
        IntegratedRuntimeSettings,
        interpreter_config,
    )

    settings = IntegratedRuntimeSettings()
    config = interpreter_config(settings)
    endpoint = urlsplit(settings.OPENROUTER_BASE_URL)
    running = {
        "interpreter_mode": config.mode,
        "transition_policy": config.transition_policy,
        "routing_mode": settings.ROUTING_MODE,
        "retrieval_top_k": settings.RETRIEVAL_TOP_K,
        "llm_model": settings.LLM_MODEL,
        "router_model": settings.ROUTER_MODEL,
        "embedding_model": settings.EMBEDDING_MODEL,
        "llm_temperature": float(settings.LLM_TEMPERATURE),
        "llm_max_tokens": settings.LLM_MAX_TOKENS,
        "llm_endpoint_host": endpoint.hostname,
    }
    differences = sorted(k for k, v in EVALUATED.items() if running[k] != v)
    return {
        "architecture": ARCHITECTURE,
        "agent_id": AGENT_ID,
        "interpreter_mode": config.mode,
        "transition_policy": config.transition_policy,
        "policy_version": POLICY_VERSION if config.transition_policy == "v2" else None,
        "jev_model": config.jev_model,
        "jev_thresholds": {
            "choice": config.jev_choice_threshold,
            "noul": config.jev_noul_threshold,
        },
        "routing_mode": settings.ROUTING_MODE,
        "retrieval_top_k": settings.RETRIEVAL_TOP_K,
        "llm_model": settings.LLM_MODEL,
        "router_model": settings.ROUTER_MODEL,
        "embedding_model": settings.EMBEDDING_MODEL,
        "llm_temperature": float(settings.LLM_TEMPERATURE),
        "llm_max_tokens": settings.LLM_MAX_TOKENS,
        "git_tag": os.getenv("PROTOTYPE_GIT_TAG") or None,
        "git_commit": os.getenv("PROTOTYPE_GIT_COMMIT") or None,
        "frozen_backend_manifest": os.getenv("PROTOTYPE_BACKEND_MANIFEST_SHA256")
        or None,
        "llm_endpoint_host": endpoint.hostname,
        "evaluated_configuration": not differences,
        "differences_from_evaluated": differences,
        "provider_route_pinned": False,
        "notice": "Protótipo experimental de pesquisa (TCC II); não é serviço institucional da UFPI.",
    }


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    identity = resolve_identity()
    allow_other = os.getenv("PROTOTYPE_ALLOW_UNEVALUATED_CONFIG", "").lower() == "true"
    if not identity["evaluated_configuration"] and allow_other:
        logger.warning(
            "configuração NÃO avaliada no TCC; diferenças: %s",
            ", ".join(identity["differences_from_evaluated"]),
        )
    elif not identity["evaluated_configuration"]:
        logger.error(
            "configuração recusada; diferenças em relação à avaliada: %s. "
            "Use PROTOTYPE_ALLOW_UNEVALUATED_CONFIG=true (ex.: deploy/compose.openai-compatible.yaml).",
            ", ".join(identity["differences_from_evaluated"]),
        )
        return 2
    logger.info("prototype identity %s", json.dumps(identity, ensure_ascii=False))

    from core import settings
    from service import app

    @app.get("/prototype/identity")
    async def prototype_identity() -> dict:
        return identity

    uvicorn.run(app, host=settings.HOST, port=settings.PORT, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
