# Container Build & Runtime Smoke V1

Data: 01/11/2026, America/Sao_Paulo. Verificação operacional local; registros de execução em UTC.

Build real **1/1**, protocolo final **65/65**, assets **11/11**, shutdown de processo **6/6**, recursos controlados **6/6**, índice **507/507 idêntico**. Suíte Linux/Python3.12: **976 passed, 12 skipped, 5 warnings in 126.80s (0:02:06)**. Uma correção mínima: healthcheck dev usa Python presente na imagem em vez de curl ausente. Integrado permanece experimental/non-default; default chatbot_ufpi_v2.

## 1. Objetivo

Preencher a lacuna operacional do Runtime Registration & Packaging V1: build real, layout Linux, startup/HTTP/SSE, persistência e shutdown. Sem experimento científico, tuning, UI, autenticação ou deploy.

## 2. Estado inicial

Branch feat/runtime-registration-packaging-v1; HEAD ccf71406849634b7f7fae3f31b9d9d7217fac831; árvore limpa na auditoria anterior à criação da branch e das evidências. Status/branch/HEAD/log -15/diff/cached/stat executados. Branch local test/container-runtime-smoke-v1 criada exatamente desse HEAD. Ver initial_audit.json.

## 3. Ambiente WSL2

Ubuntu 24.04.5 LTS (Noble), x86_64; kernel 6.18.54.1-microsoft-standard-WSL2. Python host WSL 3.12.3. 16 CPUs, 15.58 GiB de memória para Docker; df/free registrados. Sem instalação/atualização de Docker.

## 4. Docker engine

Client e server Docker Engine Community 29.9.2, API 1.56; context default, unix:///var/run/docker.sock. docker info real passou como WSL root. Usuário local recebeu permission denied e sudo -n pediu senha; nenhuma modificação de grupos/permissões.

## 5. Docker Compose

Plugin moderno docker compose v5.6.1, Buildx v0.38.1. Usado docker compose, sem depender do binário legado docker-compose. A versão real não foi rotulada incorretamente como 2.x.

## 6. Path do repositório

. confirmado por pwd, realpath e Git. Checkout permanece em .. Nenhuma cópia do projeto para home; comandos root Git usam safe.directory específico por invocação.

## 7. Arquitetura/container esperado

Imagem Linux amd64 com seis pacotes, entrypoint e quatro assets documentais; registry/factory/lifespan reais, integrado experimental/non-default, saver SQLite e índice existente por mounts. Provider controlado somente pelo seam de teste já existente.

## 8. Build context

Contexto raiz, .dockerignore allowlist. .git, .env, evaluation/results, datasets, .local/chroma, venv e caches não fazem parte do contexto necessário. Nenhum ingestion/embedding executado no build.

## 9. Dockerfile

code/docker/Dockerfile.service permanece idêntico. Python 3.12.3-slim, uv sync --frozen --no-install-project --no-dev, layout /app/code/src e CMD python src/run_service.py. Auditoria CRLF/LF em packaging_before.json; não houve normalização global. Imports reais passam no filesystem Linux case-sensitive.

## 10. Build real

Comando: `docker build --progress=plain -f code/docker/Dockerfile.service -t normative-agentic-rag-ufpi:runtime-smoke .`. Exit 0; 120.316 s; cache normal, sem --no-cache. build_01.log preservado. Rede de download no build é separada de chamadas externas de runtime.

## 11. Image metadata

Tag normative-agentic-rag-ufpi:runtime-smoke; ID `sha256:3496896a631a3bcf6a71f117bf30d4d2abd9cdfbe657cf0956f17faefb32d9d5`; 1859608777 bytes; Linux/amd64; cwd /app/code. Image metadata sanitizado em image_metadata.json. Imagem retida apenas localmente.

## 12. Python real

3.12.3 (main, May 14 2024, 07:34:56) [GCC 12.2.0]. Verificado executando o interpretador da imagem real; as suítes de regressão também usaram esse Linux/Python3.12.

## 13. Imports

4/4: rag_baseline, service, agents.agents e schema. PersistentClient/OpenRouterClient construtores proibidos no import probe; nenhum adquirido. Supervisor não registrado/tools legados não importados pelo registry import-safe. Client não é esperado na imagem service.

## 14. Assets

11/11 entradas congeladas presentes: seis diretórios de pacotes, run_service.py e quatro assets. NormativeRegistry.load valida as evidências. 95 arquivos empacotados comparados byte a byte com o baseline do build; a correção posterior é só Compose/teste e não exige rebuild da imagem.

## 15. Chroma volume

Host WSL code/.local/chroma montado writable em /app/index por --mount, validado por docker inspect. CHROMA_PERSIST_DIR absoluto /app/index; collection real ufpi_duas_regulacoes_setor, 507 registros. Índice não embutido na imagem, criado, reindexado ou usado nos testes negativos.

## 16. SQLite volume

Diretórios dedicados no workspace temporário registrado em temporary_workspace.json; mount em /app/state; SQLITE_DB_PATH=/app/state/checkpoints.db. Banco real do usuário não usado. O restart do caso controlado reutiliza o mesmo bind.

## 17. Startup

6/6 startups finais: native CMD, controlado, restart controlado e três configurações negativas. Nos válidos, assembly real do integrado, registry/stamp/índice/calculator/facade montados. Nos negativos, processo saudável com experimental explicitamente indisponível.

## 18. Logs

logs_native.log, logs_controlled_first.log, logs_controlled_restart.log e logs dos negativos preservam stdout de processos reais. Sem traceback, asset/import/collection errors inesperados nos startups finais. Tentativas anteriores e healthcheck RED preservados separadamente; nenhum segredo real fornecido.

## 19. Process health

6/6 /health status=ok. Processo saudável não é confundido com readiness do integrado; três configurações negativas reportam integrado indisponível.

## 20. Integrated readiness

6/6 snapshots com resultado esperado: três ready=true com 507 registros; missing index/index_unavailable, registry inválido/registry_invalid e sem provider/provider_not_configured. Provider configurado por presença de placeholder não certifica credenciais ou conectividade.

## 21. /info

6/6 snapshots listam o integrado experimental, com available/reason adequados. Quatro IDs legados e lista permanecem. Nenhuma substituição de get_agent/facade/graph foi usada no harness.

## 22. Default preservation

6/6 /info default_agent=chatbot_ufpi_v2. DEFAULT_AGENT e implementação das rotas gerais permanecem byte a byte iguais. Rota legado/default não foi invocada para evitar dependência Supabase/API real.

## 23. DIRECT

HTTP real no host WSL 127.0.0.1:18080, sem ASGI em processo. Oi no integrado pelo CMD normal passa: sem normative_result, grounded_followup_result ou calculator_result. Sem tentativa externa observada.

## 24. Calculator

2+2 pelo container normal retorna CalculatorToolResult ANSWER/numeric_result=4. Caso controlado também calcula entre pergunta normativa e repetição, conservando autoridade anterior. Sem RAG/provider externo.

## 25. Calculator date

Adicione 10 dias corridos a 05/11/2026. retorna date_result=2026-11-15 e conteúdo 15/11/2026. Nenhum provider externo.

## 26. Normative smoke

PASS: Resolução 177/2012, art. 68, com Router V1/core/retrieval/VersionFilter/facade reais e índice real. Provider fake existe apenas em container_entry.py montado read-only, injetado por app.state.agent_runtime_options/provider_factory já existente. ANSWER, metadata_exact, references, correlation e conteúdo tipado conferidos. Geração controlada; não mede qualidade jurídica, relevância ou credenciais reais.

## 27. Stream

3/3 streams reais: DIRECT, calculator e normativa controlada. stream_tokens=true conserva mensagem completa, contrato tipado e ausência de campos privados. Raw SSE guardado em arquivos .sse.

## 28. SSE

3/3: um frame data com type=message e um frame [DONE]. Nenhum draft/raw/token intermediário aceito. Negativos recebem HTTP 503 application/json antes de SSE, sem fallback.

## 29. Memory restart

PASS 1/1: resposta normativa, cálculo e Repita na mesma identidade; stop/start real do container com SQLite persistente; Repita restaura answer/references/correlation originais. Provider novo registra zero rotas/gerações/embeddings no restart.

## 30. Isolation

PASS 1/1: mesmo thread público e usuário smoke-B não recupera a autoridade de smoke-A. Sem autenticação nova, carga concorrente/distribuída ou promessa para turnos simultâneos da mesma identidade.

## 31. Missing index

Path /missing-index-smoke inexistente, sem mount do índice real. Processo sobe; readiness index_unavailable; invoke/stream 503 seguros. Probe dentro do container confirma que o diretório não foi criado.

## 32. Invalid registry

Arquivo temporário {} montado separadamente, sem modificar registry versionado. Processo sobe, experimental indisponível/registry_invalid; invoke/stream 503 sem fallback.

## 33. Missing provider config

OPENROUTER_API_KEY ausente no container negativo; flag existente USE_FAKE_MODEL permite apenas config legada. Readiness provider_configured=false/provider_not_configured. Nenhum HTTP externo; não foi criado backdoor/fake produtivo para o integrado.

## 34. Shutdown

6/6 stop com exit 0, sem OOM/crash/hang. Logs Uvicorn mostram shutdown concluído. Containers e rede dedicada removidos após captura de estados; imagem não publicada.

## 35. Resource close

6/6 recursos observados em dois lifespans controlados: provider, Chroma owned e SQLite por lifespan. Dez checks suplementares (runtime/index/cache/provider/connection) verdadeiros. Native CMD prova stop de processo; não se atribui observação interna que ele não instrumenta. Borrowed saver continua sob dono da aplicação.

## 36. Index snapshot before/after

507/507 IDs/documentos/metadados/embeddings float32 idênticos. Mesmo mecanismo existente snapshot_collection; before antes do build e after depois dos mounts reais. SHA256 `ab253a24b756d9f3d3e05aeb49220798b08d947704112327fd894a577bb2b38a`. Qualquer divergência encerraria a etapa; nenhuma observada.

## 37. Host permissions

index_permissions.json foi produzido como usuário Linux normal uid=1000. Confere legibilidade/escrita atual de diretório e arquivos, sem escrever neles. Não houve chmod/chown/grupos. Não existe manifesto físico de ownership anterior; não se promete igualdade histórica de ACL/housekeeping.

## 38. Generated files

SQLite e observações do runtime ficam exclusivamente nos diretórios temporários, não no checkout. Índice pode fazer housekeeping físico; igualdade lógica foi medida. Caches __pycache__ locais são ignorados e não serão versionados; auditoria final de status e staged manifest registra os arquivos entregues.

## 39. Compose config

compose.yaml e compose.prod.yaml: config --quiet --no-env-resolution com env de interpolação próprio, sem imprimir valores reais. Dev agent_service sozinho, --no-deps --no-build --pull never; override temporário remove .env real, credentials mounts, postgres/dependencies e porta pública. Docker health final healthy. Produção nunca iniciada.

## 40. Image content

Inspeção real de /app confirma ausência de .env, evaluation/results, datasets de experimento, .git e índice Chroma. Os corpora documentais necessários estão presentes. Não confundir montagens adicionais de harness/regressão com conteúdo original da imagem.

## 41. Secret exclusion

Zero arquivos proibidos encontrados na árvore de aplicação inspecionada; nenhum segredo real enviado ao build/runtime, persistido ou commitado. Placeholders não são credenciais válidas. Checagem de nomes/paths e context allowlist, sem alegar varredura criptográfica universal.

## 42. Metrics

| Métrica | Resultado observado |
|---|---:|
| Docker Engine Availability | 1/1 |
| Docker Build Success | 1/1 |
| Image Runtime Import Success | 4/4 |
| Image Asset Completeness | 11/11 |
| Container Startup Success | 6/6 |
| Process Health Success | 6/6 |
| Integrated Readiness Success | 6/6 |
| Registered Agent Visibility | 6/6 |
| Default Preservation | 6/6 |
| Direct Container Smoke | 1/1 |
| Calculator Container Smoke | 1/1 |
| Date Calculator Container Smoke | 1/1 |
| Normative Container Smoke | 1/1 |
| Container Memory Restart Continuity | 1/1 |
| Cross-user Isolation | 1/1 |
| Stream Contract Preservation | 3/3 |
| Negative Readiness Behavior | 3/3 |
| Runtime External Call Avoidance | 6/6 |
| Process Graceful Shutdown | 6/6 |
| Resource Shutdown Success | 6/6 |
| Index Logical Preservation | 507/507 |
| Container Path Portability | 11/11 |
| Typed Message Roundtrip | 11/11 |

Protocolo final: 65/65 observações aprovadas. Denominadores finitos; seleções/observações sobrepostas não são somáveis. Tentativas RED/interrompidas estão nos logs, fora do denominador final.

## 43. Negative results

Ver negative_results.json, attempt_01/, attempt_02/, attempt_03_before_compose_fix/ e compose_red/. Falhas de sandbox, socket, Python Windows, safe.directory, workspace temporário, cwd/sintaxe de preparação, rede interna sem porta, colisão de namespace e curl ausente foram explicitadas. Somente curl era bug de packaging do projeto e foi corrigido por RED→GREEN.

O primeiro diff --check staged sinalizou padding de terminal, delimitadores finais de SSE e CRLF em metadados. whitespace_policy.json e diff_staged_initial_raw_output.log preservam o achado. Atributos apenas nesta pasta nova reconhecem CR-at-eol e preservam whitespace de capturas .log/.sse; nenhum byte congelado ou arquivo anterior foi normalizado. O check staged final passou.

## 44. Limitations

Sem provider real, validação de credenciais, avaliação científica, PostgreSQL/Mongo ao vivo, deployment, UI ou carga. Runtime e Linux/Python3.12 foram executados. Guard de socket/DNS/httpx observa APIs instrumentadas; não é captura universal de pacotes/C extensions. Nenhuma tentativa externa observada nas janelas medidas; build e setup de ferramentas usaram rede separadamente. Adapter Chroma privado permanece na versão existente. Sem baseline físico anterior de ownership/housekeeping.

## 45. Decisions

decision_log.jsonl: 29 decisões públicas. execution_log.jsonl: 333 eventos até a preparação do commit final. Timestamps reais dos comandos/probes em UTC; data de relatório segue America/Sao_Paulo.

## 46. Preservation

861 arquivos iniciais; 860 idênticos; única alteração existente: code/compose.yaml, somente healthcheck dev. Adicionados teste de regressão e evidências. Core/routing/retrieval/grounding/memory/calculator/contratos/client/Streamlit/pyproject/lock/registry/corpora/resultados anteriores idênticos. Índice 507/507 idêntico. Sem default change ou tuning V2.

## 47. Tests/verifications

| Seleção Linux/Python3.12 | Resultado real |
|---|---|
| calculator | 114 passed, 806 deselected, 2 warnings in 21.65s |
| conversation | 91 passed, 829 deselected, 2 warnings in 22.38s |
| full | 976 passed, 12 skipped, 5 warnings in 126.80s (0:02:06) |
| rag_baseline | 910 passed, 10 skipped, 3 warnings in 122.35s (0:02:02) |
| runtime | 37 passed, 2 warnings in 27.47s |
| service_client | 33 passed, 4 warnings in 1.25s |
| transport | 98 passed, 822 deselected in 20.18s |

Regressão healthcheck: RED 1 failed por curl ausente; GREEN 1 passed. Test-only pytest 8.4.1/pytest-asyncio 1.0.0/pytest-env 1.1.5 fixados conforme uv.lock, montados separadamente. Full suite não inclui --run-docker legado; skips reais preservados. Rag/full finais usam imagem auxiliar com Git apenas, fixtures e metadata Git read-only, cwd de teste legado e nofile=65536. Falhas iniciais de ambiente, assets, cwd e descritores estão preservadas; imagem service/núcleo/UI permanecem intactos. Ruff e diff --check finais em verification.json. Seleções sobrepostas não são somadas.

Revisão de engenharia: zero achados críticos/importantes. Um minor adiado: o teste de healthcheck depende do PATH do executor; RED/GREEN dentro da imagem e Compose healthy são a evidência autoritativa. Ver review_findings.json. Limites de provider/rede/produção/ownership permanecem explícitos.

## 48. Commits

- cdc4996 fix: use Python for service container healthcheck
- 548ab38 test: reproduce container runtime healthcheck issue
- Evidências: commit final de artefatos, sem autorreferência. Nenhuma imagem publicada ou deploy.
