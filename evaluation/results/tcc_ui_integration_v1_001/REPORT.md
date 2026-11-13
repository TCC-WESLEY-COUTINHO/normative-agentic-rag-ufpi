# TCC UI Integration V1

Data: 01/11/2026, America/Sao_Paulo. Execuções em UTC; engenharia local com provider controlado.

**12/12 probes**, **12/12 requests ao integrado**, **26/26 referências tipadas**, **507/507 registros idênticos**. Suíte final: **1001 passed / 12 skipped**. Default backend preservado; sem seletor ou fallback legado.

## 1. Objetivo

Integrar o Streamlit do TCC ao agente registrado, com apresentação tipada e continuidade por sessão. Sem avaliação científica ou deploy.

## 2. Estado inicial

Branch `test/container-runtime-smoke-v1`, HEAD `39f866c1b788ea8a5701bc74efee2aaf0812e5d7`, árvore limpa. Todos os comandos exigidos anteriores à alteração em [initial_audit.json](initial_audit.json). Branch `feat/tcc-ui-integration-v1` criada exatamente desse HEAD.

## 3. UI anterior

Toolkit genérico; herança do default via /info; seletores de agente/modelo; /history por query thread; identidade compartilhável pela URL; ferramentas/status e exceções expostos; renderização só de content, sem fontes tipadas.

## 4. UI depois

Mesma aplicação Streamlit com título/escopo UFPI, chat e botão Nova conversa. Fontes em expander. Removidos controles de agente/modelo, arquitetura remota, compartilhamento/history e feedback remoto do toolkit. `.env` do cwd de lançamento documentado em code/ e env de processo preservados; sem redesign.

## 5. Agente utilizado

Constante `TCC_AGENT_ID=chatbot_ufpi_integrated_v1`. AgentClient existente, get_info=False e update_agent explícito verify=False; não há seletor, modo legado ou escolha por query/session_state. 12/12 requests reais ao endpoint explícito /chatbot_ufpi_integrated_v1/stream.

## 6. Default backend

DEFAULT_AGENT=chatbot_ufpi_v2. Código do registry/backend intacto; /info real e teste obrigatório confirmam. Integrado permanece experimental/non-default internamente, sem rótulo técnico na UI.

## 7. Session identity

Identidade declarada por sessão, sem autenticação. Migração de estado legado incompatível gera nova thread uma vez e limpa mensagens/transientes. Query IDs não são adotados.

## 8. User ID

UUID gerado na sessão; estável entre mensagens e Nova conversa; sem exposição visual ou compartilhamento de URL.

## 9. Thread ID

UUID por conversa. 10/10 requests da conversa original conservaram usuário/thread. Não é regenerado a cada mensagem.

## 10. Nova conversa

Novo thread_id, mensagens locais vazias e transientes de erro/feedback limpos; mesmo usuário e agente. 1/1 ação real observada; checkpoints antigos não são apagados.

## 11. ChatMessage typed dispatch

normative_result → grounded_followup_result → calculator_result → regular. Exclusividade revalidada pelo schema existente antes de armazenar a mensagem. Payload inválido resulta em erro público seguro.

## 12. Direct renderer

Conteúdo normal, sem fontes/status/provenance. Greeting e repetição sem memória após nova conversa passaram.

## 13. Normative renderer

ANSWER exibe message.content sem reescrita nem síntese. Spy AppTest confirma argumento byte a byte; o componente Markdown do Streamlit remove whitespace externo na representação de tela, comportamento documentado da biblioteca já utilizada. accepted/regenerated/fallback não viram rótulos públicos.

## 14. Official references

Somente NormativeReference.references. display_text e validated_subdivision estruturados; identidade de todos os campos para dedup visual, sem alterar os objetos. 26/26 referências esperadas mostradas nos probes. AppTest com art.999 em content mostrou nas fontes somente art.68; referências distintas com mesmo display_text e subdivisão foram mantidas. Nenhum link inventado ou chunk_id exibido.

## 15. Temporal information

Somente caption Consulta histórica quando temporal_intent=historical; sem inferir vigência. Outros dados temporais não recebem apresentação nova nesta V1. Sem JSON/provenance/constraints/core_status/estratégia brutos.

## 16. Clarification

Pergunta normal por message.content; sem fontes vazias/status técnico. Resposta seguinte mantém a mesma thread e usa a continuidade real do backend.

## 17. Normative error

Conteúdo público do contrato/safe_message, sem error_code, audit ou traceback. Validado por AppTest controlado.

## 18. Grounded follow-up

Conteúdo com indicação discreta Reformulação baseada na resposta normativa anterior. Fontes herdadas do contrato, mesma correlação verificada tecnicamente e não exibida. REPEAT/SUMMARY reais: 2/2; REPHRASE também coberto no AppTest. Nenhuma busca da UI.

## 19. Calculator

Resultado simples, 4 e 15/11/2026 nos probes reais. Sem fontes nem informação normativa: 2/2.

## 20. Calculator error

safe_message em warning, sem códigos/stack/norma. Divisão por zero coberta por AppTest.

## 21. Streaming

Um ChatMessage AI completo, sem cursor ou tokens artificiais. Retenção só após o stream completo validado; eventos inesperados/duplicados são recusados de forma controlada. DONE consumido pelo AgentClient existente e não mostrado. RED adicional comprovou que SSE type=error virava DIRECT; mudança mínima no client agora levanta AgentClientError seguro, sem repassar conteúdo do servidor. Parser de mensagens/tokens e outros métodos do client conservados por AST.

## 22. Rerun/session state

ChatMessage Pydantic completo em messages, sem duplicar o contrato em campos paralelos. 11/11 respostas reais conservaram o dump tipado após rerun; testes conferem fontes e objeto original intactos.

## 23. Unavailable service

503 real antes de SSE no agente sem configuração de provider; UI mostra O assistente está temporariamente indisponível. HTTP500, rede, payload inválido e SSE error têm apresentação segura em AppTest.

## 24. No legacy fallback

Zero chamadas legadas em 12 requests; 0/1 falhas de disponibilidade causaram fallback. Falha não é salva como resposta AI de sucesso.

## 25. History limitation

Sem reconstrução por /history. Estado visual vive na sessão Streamlit; refresh/nova sessão pode perdê-lo e gerar nova identidade. Sem cookies/localStorage ou promessa de histórico persistente completo; checkpoints backend são separados da apresentação local.

## 26. AppTest

24 focused TCC + 8 regressões do entrypoint =32 AppTests aprovados. Fake AgentClient nas unidades; cwd e ambiente isolados. Cobertura inclui exclusividade, fontes, art999, erro503/500, SSE error/DONE, rerun, migração, IDs, nova conversa e configuração .env/env. Sem novo framework.

## 27. Local integration

Python3.11.15/Windows, Streamlit1.40.2 e Uvicorn reais em loopback 18081/18501; processo negativo 18082. AppTest executa o script real com AgentClient HTTP/SSE real; processo Streamlit também respondeu /_stcore/health. Sem verificação em navegador, screenshot ou avaliação mobile. Runtime/factory/graph/core/registry/índice/saver reais; somente settings/provider pelo seam existente são controlados. SQLite e vetor de teste em workspace temporário removido. Serviços encerraram com exit0 e provider fechou; Streamlit foi terminado pelo harness após captura. Sem repetir build/protocolo Docker anterior.

## 28. Probes

[ui_protocol.json](ui_protocol.json) foi congelado antes da execução final:12 casos e hashes de UI/client/harness. [ui_probe_rows.jsonl](ui_probe_rows.jsonl) contém12 observações finais. Nenhum produto/protocolo congelado mudou após os probes. Tentativa anterior com configuração inadequada preservada em attempt_01_env_configuration; não entra no denominador final. Zero tentativas externas nos guards socket/DNS dos dois processos finais; não é captura universal de pacotes.

## 29. Technical metrics

| Métrica | Resultado | Unidade |
|---|---:|---|
| Integrated Agent Selection Preservation | 12/12 | UI requests |
| Typed Message Rendering Rate | 11/11 | successful ChatMessages |
| Official Reference Rendering Rate | 26/26 | structurally unique references per last response |
| Content-to-Reference Parsing Count | 0/26 | rendered references; source audit and art999 AppTest |
| Grounded Follow-up Rendering Rate | 2/2 | grounded UI probes |
| Calculator Rendering Rate | 2/2 | calculator UI probes |
| Thread Continuity Rate | 10/10 | requests in original conversation |
| New Conversation Thread Reset Rate | 1/1 | new conversation action |
| Legacy Fallback Count | 0/1 | unavailable integrated service probe |
| Private Field UI Leakage Count | 0/12 | observed UI screens |
| UI Probe Success Rate | 12/12 | frozen UI cases |

Denominadores finitos e observações sobrepostas; não somar taxas. Contagem0 significa zero ocorrências na unidade indicada.

## 30. Negative results

[negative_results.json](negative_results.json) registra RED17/5, ajuste de fixture inicial21/1, diferença de whitespace do Markdown, RED da revisão2/30, tentativa local11 casos com indisponibilidade mal configurada e full inicial1failed/1000passed/12skipped por variável do runner. Raw logs preservados. PowerShell classificou stderr informativo do AppTest como NativeCommandError; o Python final chegou ao print12/12 após cleanup, e evidence_audit valida todos os artefatos/hashes independentemente. Helpers de preparação tiveram uma falha de quoting e stdout cp1252; sem mudança de produto decorrente. Nenhum tuning após os probes.

## 31. Limitations

Sem validação jurídica, relevância de embeddings, provider/credenciais reais, autenticação, carga, verificação em navegador/mobile, persistência de histórico visual após refresh, PostgreSQL/Mongo ou deploy. Vetor fixo e geração controlada exercitam encadeamento técnico. Não se afirma prontidão de produção nem validação das respostas pelo frontend. Primeira tentativa local leu configuração do checkout; nenhuma chave foi impressa, versionada ou utilizada por provider externo. Execução final isola explicitamente .env e usa somente placeholders.

## 32. Decisions

[decision_log.jsonl](decision_log.jsonl):18 decisões públicas. [execution_log.jsonl](execution_log.jsonl):48 eventos até a preparação do commit final. Revisão de código encontrou1important e2minor, todos corrigidos; zero pendentes em [review_findings.json](review_findings.json).

## 33. Preservation

1217 arquivos iniciais; 1213 idênticos; quatro alterações existentes autorizadas: streamlit_app.py, client/client.py (somente erro SSE), tests/app/conftest.py e tests/app/test_streamlit_app.py. Novos testes/evidências adicionados. Core normativo, agent, Router, temporal, retrieval, VersionFilter, grounding, StructuredOutput, memory, calculator, ChatMessage/schema, emissão/projetor tipados, service, runtime, DEFAULT_AGENT, registry, corpora, pyproject/lock, container configs e todos os resultados anteriores permanecem idênticos. Outros métodos do AgentClient idênticos por AST. Índice507/507 IDs/documentos/metadados/embeddings float32 idênticos; SHA256 `ab253a24b756d9f3d3e05aeb49220798b08d947704112327fd894a577bb2b38a`. Sem reindexação ou metadata update.

## 34. Tests

Focused final314passed/5warnings: UI32,client9,service24,typed51,conversation87,calculator111. Contagens por classe em [test_counts.json](test_counts.json), comandos/cwd/timestamps em [test_results.json](test_results.json). Seleções sobrepostas não são somadas à full. Full final inclui rag_baseline/runtime/legacy app/integration; Docker opt-in permanece skipped.

| Execução | Resultado real |
|---|---|
| tdd_red | 21 failed, 1 passed in 2.01s |
| tdd_red_contract | 17 failed, 5 passed in 4.74s |
| tdd_green | 3 failed, 19 passed, 1 warning in 1.50s |
| tdd_green_final | 29 passed, 1 warning in 1.60s |
| review_regression_red | 2 failed, 30 passed, 1 warning in 1.73s |
| review_regression_green | 41 passed, 2 warnings in 1.87s |
| full | 1 failed, 1000 passed, 12 skipped, 5 warnings in 90.85s (0:01:30) |
| focused_final | 314 passed, 5 warnings in 32.74s |
| full_final | 1001 passed, 12 skipped, 5 warnings in 107.14s (0:01:47) |

Ruff check/format-check de produto/testes/scripts e diff --check/staged em verification.json após fechamento. Warnings completos nos logs: fixture deliberadamente inválida Pydantic, AsyncMock legado, depreciação de dependência e TestClient timeout.

## 35. Commits

- `4ebca8720de668262274ea8b6eda637f3a12aad2` — test: define tcc integrated ui boundaries
- `9b734f707d861e8a21067797bae8f842d4098c64` — feat: use integrated agent in tcc interface
- `699f26b8b2bacb15d262810326d9e52ee2faf66b` — fix: preserve tcc configuration and safe stream errors

Sem agent selector, fallback legado, default change, tuning, deploy ou publicação de imagem.
