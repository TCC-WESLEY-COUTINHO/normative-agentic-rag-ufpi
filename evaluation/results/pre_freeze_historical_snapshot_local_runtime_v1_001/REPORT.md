# TEMP-GRAD-002: redação documental histórica e runtime local

> **Registro histórico.** Configuração, resultados, contagens de testes e estados descritos referem-se à execução documentada, anterior à v3.4. Para a versão atual, consulte o [guia de evidências e reprodução](../../README.md).

A interpretação temporal de TEMP-GRAD-002 foi corrigida e o runtime local foi reconstruído. **A aceitação funcional é parcial: GEN-01 permanece aberto**, pois o lote instrumentado final terminou em fallback, embora o HTTP/SSE separado tenha respondido com segurança. Há distinção entre redação de snapshot e certificação de vigência histórica. Focused final: **765 passed, 2 warnings, 56.92 s, exit 0**. Full suite final: **1259 passed, 12 skipped, 6 warnings, 117.53 s, exit 0**. Índice **507/507 idêntico**. API e UI locais reconstruídas com o código final; as verificações descritas não atestam a experiência visual em navegador nem a correção normativa do conteúdo.

## Git

Estado inicial observado: branch `fix/pre-freeze-explicit-sector-temporal-fallback`, HEAD **`2483c82fd45b3fff8a2e8a74f0ee193c533e72d9`**, árvore limpa. Foram executados status, branch, HEAD, log de 15 commits, diff e diff staged antes das alterações. A branch de trabalho foi criada depois: **`fix/pre-freeze-historical-snapshot-wording`**.


| Commit local | Conteúdo |
|---|---|
| `ae04fedd193969d0744ac602b7a74321b09097bf` | test: reproduce historical snapshot chronology defect |
| `461f6af679b332642c02b3d1bfa863fe7d00793e` | fix: distinguish historical wording from validity certification |
| `3a0c93f72b09c42632041c1d0934235482c3e11e` | fix: prohibit validity certification in documentary answers |
| `4f9f8fe8422191aef9c4adb16f79173b09a57951` | fix: retain snapshot constraints through every regeneration |
| Commit que contém este relatório | test: verify temporal regression and local runtime |

O HEAD produtivo instalado é **`4f9f8fe8422191aef9c4adb16f79173b09a57951`**.

## Root Cause

Pergunta: “Como era a redação do art. 68, §4º da Resolução 177/2012 no regulamento da graduação atualizado em 2023, antes da alteração de 2026?”

O trace real anterior está em `before_trace.json`, executado em thread nova pelo builder normal de chatbot_ufpi_integrated_v1. O processo isolado usou o código do checkout inicial por overlay, pois a imagem anterior ainda não continha todos os fixes anteriores. Os smokes após rebuild usam exclusivamente o código instalado, sem overlay.

Action=NORMATIVE_RAG; Scope=IN_SCOPE_NORMATIVE, uma chamada; setor graduacao, fast path=true, Router=0. O parser **determinístico**, em classify_temporal_intent, procura “em/no ano de + ano” e encontra “em 2023”. Não há LLM classificando o intent temporal.

O mesmo parser reconhece before_amendment=true, article=68, paragraph=4 e norm_ids=[ufpi-177-2012]. O modo é historical, mas requested_year=2023 também é atribuído. O intent não distinguia o ano de uma edição documental de uma pergunta sobre aplicabilidade jurídica naquela data.

Retrieval metadata_exact recupera o art. 68 histórico. VersionFilter.apply conserva esse artigo com historical_preserved e não injeta a ressalva de 2026. **Depois do VersionFilter**, filter_context, em agentic.py, descarta todos os chunks sempre que requested_year existe e marca chronology_unresolved. Assim, a restrição de ano domina a indicação “antes da alteração”, embora ambas tenham sido reconhecidas.

O resultado fica sem evidência elegível para geração; grounding e geração não são executados. A projeção termina ERROR por contexto insuficiente. A evidência estava disponível: o problema era o significado temporal atribuído à consulta e o acionamento de uma política de certificação de vigência sobre uma pergunta documental.

As hipóteses estão em `root_cause.json`: H3 confirma a confusão de naturezas; H5 localiza o descarte posterior ao filtro. H4 é descartada como perda de “antes da alteração”. A política de cronologia insuficiente continua correta para perguntas reais de vigência.

## Semantic Distinction

TemporalIntent mantém os modos anteriores e acrescenta dois campos pequenos:

- historical_wording: identifica pedido de redação histórica com contexto documental positivo.
- document_year: conserva o ano solicitado da versão/edição/atualização como referência documental, sem certificá-lo como data jurídica.

Para TEMP-GRAD-002: mode=historical, before_amendment=true, historical_wording=true, document_year=2023 e requested_year=null. O campo requested_year continua reservado à consulta sobre aplicabilidade em um ano. Grounding recebe automaticamente esses campos por sua projeção estruturada existente.

O reconhecimento exige contexto positivo de edição/atualização ou “antes da alteração”, além de redação/texto/versão. Perguntas mistas com predicados de validade, vigência ou aplicabilidade mantêm o caminho conservador. Não basta conter “redação” ou um ano.

“Essa resolução estava vigente em 2023?”, “Qual regra valia em 2023?” e as variantes mistas testadas continuam com requested_year=2023 e chronology_unresolved. “Como era a redação antes da alteração feita em 2026?” não transforma o ano do ato em data de certificação.

document_year é o rótulo solicitado pelo usuário; não prova sozinho a existência de qualquer edição nesse ano. A instrução de geração limita a resposta ao texto disponível e veda certificar data de edição ou vigência jurídica universal. Nenhum ano, norma ou artigo foi hardcodado.

## RED


| Etapa | Falha demonstrada |
|---|---|
| snapshot_red | 10 failed, 6 passed: redação documental caía em chronology_unresolved |
| mixed_validity_red | 6 failed, 10 passed, 6 deselected: primeira proposta permitia perguntas mistas de validade |
| historical_claim_red | 5 failed, 1 passed, 22 deselected: afirmações de vigência histórica do modelo eram aceitas |
| locator_then_validity_red | 1 failed, 31 deselected: retry de erro de citação introduzia certificação histórica |

O primeiro comando RED foi `python -m pytest -q tests/rag_baseline/test_historical_snapshot_wording.py --tb=short`, executado antes da alteração produtiva. A verificação técnica encontrou o limite das perguntas mistas; as seis negativas foram registradas antes da correção desse limite.

Depois do primeiro rebuild, TEMP-GRAD-002 respondeu operacionalmente, mas o retry real afirmou “estava em vigor” e “permaneceu vigente em parte”. O HTTP/SSE inicial também trouxe “vigente antes da alteração”. Essas capturas foram preservadas; não são apresentadas como conteúdo aprovado.

O guard antigo não detectava essas formas passadas/nominais. O RED inclui replay da resposta real. Após acrescentar a proteção, outro smoke terminou em fallback correto: a primeira geração tinha erro de locator, e seu retry introduziu “em vigor”. Isso provou que o contrato documental precisava ser reafirmado em **todo** retry desse subtipo, não apenas quando o primeiro erro já fosse temporal.

## Fix

Quatro arquivos produtivos mudaram:

- `code/src/rag_baseline/agentic.py`: distingue a natureza documental e fornece enquadramento de geração.
- `code/src/rag_baseline/versioning.py`: somente os dois campos de TemporalIntent; algoritmo VersionFilter preservado.
- `code/src/rag_baseline/normative_output.py`: proteção adicional de vigência histórica, exclusivamente quando historical_wording=true.
- `code/src/rag_baseline/service.py`: reafirma o contrato documental em qualquer regeneração desse subtipo, preservando substância e condições.

A proteção nova cobre as formas passadas e nominais observadas, usando a negação delimitada já existente. A resposta pode dizer o que constava do texto; não pode promover isso a certificação de vigência jurídica histórica. Todas as verificações anteriores do guard permanecem: sua AST é idêntica quando se remove apenas o novo bloco condicionado. Não houve relaxamento de locators ou permissão para citação inventada.

O retry mantém o limite anterior de uma regeneração. Saída ainda inválida termina fallback. Não há sanitização posterior, novo provider/modelo, alteração de evidências ou resposta específica hardcodada. As referências tipadas continuam derivadas dos contratos existentes.

Duas capturas fazem parte das regressões e permanecem imutáveis/versionadas: `local_smokes.json` e `local_smokes_final.json`. Apesar do nome do segundo arquivo, ele é o lote intermediário que revelou o retry incompleto. O lote efetivamente final usa `local_smokes_verified.json`.

## GREEN

| Verificação | Resultado |
|---|---|
| Novo snapshot, negativas, guard e retry + módulo de amendment + guard geral | 96 passed antes da última full |
| Verificação técnica do último reparo | 96 passed, sem novo finding no diff |
| Focused final | **765 passed, 2 warnings, 56.92 s, exit 0** |
| Full final | **1259 passed, 12 skipped, 6 warnings, 117.53 s, exit 0** |
| Ruff check final | All checks passed, exit 0 |
| Ruff format --check | 10 files formatted, exit 0 |
| git diff --check | exit 0 |

O focused abrange intent, VersionFilter, grounding, geração, guards, locators, retry/fallback, Scope Gate, Router V1, setor explícito, integração, transport e memória/pending. TEMP-GRAD-001–005 são executados explicitamente no módulo parametrizado: 002 responde com texto histórico; 001/003/004/005 preservam relação de alteração e norma-base.

Os testes controlam apenas fronteiras externas, usando corpus real, filtering/grounding/guard reais. As gerações reais são observadas separadamente nos smokes. Não se confunde texto retornado por provider controlado com prova de comportamento semântico do modelo.

Resultados intermediários 1249 e 1258 passed foram superados pela última full após a última alteração de retry. Nenhum arquivo produtivo/teste mudou depois da execução final.

Comando full final: `python -m pytest -q -rs --tb=short`, cwd `code/`, registro `full_verified`. O protocolo executa o Python 3.11.15 existente com as dependências locais, sem instalação ou troca de configuração para obter o resultado.

Skips: dois Docker dependem de --run-docker; um exige CITATION_REGRESSION_RUN; nove exigem ROUTER_REGRESSION_RUN. Não contam como pass. Warnings preservados: dois serializers Pydantic de fixtures inválidas; um AsyncMock não awaited no cliente; duas deprecações LangChain/Pydantic __fields__; uma deprecação de timeout do Starlette TestClient.

## Preservation

Índice antes/depois: **507/507**, snapshot lógico SHA256 **`ab253a24b756d9f3d3e05aeb49220798b08d947704112327fd894a577bb2b38a`**.

Registry canônico: **`fbd017d0f080481bb0f89e6809b48a87317d8fc97909e7ec2d40f8240bff25ef`**. Router V2: **`41b3e56fcc83b33998b614ab13fe37f2e71c42e90a5010d3827aea9a62aff186`**, inalterado.


A classe VersionFilter e as funções decide, route_query, reroute, retrieve e filter_context têm AST idêntica ao início. As verificações prévias do guard também permanecem idênticas por AST, além da nova restrição documentada.

Modelos, temperature, embeddings, top_k, collection, chunks, metadata e estratégias não mudaram. Não houve reindexação, re-embedding, mudança de registry/corpus, redesign, deploy externo, freeze, avaliação final, push/pull/merge/rebase/reset/clean.

## Runtime Rebuild

O procedimento existente `local_runtime.py`, da etapa anterior, foi reutilizado. Ele chama Docker Compose para o projeto local ufpi-tcc-local, pelos Dockerfiles existentes, preservando environment e mounts em memória sem salvar segredos.

Comandos: `python .../local_runtime.py build`, `up`, `health` e `integrity`. O Compose recebe a especificação local existente por stdin; build usa os contextos/Dockerfiles oficiais. up usa -d --no-deps --no-build --pull never. Os comandos completos estão no execution_log.

A primeira reconstrução instalou o fix de intent após a suite 1249. A descoberta de certificação histórica exigiu novas regressões, nova full e rebuild. O último runtime contém todos os fixes anteriores, a distinção documental e o reparo completo de retry, no HEAD produtivo indicado acima.

| Serviço | Container (prefixo) | Imagem SHA256 |
|---|---|---|
| agent_service | `74dcfdf4bd6f` | `2adfce60a8dbf78bd9e43d1f23e61fd60cf1d1f424a54d5817f1ac10dc17a673` |
| streamlit_app | `e9a3b7af2e86` | `b97d54f7a9f7a3f8cf238877b50af3b464fc72e6f01ffde8a4c840f903fe5e2c` |

API: **http://127.0.0.1:8080**. UI: **http://localhost:8501**. Ambos healthy; readiness=true; index_records=507. Foram comparados **94 arquivos Python instalados na API e 66 na UI** com o checkout: todos coincidem. IDs, imagens e hashes completos estão em `runtime_integrity.json`.

As tentativas intermediárias do coletor foram registradas: PYTHONPATH inicialmente omitido impediu importar httpx; serialização Pydantic de uma dataclass foi corrigida para asdict; Ruff ajustou imports dos runners no cwd correto. Esses erros não foram atribuídos à implementação. A primeira falha do coletor ocorreu após ABOUT, antes de qualquer provider externo; o lote foi refeito integralmente em threads novas.

## Local Smokes

Cinco casos foram executados no grafo instalado, builder/config/provider/índice normais, InMemorySaver e uma thread nova por pergunta. Não houve overlay nem replay de geração nos lotes locais. Respostas integrais e traces estão nos artefatos; os lotes intermediários não foram descartados. Além do lote final de cinco, foram preservados dois lotes anteriores de cinco, dois smokes HTTP/SSE anteriores e o trace diagnóstico inicial. A tentativa do coletor que parou após ABOUT também está registrada no log.

| Caso | Esperado | Observado | Terminal | Fallback? | Clarification? |
|---|---|---|---|---|---|
| quem é você? | ABOUT direto | ABOUT_ASSISTANT, Scope=0, Router=0 | direct | não | não |
| cidade mais antiga | recusa fora do escopo | OUT_OF_SCOPE, Scope=1, Router=0 | direct | não | não |
| Resolução 658/2024 | pós sem clarification | fast path pós, Router=0, resposta | ANSWER/accepted | não | não |
| TEMP-GRAD-001 adaptado | resposta sem fallback anterior | fast path graduação, Router=0, resposta | ANSWER/accepted | não | não |
| TEMP-GRAD-002 | resposta histórica | intent documental correto; modelo repetiu afirmação temporal rejeitada no retry | ANSWER/fallback | **sim** | não |

**4/5 ações/terminais esperados no lote final.** TEMP-GRAD-002 não falhou por chronology_unresolved: manteve a evidência histórica, mas o modelo descumpriu o contrato documental. O primeiro guard bloqueou “em vigor”, cronologia/eficácia sem suporte e “vigente”; o segundo bloqueou “redação vigente”. Não houve terceira tentativa nem relaxamento. O fallback seguro foi preservado como resultado principal, sem substituí-lo pelo HTTP bem-sucedido.

O teste adicional HTTP/SSE de TEMP-GRAD-002 usa a API reconstruída e a projeção pública oficial. Resultado observado: **ANSWER/regenerated**, com texto histórico seguro e sem fallback/clarification. Somente eventos message e DONE foram recebidos, sem tokens de drafts. O resultado e a resposta integral estão em `http_sse_smoke_verified.json`.

O fluxo final de TEMP-GRAD-002 mantém o art. 68 histórico, com historical_wording=true, document_year=2023, requested_year=null e sem chronology_unresolved. No HTTP/SSE separado, o texto descreve docente efetivo, escolha entre orientadores, designação por portaria e condição do colegiado, sem aplicar a ressalva posterior ao snapshot. A relação parcial com 1056/2026 permanece documentada. Essa observação não certifica correção jurídica de toda formulação gerada.

## Limitations

TEMP-GRAD-001–005 continuam candidatos de desenvolvimento e regressão, usados como DEVELOPMENT/REGRESSION CANDIDATES. Nenhum dataset foi modificado ou promovido a gold. Não é avaliação científica final nem validação jurídica.

A identificação de redação documental é conservadora e delimitada linguisticamente. Pedidos sem contexto positivo ou com linguagem de aplicabilidade mantêm a política anterior. O corpus não permite certificar arbitrariamente qualquer edição ou ano citado pelo usuário.

Guard e geração não são juízes jurídicos/factuais completos. O novo bloqueio cobre os padrões e negações testados, sem prometer compreensão de toda paráfrase. Há um único retry; uma saída que permaneça inválida continua devendo terminar fallback. As falhas intermediárias demonstram essa limitação e permanecem disponíveis.

Os smokes são pequenos, conhecidos e operacionais; não estimam precisão universal. As 40 perguntas históricas continuam expostas ao desenvolvimento. AppTest/full suite não equivalem a aprovação visual de layout, scroll ou timing.

Redesign não foi implementado. A instalação foi apenas local; aparência e conteúdo devem ser revisados pelo usuário.

## Findings Remaining

**GEN-01 — OPEN / Important:** confiabilidade de geração documental ainda intermitente. No lote principal final, o retry manteve “redação vigente” apesar de receber o contrato completo; os guards bloquearam e emitiram fallback. O HTTP/SSE separado entregou uma resposta histórica segura. Esses resultados não permitem declarar TEMP-GRAD-002 integralmente aprovado ou a etapa aceita em todos os critérios.

A verificação técnica confirmou que o bloqueio é correto para a pergunta documental e não encontrou novo bug concreto no último diff. O defeito original de interpretação/chronology_unresolved está corrigido; a confiabilidade do modelo permanece pendente. Os 32 novos testes cobrem os limites e os replays observados, sem garantir conformidade de toda geração real.

As verificações técnicas não constituem validação jurídica ou científica do conteúdo nem atestam a experiência visual da interface. Nenhum outro finding de implementação identificado na revisão está aberto.

Verificação do código das mudanças e artefatos finais: sem novo finding de implementação; GEN-01 confirmado como pendência funcional, não como aprovação do smoke principal.

## Cenários de verificação funcional

Interface: **http://localhost:8501**. Use nova conversa para os casos independentes. A lista abaixo delimita cenários funcionais; não constitui evidência de sua aprovação.

- quem é você?
- pergunta fora do escopo
- Resolução 658/2024 / pós-graduação
- TEMP-GRAD-001
- TEMP-GRAD-002
- pending + nova pergunta
- abrir/fechar referências
- mostrar trecho completo
- scroll
- progressive rendering
