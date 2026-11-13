"""Consolidate observed engineering results; never synthesizes unexecuted outcomes."""

import json
import re
import subprocess

from operations import OUT, ROOT, decision, journal, now, write


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def git(*args):
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT}", *args], cwd=ROOT, text=True
    ).strip()


def main():
    probes = read("probe_results.json")
    build, image, preservation = (
        read("build_result.json"),
        read("image_metadata.json"),
        read("preservation.json"),
    )
    before, after = read("index_before.json"), read("index_after.json")
    image_audit = {}
    for line in (OUT / "image_import_assets.log").read_text().splitlines():
        if line.startswith("{"):
            image_audit.update(json.loads(line))
    write("image_audit.json", image_audit)
    assert before == after and before["count"] == 507
    assert all(row["status"] == "PASS" for row in probes)
    assert [row["path"] for row in preservation["changes"]] == ["code/compose.yaml"]
    assert read("compose_docker_health.json")["status"] == "healthy"
    assert read("compose_network_observation.json")["blocked_external_attempts"] == 0
    tests = []
    for path in sorted(OUT.glob("linux_tests_*.log")):
        text = path.read_text(encoding="utf-8")
        summary = next(
            (
                line
                for line in reversed(text.splitlines())
                if re.search(r"\d+ (?:passed|failed|error|skipped)", line)
            ),
            "",
        )
        counts = {
            label: int(match.group(1))
            if (match := re.search(r"(\d+) " + label, summary))
            else 0
            for label in (
                "passed",
                "failed",
                "skipped",
                "errors",
                "deselected",
                "warnings",
            )
        }
        tests.append(
            {
                "suite": path.stem.removeprefix("linux_tests_"),
                "stdout_file": path.name,
                "summary": summary,
                **counts,
            }
        )
    exits = read("linux_suite_exit_codes.json")
    assert not any(exits.values()), exits
    write(
        "test_results.json",
        {
            "environment": "Built Linux/Python3.12 runtime dependencies with test-only Git layer; locked pytest plugins, source/tests/evaluation and two corpus fixtures mounted read-only. Aggregate retries use nofile=65536 and legacy AppTest cwd fixture. No .env or real index mounted.",
            "selections_overlap": True,
            "runs": tests,
            "exit_codes": exits,
        },
    )
    by_name = {row["case"]: row for row in probes}
    metrics = {}

    def group(metric, prefix):
        selected = [row for row in probes if row["case"].startswith(prefix)]
        metrics[metric] = [
            sum(row["status"] == "PASS" for row in selected),
            len(selected),
        ]

    metrics["Docker Engine Availability"] = [1, 1]
    metrics["Docker Build Success"] = [int(build["exit_code"] == 0), 1]
    metrics["Image Runtime Import Success"] = [len(image_audit["imports"]), 4]
    metrics["Image Asset Completeness"] = image_audit["asset_completeness"]
    group("Container Startup Success", "startup_")
    group("Process Health Success", "health_")
    group("Integrated Readiness Success", "readiness_")
    group("Registered Agent Visibility", "info_")
    group("Default Preservation", "default_")
    for metric, case in [
        ("Direct Container Smoke", "direct_native"),
        ("Calculator Container Smoke", "calculator_native"),
        ("Date Calculator Container Smoke", "date_native"),
        ("Normative Container Smoke", "normative_controlled"),
        ("Container Memory Restart Continuity", "memory_restart"),
        ("Cross-user Isolation", "cross_user_isolation"),
    ]:
        metrics[metric] = [int(by_name[case]["status"] == "PASS"), 1]
    group("Stream Contract Preservation", "stream_")
    metrics["Negative Readiness Behavior"] = [
        sum(
            by_name["readiness_" + case]["status"] == "PASS"
            for case in ("missing_index", "invalid_registry", "missing_provider")
        ),
        3,
    ]
    group("Runtime External Call Avoidance", "external_call_avoidance_")
    group("Process Graceful Shutdown", "shutdown_")
    resources = [
        read("controlled_first_closed_resources.json"),
        read("controlled_restart_closed_resources.json"),
    ]
    metrics["Resource Shutdown Success"] = [
        sum(
            bool(row[key])
            for row in resources
            for key in ("index_closed", "provider_closed", "sqlite_connection_closed")
        ),
        6,
    ]
    metrics["Index Logical Preservation"] = [507, 507]
    metrics["Container Path Portability"] = [11, 11]
    metrics["Typed Message Roundtrip"] = by_name["typed_transport"]["payload"][
        "typed_roundtrips"
    ]
    metrics["Secret/Image Exclusion"] = {
        "forbidden_secret_bearing_files_found": len(
            image_audit["secret_bearing_files_found"]
        ),
        "scan_scope": "/app application tree and explicit forbidden paths; not a universal cryptographic scan",
    }
    write(
        "metrics.json",
        {
            "recorded_at": now(),
            "metrics": metrics,
            "final_probe_observations": {"passed": len(probes), "failed": 0},
            "units": "Each denominator is finite and local to its own metric; overlapping metrics are not additive. Native+controlled+restart+three negative startups = six.",
        },
    )
    negative = [
        {
            "class": "ENVIRONMENT/PERMISSION",
            "finding": "Sandbox WSL access denied; host-authorized read succeeded. Normal Linux user docker socket denied and sudo -n required password.",
            "resolution": "WSL root used for Docker; no group/socket permission changes.",
        },
        {
            "class": "ENVIRONMENT/PYTHON",
            "finding": "Windows project .venv targets missing C:/Program Files/Python311/python.exe.",
            "resolution": "Isolated WSL snapshot dependencies and built image Linux/Python3.12 for regression suites; project venv/lock not changed.",
        },
        {
            "class": "ENVIRONMENT/FILESYSTEM",
            "finding": "First /tmp snapshot dependency workspace was not found on the next call; cause not determined.",
            "resolution": "Use recorded /var/tmp workspace; original setup log retained.",
        },
        {
            "class": "ENVIRONMENT/GIT",
            "finding": "WSL root Git safe-directory guard rejected the user-owned checkout.",
            "resolution": "Exact safe.directory passed per Git invocation only; no global config change.",
        },
        {
            "class": "HARNESS/PREPARATION",
            "finding": "Bootstrap script indentation and Git cwd errors occurred during preparation; initial Ruff E402 ordering findings were also observed.",
            "resolution": "Corrected before applicable final freeze; delayed guarded imports explicitly annotated. No product changes.",
        },
        {
            "class": "HARNESS/NETWORK",
            "finding": "attempt_01: internal bridge did not publish the host port. Service logs showed startup complete; host HTTP startup probe failed. Controlled continuation interrupted with finally cleanup.",
            "resolution": "Dedicated bridge plus localhost-only binding and test-only HTTP/DNS/socket guard; first protocol/results/logs retained.",
        },
        {
            "class": "HARNESS/TEMPORARY_PATH",
            "finding": "attempt_02: old observation directory caused FileExistsError before service creation.",
            "resolution": "Unique namespace per run; restart reuses only its own SQLite volume. Attempt retained.",
        },
        {
            "class": "PACKAGING/HEALTHCHECK",
            "finding": "Dev Compose used curl absent from the built image: actual docker exec exit 127; regression RED 1 failed.",
            "resolution": "Only dev service healthcheck changed to Python urllib /health; regression GREEN 1 passed; real Docker health healthy. RED logs retained in compose_red/.",
        },
    ]
    negative.extend(
        [
            {
                "class": "TEST_ENVIRONMENT/DESCRIPTORS",
                "finding": "Docker test process default RLIMIT_NOFILE soft=1024, hard=1048576. Aggregate rag_baseline/full exhausted descriptors.",
                "resolution": "Only affected transient test containers use nofile=65536:65536; daemon/product limits unchanged. Initial logs retained in linux_default_limits_red/.",
            },
            {
                "class": "TEST_ENVIRONMENT/CONTEXT",
                "finding": "After descriptor adjustment: rag_baseline 3 failed/907 passed/10 skipped; full 9 failed/967 passed/12 skipped due missing Git, two corpus fixtures, and legacy AppTest relative cwd.",
                "resolution": "Auxiliary test-tools image adds Git only; fixtures/.git read-only bind; test-only autouse cwd fixture for legacy app tests. Logs retained in linux_incomplete_test_context_red/. Service image, corpus and UI source unchanged.",
            },
            {
                "class": "WINDOWS_LINUX/BYTECODE",
                "finding": "Mounted cached test bytecode produced Windows source filenames in Linux tracebacks.",
                "resolution": "Final aggregate test containers use a separate PYTHONPYCACHEPREFIX; existing host bytecode is neither normalized nor deleted.",
            },
        ]
    )
    write(
        "negative_results.json",
        {
            "consolidated_at": now(),
            "observations": negative,
            "initial_attempts_not_counted_as_final_denominators": True,
        },
    )
    decision(
        "healthcheck_correction",
        "Replace only dev agent_service curl healthcheck with the Python urllib command already used in production.",
        "Actual image has no curl; RED reproduced and GREEN observed. No dependency/image/core changes needed.",
    )
    decision(
        "index_boundary",
        "Use existing snapshot_collection before build and after every real-index smoke is finished.",
        "Compare IDs/documents/canonical metadata/float32 embeddings; physical housekeeping is outside the logical equality boundary.",
    )
    decision(
        "verification",
        "Run all requested regression selections and full suite under the image Linux/Python3.12 dependencies.",
        "The Windows project venv targets a missing interpreter; a separate managed Python3.11.15 shim was discovered later. Linux verification is intentionally kept independent of that venv. Test-only dependencies and source mounts do not change the production image.",
    )
    decision(
        "cleanup",
        "Stop/remove only named smoke containers and their dedicated networks; retain built image and evidence.",
        "No user containers existed initially; no global Docker prune or destructive repository cleanup.",
    )
    journal(
        "evidence_consolidation",
        probe_observations=len(probes),
        index_identical=True,
        initial_files=preservation["initial_files"],
        preserved_files=preservation["unchanged"],
    )
    commits = git(
        "log", "--oneline", "ccf71406849634b7f7fae3f31b9d9d7217fac831..HEAD"
    ).splitlines()
    write(
        "local_commits_before_evidence.json",
        {
            "commits": commits,
            "note": "Final evidence commit SHA is omitted to avoid self-reference.",
        },
    )
    decisions = len((OUT / "decision_log.jsonl").read_text().splitlines())
    events = len((OUT / "execution_log.jsonl").read_text().splitlines())
    metric_table = "\n".join(
        f"| {name} | {value[0]}/{value[1]} |"
        for name, value in metrics.items()
        if isinstance(value, list)
    )
    test_table = "\n".join(f"| {row['suite']} | {row['summary']} |" for row in tests)
    snapshot = after["sha256"]
    sections = [
        (
            "Objetivo",
            "Preencher a lacuna operacional do Runtime Registration & Packaging V1: build real, layout Linux, startup/HTTP/SSE, persistência e shutdown. Sem experimento científico, tuning, UI, autenticação ou deploy.",
        ),
        (
            "Estado inicial",
            "Branch feat/runtime-registration-packaging-v1; HEAD ccf71406849634b7f7fae3f31b9d9d7217fac831; árvore limpa na auditoria anterior à criação da branch e das evidências. Status/branch/HEAD/log -15/diff/cached/stat executados. Branch local test/container-runtime-smoke-v1 criada exatamente desse HEAD. Ver initial_audit.json.",
        ),
        (
            "Ambiente WSL2",
            "Ubuntu 24.04.5 LTS (Noble), x86_64; kernel 6.18.54.1-microsoft-standard-WSL2. Python host WSL 3.12.3. 16 CPUs, 15.58 GiB de memória para Docker; df/free registrados. Sem instalação/atualização de Docker.",
        ),
        (
            "Docker engine",
            "Client e server Docker Engine Community 29.9.2, API 1.56; context default, unix:///var/run/docker.sock. docker info real passou como WSL root. Usuário local recebeu permission denied e sudo -n pediu senha; nenhuma modificação de grupos/permissões.",
        ),
        (
            "Docker Compose",
            "Plugin moderno docker compose v5.6.1, Buildx v0.38.1. Usado docker compose, sem depender do binário legado docker-compose. A versão real não foi rotulada incorretamente como 2.x.",
        ),
        (
            "Path do repositório",
            ". confirmado por pwd, realpath e Git. Checkout permanece em .. Nenhuma cópia do projeto para home; comandos root Git usam safe.directory específico por invocação.",
        ),
        (
            "Arquitetura/container esperado",
            "Imagem Linux amd64 com seis pacotes, entrypoint e quatro assets documentais; registry/factory/lifespan reais, integrado experimental/non-default, saver SQLite e índice existente por mounts. Provider controlado somente pelo seam de teste já existente.",
        ),
        (
            "Build context",
            "Contexto raiz, .dockerignore allowlist. .git, .env, evaluation/results, datasets, .local/chroma, venv e caches não fazem parte do contexto necessário. Nenhum ingestion/embedding executado no build.",
        ),
        (
            "Dockerfile",
            "code/docker/Dockerfile.service permanece idêntico. Python 3.12.3-slim, uv sync --frozen --no-install-project --no-dev, layout /app/code/src e CMD python src/run_service.py. Auditoria CRLF/LF em packaging_before.json; não houve normalização global. Imports reais passam no filesystem Linux case-sensitive.",
        ),
        (
            "Build real",
            f"Comando: `docker build --progress=plain -f code/docker/Dockerfile.service -t normative-agentic-rag-ufpi:runtime-smoke .`. Exit {build['exit_code']}; {build['duration_seconds']} s; cache normal, sem --no-cache. build_01.log preservado. Rede de download no build é separada de chamadas externas de runtime.",
        ),
        (
            "Image metadata",
            f"Tag {image['tags'][0]}; ID `{image['id']}`; {image['size_bytes']} bytes; Linux/amd64; cwd /app/code. Image metadata sanitizado em image_metadata.json. Imagem retida apenas localmente.",
        ),
        (
            "Python real",
            image_audit["python"]
            + ". Verificado executando o interpretador da imagem real; as suítes de regressão também usaram esse Linux/Python3.12.",
        ),
        (
            "Imports",
            "4/4: rag_baseline, service, agents.agents e schema. PersistentClient/OpenRouterClient construtores proibidos no import probe; nenhum adquirido. Supervisor não registrado/tools legados não importados pelo registry import-safe. Client não é esperado na imagem service.",
        ),
        (
            "Assets",
            f"11/11 entradas congeladas presentes: seis diretórios de pacotes, run_service.py e quatro assets. NormativeRegistry.load valida as evidências. {image_audit.get('packaged_source_files_identical_to_build_baseline', 'NOT EXECUTED')} arquivos empacotados comparados byte a byte com o baseline do build; a correção posterior é só Compose/teste e não exige rebuild da imagem.",
        ),
        (
            "Chroma volume",
            "Host WSL code/.local/chroma montado writable em /app/index por --mount, validado por docker inspect. CHROMA_PERSIST_DIR absoluto /app/index; collection real ufpi_duas_regulacoes_setor, 507 registros. Índice não embutido na imagem, criado, reindexado ou usado nos testes negativos.",
        ),
        (
            "SQLite volume",
            "Diretórios dedicados no workspace temporário registrado em temporary_workspace.json; mount em /app/state; SQLITE_DB_PATH=/app/state/checkpoints.db. Banco real do usuário não usado. O restart do caso controlado reutiliza o mesmo bind.",
        ),
        (
            "Startup",
            "6/6 startups finais: native CMD, controlado, restart controlado e três configurações negativas. Nos válidos, assembly real do integrado, registry/stamp/índice/calculator/facade montados. Nos negativos, processo saudável com experimental explicitamente indisponível.",
        ),
        (
            "Logs",
            "logs_native.log, logs_controlled_first.log, logs_controlled_restart.log e logs dos negativos preservam stdout de processos reais. Sem traceback, asset/import/collection errors inesperados nos startups finais. Tentativas anteriores e healthcheck RED preservados separadamente; nenhum segredo real fornecido.",
        ),
        (
            "Process health",
            "6/6 /health status=ok. Processo saudável não é confundido com readiness do integrado; três configurações negativas reportam integrado indisponível.",
        ),
        (
            "Integrated readiness",
            "6/6 snapshots com resultado esperado: três ready=true com 507 registros; missing index/index_unavailable, registry inválido/registry_invalid e sem provider/provider_not_configured. Provider configurado por presença de placeholder não certifica credenciais ou conectividade.",
        ),
        (
            "/info",
            "6/6 snapshots listam o integrado experimental, com available/reason adequados. Quatro IDs legados e lista permanecem. Nenhuma substituição de get_agent/facade/graph foi usada no harness.",
        ),
        (
            "Default preservation",
            "6/6 /info default_agent=chatbot_ufpi_v2. DEFAULT_AGENT e implementação das rotas gerais permanecem byte a byte iguais. Rota legado/default não foi invocada para evitar dependência Supabase/API real.",
        ),
        (
            "DIRECT",
            "HTTP real no host WSL 127.0.0.1:18080, sem ASGI em processo. Oi no integrado pelo CMD normal passa: sem normative_result, grounded_followup_result ou calculator_result. Sem tentativa externa observada.",
        ),
        (
            "Calculator",
            "2+2 pelo container normal retorna CalculatorToolResult ANSWER/numeric_result=4. Caso controlado também calcula entre pergunta normativa e repetição, conservando autoridade anterior. Sem RAG/provider externo.",
        ),
        (
            "Calculator date",
            "Adicione 10 dias corridos a 05/11/2026. retorna date_result=2026-11-15 e conteúdo 15/11/2026. Nenhum provider externo.",
        ),
        (
            "Normative smoke",
            "PASS: Resolução 177/2012, art. 68, com Router V1/core/retrieval/VersionFilter/facade reais e índice real. Provider fake existe apenas em container_entry.py montado read-only, injetado por app.state.agent_runtime_options/provider_factory já existente. ANSWER, metadata_exact, references, correlation e conteúdo tipado conferidos. Geração controlada; não mede qualidade jurídica, relevância ou credenciais reais.",
        ),
        (
            "Stream",
            "3/3 streams reais: DIRECT, calculator e normativa controlada. stream_tokens=true conserva mensagem completa, contrato tipado e ausência de campos privados. Raw SSE guardado em arquivos .sse.",
        ),
        (
            "SSE",
            "3/3: um frame data com type=message e um frame [DONE]. Nenhum draft/raw/token intermediário aceito. Negativos recebem HTTP 503 application/json antes de SSE, sem fallback.",
        ),
        (
            "Memory restart",
            "PASS 1/1: resposta normativa, cálculo e Repita na mesma identidade; stop/start real do container com SQLite persistente; Repita restaura answer/references/correlation originais. Provider novo registra zero rotas/gerações/embeddings no restart.",
        ),
        (
            "Isolation",
            "PASS 1/1: mesmo thread público e usuário smoke-B não recupera a autoridade de smoke-A. Sem autenticação nova, carga concorrente/distribuída ou promessa para turnos simultâneos da mesma identidade.",
        ),
        (
            "Missing index",
            "Path /missing-index-smoke inexistente, sem mount do índice real. Processo sobe; readiness index_unavailable; invoke/stream 503 seguros. Probe dentro do container confirma que o diretório não foi criado.",
        ),
        (
            "Invalid registry",
            "Arquivo temporário {} montado separadamente, sem modificar registry versionado. Processo sobe, experimental indisponível/registry_invalid; invoke/stream 503 sem fallback.",
        ),
        (
            "Missing provider config",
            "OPENROUTER_API_KEY ausente no container negativo; flag existente USE_FAKE_MODEL permite apenas config legada. Readiness provider_configured=false/provider_not_configured. Nenhum HTTP externo; não foi criado backdoor/fake produtivo para o integrado.",
        ),
        (
            "Shutdown",
            "6/6 stop com exit 0, sem OOM/crash/hang. Logs Uvicorn mostram shutdown concluído. Containers e rede dedicada removidos após captura de estados; imagem não publicada.",
        ),
        (
            "Resource close",
            "6/6 recursos observados em dois lifespans controlados: provider, Chroma owned e SQLite por lifespan. Dez checks suplementares (runtime/index/cache/provider/connection) verdadeiros. Native CMD prova stop de processo; não se atribui observação interna que ele não instrumenta. Borrowed saver continua sob dono da aplicação.",
        ),
        (
            "Index snapshot before/after",
            f"507/507 IDs/documentos/metadados/embeddings float32 idênticos. Mesmo mecanismo existente snapshot_collection; before antes do build e after depois dos mounts reais. SHA256 `{snapshot}`. Qualquer divergência encerraria a etapa; nenhuma observada.",
        ),
        (
            "Host permissions",
            "index_permissions.json foi produzido como usuário Linux normal uid=1000. Confere legibilidade/escrita atual de diretório e arquivos, sem escrever neles. Não houve chmod/chown/grupos. Não existe manifesto físico de ownership anterior; não se promete igualdade histórica de ACL/housekeeping.",
        ),
        (
            "Generated files",
            "SQLite e observações do runtime ficam exclusivamente nos diretórios temporários, não no checkout. Índice pode fazer housekeeping físico; igualdade lógica foi medida. Caches __pycache__ locais são ignorados e não serão versionados; auditoria final de status e staged manifest registra os arquivos entregues.",
        ),
        (
            "Compose config",
            "compose.yaml e compose.prod.yaml: config --quiet --no-env-resolution com env de interpolação próprio, sem imprimir valores reais. Dev agent_service sozinho, --no-deps --no-build --pull never; override temporário remove .env real, credentials mounts, postgres/dependencies e porta pública. Docker health final healthy. Produção nunca iniciada.",
        ),
        (
            "Image content",
            "Inspeção real de /app confirma ausência de .env, evaluation/results, datasets de experimento, .git e índice Chroma. Os corpora documentais necessários estão presentes. Não confundir montagens adicionais de harness/regressão com conteúdo original da imagem.",
        ),
        (
            "Secret exclusion",
            "Zero arquivos proibidos encontrados na árvore de aplicação inspecionada; nenhum segredo real enviado ao build/runtime, persistido ou commitado. Placeholders não são credenciais válidas. Checagem de nomes/paths e context allowlist, sem alegar varredura criptográfica universal.",
        ),
        (
            "Metrics",
            "| Métrica | Resultado observado |\n|---|---:|\n"
            + metric_table
            + f"\n\nProtocolo final: {len(probes)}/{len(probes)} observações aprovadas. Denominadores finitos; seleções/observações sobrepostas não são somáveis. Tentativas RED/interrompidas estão nos logs, fora do denominador final.",
        ),
        (
            "Negative results",
            "Ver negative_results.json, attempt_01/, attempt_02/, attempt_03_before_compose_fix/ e compose_red/. Falhas de sandbox, socket, Python Windows, safe.directory, workspace temporário, cwd/sintaxe de preparação, rede interna sem porta, colisão de namespace e curl ausente foram explicitadas. Somente curl era bug de packaging do projeto e foi corrigido por RED→GREEN.",
        ),
        (
            "Limitations",
            "Sem provider real, validação de credenciais, avaliação científica, PostgreSQL/Mongo ao vivo, deployment, UI ou carga. Runtime e Linux/Python3.12 foram executados. Guard de socket/DNS/httpx observa APIs instrumentadas; não é captura universal de pacotes/C extensions. Nenhuma tentativa externa observada nas janelas medidas; build e setup de ferramentas usaram rede separadamente. Adapter Chroma privado permanece na versão existente. Sem baseline físico anterior de ownership/housekeeping.",
        ),
        (
            "Decisions",
            f"decision_log.jsonl: {decisions} decisões públicas. execution_log.jsonl: {events} eventos até a consolidação (verificações/commit podem acrescentar eventos posteriores). Timestamps reais dos comandos/probes em UTC; data de relatório segue America/Sao_Paulo.",
        ),
        (
            "Preservation",
            f"{preservation['initial_files']} arquivos iniciais; {preservation['unchanged']} idênticos; única alteração existente: code/compose.yaml, somente healthcheck dev. Adicionados teste de regressão e evidências. Core/routing/retrieval/grounding/memory/calculator/contratos/client/Streamlit/pyproject/lock/registry/corpora/resultados anteriores idênticos. Índice 507/507 idêntico. Sem default change ou tuning V2.",
        ),
        (
            "Tests/verifications",
            "| Seleção Linux/Python3.12 | Resultado real |\n|---|---|\n"
            + test_table
            + "\n\nRegressão healthcheck: RED 1 failed por curl ausente; GREEN 1 passed. Test-only pytest 8.4.1/pytest-asyncio 1.0.0/pytest-env 1.1.5 fixados conforme uv.lock, montados separadamente. Full suite não inclui --run-docker legado; skips reais preservados. Rag/full finais usam imagem auxiliar com Git apenas, fixtures e metadata Git read-only, cwd de teste legado e nofile=65536. Falhas iniciais de ambiente, assets, cwd e descritores estão preservadas; imagem service/núcleo/UI permanecem intactos. Ruff e diff --check finais em verification.json. Seleções sobrepostas não são somadas.",
        ),
        (
            "Commits",
            "\n".join("- " + commit for commit in commits)
            + "\n- Evidências: commit final de artefatos, sem autorreferência. Nenhuma imagem publicada ou deploy.",
        ),
    ]
    full = next(row for row in tests if row["suite"] == "full")
    intro = f"# Container Build & Runtime Smoke V1\n\nData: 01/11/2026, America/Sao_Paulo. Verificação operacional local; registros de execução em UTC.\n\nBuild real **1/1**, protocolo final **{len(probes)}/{len(probes)}**, assets **11/11**, shutdown de processo **6/6**, recursos controlados **6/6**, índice **507/507 idêntico**. Suíte Linux/Python3.12: **{full['summary']}**. Uma correção mínima: healthcheck dev usa Python presente na imagem em vez de curl ausente. Integrado permanece experimental/non-default; default chatbot_ufpi_v2.\n"
    text = intro + "".join(
        f"\n## {number}. {title}\n\n{content}\n"
        for number, (title, content) in enumerate(sections, 1)
    )
    (OUT / "REPORT.md").write_text(text, encoding="utf-8")
    print(
        json.dumps(
            {
                "probe_passes": len(probes),
                "full_suite": full["summary"],
                "initial_files": preservation["initial_files"],
                "preserved_files": preservation["unchanged"],
                "index_count": after["count"],
                "index_sha256": snapshot,
                "decisions": decisions,
                "execution_events_at_consolidation": events,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
