# Runtime Registration & Packaging V1

Data: 01/11/2026, America/Sao_Paulo, conforme contexto atualizado do cliente. Verificação local de engenharia com providers controlados; timestamps de execução nos artefatos estão em UTC.

O integrado foi registrado como **experimental/non-default** e construído pelo runtime normal nos dois startups válidos observados (2/2). Default preservado (5/5), transporte tipado (12/12), continuidade (6/6), isolamento (2/2) e fechamento de recursos (9/9). Zero chamadas externas em cinco startups. A suíte completa passou com **975 passed / 12 skipped**; **507 registros** permaneceram idênticos. Docker indisponível: completeness estático 11/11 e import smoke em layout simulado 1/1 não demonstram build/container Linux ou prontidão para produção.

## 1. Objetivo

Registrar e empacotar o integrado como experimental/non-default no runtime normal, com lifecycle e readiness explícitos. Sem UI nova, autenticação, deploy, tuning, calculator/memória novas ou experimento científico.

## 2. Estado inicial

Branch `feat/calculator-tool-routing-v1`, HEAD `706bd7cc5e7f333032c7de7b58ed89dc41c09bd0`, árvore limpa na inspeção inicial. Status, branch, HEAD, log -15, diff, diff --cached e diff --stat foram executados antes de mudar código. A branch `feat/runtime-registration-packaging-v1` nasceu desse HEAD. [initial_audit.json](initial_audit.json) distingue a observação da branch-fonte da captura posterior à criação da pasta de evidência.

## 3. Arquitetura antes

Registry com quatro grafos importados antecipadamente, além de agentes não registrados e modelo de supervisor. Lifespan atribuía saver/store a grafos prontos. O integrado existia apenas por builder/injeção; Dockerfile.service não copiava rag_baseline nem os assets documentais necessários.

## 4. Arquitetura depois

Registry import-safe → lifespan das factories existentes de saver/store → assembly do integrado uma vez → get_agent geral → invoke/stream tipados. Falha esperada de dependência experimental não derruba legado; erro crítico de banco/store ou programação continua interrompendo startup.

## 5. Runtime factory

[integrated_runtime.py](../../../code/src/rag_baseline/integrated_runtime.py) contém build_integrated_agent_runtime e IntegratedAgentRuntime. Monta settings, registry validado, índice existente, RagService, Router V1, VersionFilter, facade, stamp, transformer e grafo. O builder anterior constrói a calculator; não há implementação duplicada. Saver real é recebido do lifespan/factory existente, com um único owner.

## 6. Registration

Extensão mínima de Agent com import_path e runtime_factory, mantendo graph pronto para compatibilidade. Não há special-case do ID em invoke/stream; o contrato geral resolve agentes. AgentInfo ganha experimental, available e unavailable_reason opcionais/aditivos. Os quatro IDs/descrições anteriores permanecem.

## 7. Agent ID

`chatbot_ufpi_integrated_v1`, sem aliases. Registrado publicamente nesta etapa, experimental e chamado por seleção explícita.

## 8. Default preservation

DEFAULT_AGENT antes/depois = `chatbot_ufpi_v2`. Rotas sem agent_id permanecem vinculadas a esse default. Verificação rígida e probes: 5/5 snapshots de /info conservaram o default.

## 9. Lazy/eager behavior

Importar registry/factory não abre Chroma, provider, banco, registry documental ou fingerprint. Grafos legados são carregados sob demanda e recebem as dependências no lifespan. O integrado é montado no startup e reutilizado por request. Supervisor não registrado deixa de ser importado pelo registry.

## 10. Resource ownership

Aplicação: saver/store e respectivos context managers. Runtime: graph, provider closable e leases Chroma. OpenRouter existente não mantém httpx client permanente: cada request possui seu contexto. Transformer sem provider não tem recurso externo. Sistema Chroma pré-existente é borrowed e permanece do criador. O adapter usa APIs internas estreitas da versão instalada porque não há Client.close público; upgrades exigem revisão.

## 11. Startup

Factories existentes inicializam saver/store; registry carrega grafos legados e entra no context manager integrado. Sem provider/HTTP, embeddings, retrieval de pergunta ou geração no startup observado. Leitura local de arquivos/count/get para validar e fingerprint é permitida. Um assembly por lifespan, não por request. Dois startups válidos e três indisponibilidades configuradas foram observados.

## 12. Shutdown

AsyncExitStack fecha provider e leases; aplicação fecha saver/store. Falhas depois da aquisição também limpam recursos. Chroma parcialmente iniciado é limpo sem parar sistemas borrowed; Rust sem bindings é tratado apenas nesse caminho parcial. Observações: provider 2/2, Chroma owned 2/2, SQLite saver 5/5, total 9/9. Store SQLite é InMemoryStore, sem conexão a fechar.

## 13. Registry

Quatro entradas legadas: chatbot_ufpi_agentic, chatbot_ufpi, chatbot_ufpi_v2 e chatbot_generic. Agente desconhecido retorna 404; experimental conhecido e indisponível retorna 503 com código seguro, inclusive antes dos headers SSE. Sem fallback silencioso para outro agente. /info conserva a lista, ampliando metadata aditivamente.

## 14. Chroma/index

Adapter reutiliza métodos de ChromaVectorStore e abre somente get_collection, desviando do get_or_create do construtor legado. Exige diretório/database existentes; não cria índice ausente ou collection faltante. Bind persistente no container, fora da imagem. Chroma pode fazer housekeeping local no startup; a fronteira protegida mede igualdade lógica de IDs/documentos/metadados/embeddings.

## 15. Normative registry

NormativeRegistry.load valida schema, relações e evidências documentais, sem aceitar registry parcial. Default no layout do checkout/imagem; override opcional NORMATIVE_REGISTRY_PATH. Registry inválido ou evidência ausente produz registry_invalid, sem expor paths/exceção/chaves ao client.

## 16. Memory stamp

build_memory_stamp existente executa uma vez por build após a validação. Corpus/registry fingerprints e versões conservam o contrato anterior. Requests e health não recalculam o fingerprint. Restart é necessário após mudanças nos assets/índice; readiness não monitora equivalência semântica ou deriva do corpus.

## 17. Checkpointer

initialize_database/initialize_store e backends existentes permanecem intactos. Default do código: SQLite; Compose de produção mantém PostgreSQL como antes. Runtime borrows o saver, sem conectar outro. SQLite em arquivo temporário foi fechado/reaberto; Postgres/Mongo não foram iniciados nem validados ao vivo.

## 18. Provider config

BaselineSettings e perfil duas-regulacoes existentes; OpenRouter, embedding/modelo de geração, temperatura, top_k e Router V1 preservados. Campo model legado do request não substitui modelos internos. Chave obrigatória é validada por presença, sem imprimir valor ou testar credencial remotamente. Todos os providers dos probes são controlados. Transformer usa fallback determinístico para o source answer.

## 19. Readiness

Endpoint `/agents/{agent_id}/readiness`. Checa registro, configuração, registry/stamp montados, saver inicializado, calculator/facade disponíveis e count/acesso local ao índice. Não confunde configured com connected. Flag de registry/stamp reflete startup; acesso/count do índice é consultado localmente. Resultados esperados de cinco snapshots: 5/5, incluindo três falhas explícitas.

## 20. Health

`/health` conserva status do processo e adiciona integrated_agent. Processo ok não implica agente pronto. Health/readiness não chamam OpenRouter/LLM ou HTTP; a antiga auth_check remota do Langfuse foi substituída por estado de configuração, sem alegar conectividade.

## 21. /info

Lista o integrado experimental e sua disponibilidade/reason code, sem removê-lo quando faltam assets. Default e estrutura de lista anteriores permanecem. Legacy registry preservation 4/4 entradas; mensagens de erro não expõem chave, envelope privado ou storage key.

## 22. Invoke registered

POST `/chatbot_ufpi_integrated_v1/invoke` usa o registry/factory/lifespan reais, sem substituir get_agent, facade ou graph no harness. Somente settings/provider controlado e path SQLite são configurados em dependências confiáveis da aplicação. AgentClient restaura modelos tipados pelo schema compartilhado.

## 23. Stream registered

POST `/chatbot_ufpi_integrated_v1/stream` usa o mesmo runtime e transporte existente. Um message completo + DONE para emissão integrada, inclusive stream_tokens=true. /stream desconhecido/indisponível recebe erro HTTP explícito antes dos headers. Testes/probes usam ASGI em processo, sem servidor exposto.

## 24. Direct

Oi no agente registrado produz resposta direta e nenhum dos três resultados tipados; não chama provider normativo.

## 25. Calculator

2+2 no agente registrado produz CalculatorToolResult e zero provider. ERROR 1/0 durante pending preserva memória/pendência. Parser/tool/contratos e semântica da calculator permanecem byte a byte iguais.

## 26. Normative

Queries passam por Router V1, facade, estratégias e núcleo anteriores. Há metadata_exact real/controlado, além de dense para perguntas temáticas. Providers e vetores 2D de dez chunks temporários são fixtures técnicas; não medem qualidade jurídica ou relevância do índice completo de 507 registros.

## 27. Memory continuity

Mesma identidade mantém envelope ao transformar/calcular; mudança de domínio cria operação nova; clarification retorna UUID/pergunta originais sem campo clarification manual. Após fechar/reabrir o lifespan/SQLite, repita recupera o último ANSWER sem nova rota/provider. Seis observações de continuidade: 6/6. /history permanece legado/default, sem reconstrução dos resultados integrados privados.

## 28. Isolation

Mesmo thread público e usuários diferentes não compartilham authority. Requests concorrentes distintos para normativa/calculator ficaram isolados: 2/2 grupos. Identidade segue declarada pelo cliente; nenhuma autenticação/autorizaçao adicionada. Sem promessa de turnos simultâneos da mesma identidade ou segurança distribuída.

## 29. Typed transport

normative_result, grounded_followup_result e calculator_result continuam exclusivos, com conteúdo exato. ChatMessage e projetor tipado anteriores são preservados. AgentClient não mudou. 12/12 mensagens tipadas conservadas e 0/25 vazamentos de campos privados nos registros públicos avaliados.

## 30. Dockerfile

Dockerfile.service passa a buildar com contexto da raiz; layout /app/code/src preserva paths package-relative. Copia seis pacotes, entrypoint e quatro assets documentais específicos. Não copia evaluation/results, datasets, logs, .env ou índice. Imagem não foi construída neste ambiente.

## 31. Runtime assets

Lista derivada da validação do registry: data/normative_registry.json, graduacao_setor_v2.json, pos_graduacao_setor_v2.json e 1056_2026_temporal_v1.json. Não são datasets de experimento; a validação documental existente lê esses arquivos. Arquivos fonte permanecem idênticos.

## 32. Chroma packaging

Compose monta `code/.local/chroma` em `/app/index` e configura CHROMA_PERSIST_DIR absoluto. Índice é persistent data, não code asset; não é embutido na imagem nem gerado no startup. Mount é writable por requisitos de housekeeping do Chroma, sem chamadas de indexação da aplicação.

## 33. Paths Windows/Linux

Index/registry relativos ancorados em code/; testados a partir de outro cwd. Docker usa caminhos POSIX e hierarquia compatível com versioning.py. Factory SQLite anterior conserva resolução de path relativo por cwd; use path absoluto fora de code/. Nenhum path Windows hardcoded na implementação/packaging. Linux real de container não foi executado.

## 34. langgraph.json

Permanece byte a byte igual: Python3.12 e research_assistant. É entrypoint separado do registry da API. Não muda graph principal/default desta configuração.

## 35. Python/dependencies

Execução local: 3.11.15 (main, Mar 10 2026, 18:12:25) [MSC v.1944 64 bit (AMD64)]. Docker3.12.3 e LangGraph3.12 mantidos. Pyproject/lock intactos; versões instaladas em packaging_audit.json. Nenhuma instalação/atualização necessária. Compatibilidade Linux3.12 é inspecionada/configurada, não demonstrada por execução.

## 36. Container build

Não executado: Docker CLI não encontrado no PATH nem no local convencional inspecionado. Não se instalou Docker nem se publicou imagem. packaging_audit.json registra indisponibilidade; a checagem de completeness é estática/contexto, não prova de build.

## 37. Container smoke

Não executado, pelo mesmo motivo. Smoke alternativo copia pacotes/assets para filesystem temporário com layout da imagem, muda cwd e importa registry/service, validando registry/evidências: 1/1. Não equivale a container/startup Linux real. Dockerfile.app também passa a copiar os contratos rag_baseline no layout profundo; fonte Streamlit permanece intacta.

## 38. Probes

[technical_protocol.json](technical_protocol.json) congelou 15 grupos e 18 hashes antes da única execução integral. [local_probes.py](local_probes.py) bloqueia socket/HTTP externos e permite somente ASGI local exato; usa factories existentes, provider controlado e journal imediato. [probe_rows.jsonl](probe_rows.jsonl) tem 25 observações. Nenhum código/harness/expectativa congelado mudou após execução. Startup external calls 0/5 startups; nenhuma tentativa externa no conjunto observado.

## 39. Technical metrics

Denominadores finitos e unidades: builds válidos 2; snapshots de disponibilidade 2/default5/readiness5; quatro entradas legadas únicas; mensagens tipadas12; continuidade6; grupos de isolamento2; recursos com fechamento9; configurações recusadas3; entradas declaradas de packaging11; import smoke1. Não somar métricas sobrepostas.

| Métrica | Numerador/denominador |
|---|---:|
| Runtime Build Success | 2/2 |
| Registered Agent Availability | 2/2 |
| Startup External Call Avoidance | 5/5 |
| Private Field Exclusion | 25/25 |
| Default Preservation | 5/5 |
| Legacy Agent Registry Preservation | 4/4 |
| Integrated Readiness Checks | 5/5 |
| Runtime Typed Transport Preservation | 12/12 |
| Runtime Memory Continuity | 6/6 |
| Runtime Isolation | 2/2 |
| Resource Close Success | 9/9 |
| Unavailable Configuration Rejection | 3/3 |
| Packaging Completeness | 11/11 |
| Import Smoke Success | 1/1 |

## 40. Negative results

RED inicial: 14 failed, 1 passed, 16 erros de fixture por ausência do componente. Primeiro GREEN: 4 failed/27 passed por fixtures de subprocess/modelo/pergunta canônica; corrigidas sem mudar núcleo/resolver. Revisão reproduziu vazamento de sistema Chroma parcial com SQLite corrompido, inclusive stop nativo sem bindings; corrigido por regressão RED→GREEN. Um teste antigo de ausência no registry falhou legitimamente e teve a expectativa atualizada para esta etapa. Capturas tdd_*.txt preservam resultados. Check de format de scripts ocorreu durante sua preparação; captura inicial foi preservada e os checks estáticos repetidos depois. Não houve tuning seletivo após freeze.

## 41. Limitations

Sem Docker/container real, Python3.12 executado, Postgres/Mongo ao vivo, API real, carga, deployment ou validação de credenciais. Adapter Chroma depende de API privada da versão instalada. Registry global pressupõe uma lifespan de aplicação por processo; overlapping lifespans não são suportadas. Readiness não certifica semântica do corpus, modelo ou qualidade jurídica. As limitações científicas anteriores, inclusive o experimento dos 44 casos, permanecem; nenhum novo experimento ou tuning foi realizado.

## 42. Decisions

[decision_log.jsonl](decision_log.jsonl) tem 22 decisões públicas. [execution_log.jsonl](execution_log.jsonl) tem 30 eventos observáveis; recorded_at é consolidação, enquanto testes/protocolo contêm timestamps de execução. [runtime_audit.json](runtime_audit.json), [packaging_audit.json](packaging_audit.json) e [review_findings.json](review_findings.json) preservam escolhas/achados. A correção da revisão foi verificada por regressões e suíte completa; não houve segunda revisão.

## 43. Preservation

[preservation_before.json](preservation_before.json) e [preservation.json](preservation.json): **798 arquivos iniciais, 788 idênticos e dez mudanças autorizadas**:

- `code/.dockerignore`
- `code/.env.example`
- `code/compose.prod.yaml`
- `code/compose.yaml`
- `code/docker/Dockerfile.app`
- `code/docker/Dockerfile.service`
- `code/src/agents/agents.py`
- `code/src/schema/schema.py`
- `code/src/service/service.py`
- `code/tests/rag_baseline/test_typed_normative_transport.py`

Core normativo, RouterV1/V2, Temporal Intent, dense/metadata_exact/vector_filtered, VersionFilter, grounding, StructuredOutputV2, NormativeToolResult, facade/tool, agent builder, conversation policy/memory/transformer, calculator, ChatMessage/projetor, client, registry normativo, Streamlit, pyproject/lock, langgraph.json e resultados anteriores permanecem intactos. Registro público muda intencionalmente; default/IDs/descrições legados são preservados. [contract_checks.json](contract_checks.json) confirma AST de contratos/funções preservados dentro dos arquivos alterados.

**507 IDs/documentos/metadados/embeddings float32 idênticos**, snapshot `ab253a24b756d9f3d3e05aeb49220798b08d947704112327fd894a577bb2b38a`. Sem reindexação, metadata update ou re-embedding. .gitattributes -text/CR aplica-se somente à pasta nova de evidências. Manifests distinguem working files e blobs Git quando finais de linha diferem.

## 44. Tests

[test_results.json](test_results.json) e stdout pytest registram comandos, cwd, timestamps, status e contagens reais. Seleções sobrepostas não são somáveis.

| Seleção | Resultado real |
|---|---|
| runtime | 37 passed, 2 warnings in 24.25s |
| calculator | 111 passed in 9.25s |
| conversation_memory | 89 passed in 15.88s |
| memory | 2 passed in 0.23s |
| transport | 51 passed in 8.98s |
| agent | 61 passed in 3.45s |
| retrieval | 76 passed in 9.49s |
| facade | 79 passed in 0.68s |
| structured | 122 passed in 2.24s |
| temporal | 93 passed in 5.03s |
| rag_baseline | 910 passed, 10 skipped, 2 warnings in 67.07s (0:01:07) |
| service | 24 passed, 3 warnings in 1.22s |
| client | 9 passed, 1 warning in 0.12s |
| legacy_app_integration | 7 passed, 2 skipped in 1.90s |
| legacy_core | 23 passed in 6.22s |
| full | 975 passed, 12 skipped, 4 warnings in 69.89s (0:01:09) |

Ruff check/format-check de produto/testes e scripts de evidência aprovados; git diff --check staged/unstaged aprovados, conforme [verification.json](verification.json). Warnings completos são legados: Pydantic de dependência, AsyncMock/client e timeout TestClient. Docker opt-in e skips anteriores permanecem.

## 45. Commits

1. `3610c0c` — test: define integrated runtime registration boundaries.
2. `7be35db0999240d111ddf430fe108b09afd072a9` — feat: register integrated agent runtime.
3. `fa567262ab2dabe7ec59f09796416c6888e8cbb3` — build: package integrated normative agent runtime.
4. Evidências — test: verify registered runtime and packaging.

Sem deploy, autenticação nova, Supabase no integrado, reindexação, tuningV2 ou API real nos probes. Default e fonte Streamlit intactos. Esta entrega termina no runtime/packaging experimental, sem iniciar a próxima etapa.
