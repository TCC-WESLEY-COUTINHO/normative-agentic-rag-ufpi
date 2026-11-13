"""Capture packaging/runtime audit and public implementation decisions."""

import ast
import importlib.metadata
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
BASE = "706bd7cc5e7f333032c7de7b58ed89dc41c09bd0"
PACKAGES = ["agents", "core", "memory", "schema", "service", "rag_baseline"]
ASSETS = [
    "data/normative_registry.json",
    "evaluation/corpora/graduacao_setor_v2.json",
    "evaluation/corpora/pos_graduacao_setor_v2.json",
    "evaluation/corpora/1056_2026_temporal_v1.json",
]


def write(name, value):
    (OUT / name).write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def legacy_descriptions():
    source = subprocess.check_output(
        ["git", "show", f"{BASE}:code/src/agents/agents.py"], cwd=ROOT
    ).decode()
    tree = ast.parse(source)
    node = next(
        n
        for n in tree.body
        if isinstance(n, ast.AnnAssign)
        and isinstance(n.target, ast.Name)
        and n.target.id == "agents"
    )
    return {
        key.value: next(k.value.value for k in value.keywords if k.arg == "description")
        for key, value in zip(node.value.keys, node.value.values, strict=True)
    }


if __name__ == "__main__":
    declarations = [f"COPY code/src/{p}/ ./src/{p}/" for p in PACKAGES]
    declarations += ["COPY code/src/run_service.py ./src/run_service.py"]
    declarations += [f"COPY {asset} /app/{asset}" for asset in ASSETS]
    dockerfile = (ROOT / "code/docker/Dockerfile.service").read_text(encoding="utf-8")
    assert all(line in dockerfile for line in declarations)
    write(
        "packaging_audit.json",
        dict(
            declarations=declarations,
            completeness=[len(declarations), len(declarations)],
            assets=ASSETS,
            packages=PACKAGES,
            build_context="repository_root",
            index="Persistent bind mount; existing nonempty collection only; not in image",
            docker_cli=shutil.which("docker"),
            docker_build="not_run: docker_cli_not_found"
            if not shutil.which("docker")
            else "requires_build",
            container_smoke="not_run: docker_cli_not_found"
            if not shutil.which("docker")
            else "requires_build",
            python_executed=sys.version,
            python_container="3.12.3",
            langgraph_python="3.12",
            dependency_versions={
                p: importlib.metadata.version(p)
                for p in [
                    "chromadb",
                    "langgraph",
                    "pydantic",
                    "httpx",
                    "langgraph-checkpoint-sqlite",
                ]
            },
            pyproject_and_lock_unchanged=True,
        ),
    )
    write(
        "runtime_audit.json",
        dict(
            source_head=BASE,
            source_branch="feat/calculator-tool-routing-v1",
            initial_status="clean",
            default_agent="chatbot_ufpi_v2",
            legacy_agents=legacy_descriptions(),
            before="Eager imports of unused agents and supervisor model; four registry entries; service injects saver/store into ready graphs; Docker lacks rag_baseline/assets",
            entrypoint="code/src/run_service.py -> uvicorn service:app -> lifespan -> existing memory factories -> registry initialization",
            default_memory_backend_code="sqlite",
            compose_prod_backend="postgres",
            live_backends_tested=["sqlite"],
            after="Import-safe registration; explicit context-managed integrated assembly in normal lifespan; stable non-default ID",
            runtime_settings="Existing duas-regulacoes profile and BaselineSettings; registry override optional; paths anchored at code/",
            lifecycle_ownership={
                "saver_store": "Existing application lifespan/factories; integrated runtime borrows saver",
                "chroma": "Runtime-owned lease or external-owner borrowed system; last owned lease stops; partial acquisition cleaned",
                "provider": "Runtime calls optional aclose; existing OpenRouter per-request HTTP context owns client",
                "transformer": "No presentation provider; deterministic fallback; no resource to close",
                "postgres_mongo": "Existing factory context managers, not live validated",
            },
            failure_policy="Expected experimental asset/config failure -> unavailable, legacy survives; database/store or unexpected errors -> startup fails",
            provider_boundary="Request model/config does not override scientific internal models",
            langgraph_decision="Unchanged separate research-assistant entrypoint; not service default",
        ),
    )
    decisions = [
        ("agent_id", "chatbot_ufpi_integrated_v1, único ID, experimental/non-default."),
        (
            "registry",
            "Extensão pequena de Agent: import_path lazy e runtime_factory com lifecycle; quatro IDs/descrições legados preservados.",
        ),
        (
            "imports",
            "Remover imports eager do registry, incluindo supervisor não registrado; graph/model/client não é construído no import novo.",
        ),
        (
            "factory",
            "Context manager explícito monta dependências existentes, sem lógica normativa nova ou Supabase.",
        ),
        (
            "resources",
            "Aplicação possui saver/store; runtime possui provider/leases Chroma. Uma ownership por recurso, cleanup por context managers.",
        ),
        (
            "chroma_close",
            "Chroma 1.0.x sem Client.close público: adapter estreito de System/cache, refcount de leases, dono externo preservado e cleanup de start parcial.",
        ),
        (
            "memory_backend",
            "SQLite default do código mantido. Postgres/Mongo factories intactas, sem alegação de validação ao vivo.",
        ),
        (
            "provider",
            "Reusar OpenRouter/BaselineSettings, modelos/top_k/temperatura existentes. Campo model legado do request não troca modelos internos.",
        ),
        (
            "transformer",
            "Fallback determinístico para source answer, sem provider de apresentação obrigatório.",
        ),
        (
            "stamp",
            "Validar registry/evidências e computar fingerprints uma vez por build; sem embeddings/retrieval de pergunta.",
        ),
        (
            "index",
            "Exigir diretório/database/collection existente e não vazia; get_collection apenas. 507 é snapshot científico local, não constante de saúde.",
        ),
        (
            "readiness",
            "Separar liveness e readiness, provider configured não é conectado. Health local sem HTTP; Langfuse informa configuração.",
        ),
        (
            "availability",
            "Falhas esperadas de asset/config deixam somente integrado indisponível. 503 explícito, unknown 404, nenhum fallback de agente.",
        ),
        (
            "critical_startup",
            "Erros inesperados e falha do saver/store continuam falhando startup; não mascarar configuração crítica.",
        ),
        (
            "docker_assets",
            "Contexto raiz com allowlist; copiar seis pacotes, entrypoint e quatro assets documentais; excluir resultados/datasets/segredos/índice.",
        ),
        (
            "client_image",
            "Incluir contratos rag_baseline usados pelo schema e manter layout profundo. Streamlit fonte/intenção intactos.",
        ),
        (
            "paths",
            "Layout /app/code/src + /app/data + corpora; paths relativos do runtime ancorados em code/. SQLite conserva factory; usar absoluto fora de code/.",
        ),
        (
            "index_mount",
            "Bind persistente code/.local/chroma -> /app/index; Chroma requer housekeeping local; não reindexar ou embutir índice.",
        ),
        (
            "langgraph",
            "langgraph.json permanece com research_assistant, separado do registry da API.",
        ),
        (
            "python_dependencies",
            "Manter imagens Python3.12.3, LangGraph3.12, pyproject/lock; executar local3.11.15 sem instalar/atualizar libs.",
        ),
        (
            "legacy_test_transition",
            "Atualizar somente assert obsoleto de ausência no registry para presença experimental/default preservado; restantes contratos tipados mantidos.",
        ),
        (
            "scope",
            "Uma lifespan de aplicação por processo. Sem UI, deploy, auth, tuning, reindex ou novo experimento científico.",
        ),
    ]
    now = datetime.now(UTC).isoformat()
    (OUT / "decision_log.jsonl").write_bytes(
        b"".join(
            (
                json.dumps(dict(id=i, recorded_at=now, topic=t, decision=d), ensure_ascii=False)
                + "\n"
            ).encode()
            for i, (t, d) in enumerate(decisions, 1)
        )
    )
    print("Prepared", len(declarations), "packaging entries and", len(decisions), "decisions")
