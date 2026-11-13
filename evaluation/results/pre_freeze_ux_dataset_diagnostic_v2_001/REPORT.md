**Pre-freeze UX & Dataset Diagnostic V2 — execução diagnóstica concluída**

Esta entrega implementa as correções de apresentação autorizadas e registra uma execução única das 40 perguntas atuais de `data/` no `chatbot_ufpi_integrated_v1`. Não é avaliação científica final nem comprovação de correção jurídica. Os resultados incluem 24 clarificações, 15 terminais ANSWER (8 accepted, 3 regenerated, 4 fallback) e 1 ERROR. As falhas foram preservadas, sem tuning depois do lote.

O sistema local permanece disponível em http://localhost: 8501; API em http://127.0.0.1:8080. Ambos os containers foram reconstruídos somente para o ambiente local e estão healthy, com readiness verdadeira e 507 registros. Isso não constitui deploy externo. O teste operacional usa AppTest real e cliente HTTP/SSE; não há verificação visual no navegador registrada.

**Git e escopo**

Estado inicial: branch `fix/pre-freeze-ux-answer-reliability-v2`, HEAD `20b56b4a642093cffdd25aea79bd369ab836fc32`, árvore limpa. Estado produtivo final/congelado para o lote: `582d2ba7c8e414727f76c187d87570d80f875e76`.

Commits locais desta fase:

- `d80fe528fa51e051a353852d92de075af6201067` — test: reproduce preview speed and temporal presentation defects.
- `9c6dadbda7debc1948d2dc1a4ab408d4e2589e6b` — feat: preview long evidence and pace validated response rendering.
- `582d2ba7c8e414727f76c187d87570d80f875e76` — fix: distinguish indexed corpus scope from explicit validity queries.
- Commit contendo este relatório — test: audit pre-freeze dataset and router behavior.

Arquivos produtivos alterados nesta fase, relativamente ao HEAD inicial:

- `code/src/rag_baseline/agentic.py`
- `code/src/rag_baseline/normative_output.py`
- `code/src/rag_baseline/service.py`
- `code/src/rag_baseline/ui_presentation.py`
- `code/src/streamlit_app.py`

Os 5 arquivos de testes alterados/adicionados estão em `git diff --name-only 20b56b4a642093cffdd25aea79bd369ab836fc32 -- code/tests`. As correções anteriores de frequência, cues “a pós”, referências tipadas e scroll foram preservadas; não foram artificialmente reimplementadas para gerar commits.

**Referências e apresentação gradual**

Antes desta fase, a UI já tinha expanders individuais tipados, mas mostrava todo evidence_text de uma vez e revelava respostas em até 50 fragmentos de 8 ms, com no máximo cerca de 0,4 s de atraso. Agora cada NormativeReference continua com um expander independente, inicialmente fechado, sob “Trechos normativos recuperados”. Não há expander externo com todos os artigos abertos. O título vem do contrato tipado; subdivisão só aparece quando validada. Não há parser jurídico de §/inciso na UI.

Dentro do artigo, trechos com mais de 600 caracteres recebem preview cortado em boundary de espaço/quebra de linha próximo de 600; há controle “Mostrar trecho completo”. A chave inclui conversa, mensagem e identidade da referência, evitando colisões e compartilhamento indevido entre respostas. O evidence_text original permanece intacto. Identificadores internos, scores, embeddings e auditoria não aparecem na UI.

Parâmetros centralizados em `ui_presentation.py`: `REFERENCE_PREVIEW_CHARACTERS=600`, `PROGRESSIVE_CHUNK_WORDS=2`, `PROGRESSIVE_DELAY_SECONDS=0.05`, `PROGRESSIVE_MAX_SECONDS=6.0`. Os fragmentos preservam cada caractere e whitespace. O atraso agregado programado é limitado a 6 s; o tempo real inclui processamento da UI. Para 100–200 palavras, o atraso nominal é 2,5–5 s. Os smokes reais mediram 118 palavras/59 fragmentos em 3,516 s e 156 palavras/78 fragmentos em 3,937 s. Testes usam delay mockado.

O backend continua geração → guard → regeneração/fallback → ChatMessage final → SSE. Somente o texto final validado é revelado. Nos 9 requests operacionais, o cliente recebeu apenas `message`, `DONE`; exposição de raw drafts observada: 0/9. Os testes de transporte e guard da full suite também foram preservados. Os 40 casos do lote passam pela projeção tipada do grafo, sem streaming privado.

Auto-scroll continua limitado a nova mensagem, início e fim da resposta, usando marcador próprio e nonce. Os 9 requests emitiram 3 chamadas cada; rerun de histórico e toggle de trecho completo emitiram 0 scrolls e 0 novas animações. Isso verifica o helper e a árvore AppTest, não prova posição/rolagem efetiva no DOM do navegador; não há validação visual registrada.

**Política temporal**

A mensagem antiga vinha de `render_temporal_statements` aplicado a fatos `STATUS_UNKNOWN` em qualquer resposta: “o conjunto documental utilizado não permite certificar a vigência atual”. A composição agora usa `present_temporal_scope` e o estado estruturado `TemporalGroundingContext`.

Perguntas normativas comuns, com intent current/indeterminate, usam “Com base nas normas indexadas no sistema:”, preservando relações documentadas de alteração/revogação quando existirem. Perguntas explícitas de validade, históricas e comparativas continuam com a composição temporal completa. O sistema afirma a base documental indexada; não converte status desconhecido em vigente, não certifica validade universal hoje e não altera os fatos estruturados ou o VersionFilter.

RED provou que “Essa regra ainda vale hoje?” não era validity. A revisão de código encontrou também “Essa norma está vigente?” e “Essa resolução está em vigor?”. Foi ampliada somente a classificação existente no backend; não há keyword hack de UI. GREEN inclui perguntas comuns negativas, preservação histórica/comparativa e guard que continua rejeitando validade atual sem suporte. `NormativeOutputGuard`, facts, renderer antigo, instruções de geração, grafo e VersionFilter foram comparados por AST/hash e permanecem idênticos ao início desta fase.

Smoke: “como funciona o ajuste de turmas?” pediu nível; após “graduação”, recebeu o prefixo neutro, mas terminou fallback. Assim, o framing está verificado e a resposta substantiva desse smoke continua uma falha aberta. “Essa Resolução 177/2012 ainda está vigente?” também pediu nível; após “graduação”, o estado foi validity e a resposta manteve explicitamente a impossibilidade de certificar vigência atual. A redundância do aviso dentro desse corpo gerado e afirmações substantivas continuam sujeitas a revisão.

**Frequência 75%: trace, causa e resultado**

`regression_cases.json.previous_frequency_before` preserva o trace real anterior completo: pergunta exata, esclarecimento graduação, decisão do Router explicit_graduacao, retrieval dense_vector, 5 referências norm/article/evidence, geração bruta, guard, regeneração, segundo guard, fallback e resultado. Os arts. 112 e 115 da Resolução 177/2012 foram retornados em ranks 1 e 2. O art. 112 explicita frequência inferior a 75% como reprovação; o 115 limita faltas a 25%.

A geração inicial continha “Art. 112, inciso I” e a regeneração repetiu “inciso I”. Ambos os guards retornaram `unvalidated_subdivision`, pois o contrato autorizava citação article-level e não havia subdivision estruturada validada. Portanto, a falha não era retrieval nem um falso positivo ao percentual: era descumprimento do contrato de localização pelo gerador. A correção anterior preservada orienta a geração e o retry a citar apenas a granularidade autorizada e omitir subdivisão não autorizada. O guard continua bloqueando locators indevidos; não foi afrouxado globalmente. Nenhuma resposta/75% foi hardcodada na produção, e embedding/top_k/estratégias não mudaram.

Há regressões para frequência, registro por 60 minutos, reprovação por faltas, regeneração orientada, retry que continua inválido → fallback e evidência insuficiente → abstenção. O guard de localização não constitui juiz jurídico/factual completo, e esses testes não dispensam revisão do conteúdo.

Nesta execução congelada, DATA-GRAD-002 recebeu CLARIFICATION sem retrieval; esse resultado não foi substituído pelo smoke posterior. A regra 75% pode ser comum aos setores, por isso foi excluída do denominador de wrong route estrito e incluída nos suspeitos como answer-expected-but-clarified. No smoke operacional separado, a mesma pergunta pediu nível; a resposta planejada “graduação” gerou accepted: “frequência igual ou superior a 75% ... Art. 112”. O trace e as referências desse resultado estão em `operational_ui_smokes`. Esse êxito contextual não significa que a pergunta fresca seja sempre respondida diretamente nem que os 4 novos fallbacks do lote tenham sido corrigidos.

**“A pós” e conversa**

A correção herdada normaliza a abreviação nominal inequívoca “a pós” para pós-graduação. Foram preservados positivos “como trancar a pós”, “posso trancar a pós?”, “quero fazer a pós”, “como funciona a pós?” e negativos pós-alteração, pós-2025, período pós defesa, efeito pós recurso. O comportamento anterior de pedir graduação/pós/ambas nesse cue é coberto pela regressão RED→GREEN da fase anterior.

Smoke real atual: “como trancar a pós” → ANSWER/pos_graduacao/regenerated; na mesma conversa, “precisa de ira pra passar na pós” → nova ANSWER/pos_graduacao/regenerated sobre IRA, sem pending de trancamento. Não se toma a ausência de exigência localizada como comprovação jurídica de inexistência: a afirmação categórica sobre IRA e procedimentos gerados precisa de revisão.

**Inventário read-only de data/**

| path | classification | records | contains_questions | contains_gold | used_before | eligible_as_future_independent_test |
|---|---|---:|---|---|---|---|
| `data/backend_doc.md` | UNKNOWN | 1 | não | não | historical_documentation | não |
| `data/normative_registry.json` | NORMATIVE_REGISTRY | 4 | não | não | True | não |
| `data/prompt_v2.md` | LEGACY_DATA | 1 | não | não | historical_documentation | não |
| `data/questoes_para_avaliar_o_agente.md` | EVALUATION_DATASET | 20 | sim | referência candidata em prosa | True | não |
| `data/questoes_para_avaliar_o_agente_pos_graduacao.md` | EVALUATION_DATASET | 20 | sim | referência candidata em prosa | True | não |
| `data/REGULAMENTO_GERAL_DA_GRADUAÇÃO_-_177.2012_atualizada_2023_para_site_1_.pdf` | CORPUS | 1 | não | não | True | não |
| `data/RGG_markdown.txt` | CORPUS | 1 | não | não | True | não |

O inventário contém os 7 arquivos, extensões, bytes, SHA256, esquema/chaves, contagem/unidade de registros, propósito, referências no código/testes e histórico. PDF: 93 páginas; texto RGG: 376 marcadores de artigo (não equivalem a registros de dataset). JSON registry: 4 normas. `backend_doc.md` é documentação de API, categorizada UNKNOWN porque não há classe específica de documentação entre as autorizadas; `prompt_v2.md` é documento histórico, não dataset nem prompt exportado pelo diagnóstico.

As duas bancadas têm 20 perguntas cada, campos extraíveis item_number, question e resposta de referência em prosa. Não possuem expected_domain/norm/article/facts estruturados nem revisão independente comprovada. Esses campos de origem permanecem null no lote. Não há GOLD_DATASET validado em data/. As referências candidatas da graduação contêm citações inconsistentes, por exemplo a frequência citada como 137 na prosa versus 111/112 no corpus; números da prosa não foram promovidos automaticamente a gold.

Gold estruturado **candidato** foi localizado fora de data/: `evaluation/datasets/graduacao_v1.json`, `graduacao_v2.json`, `pos_graduacao_v1.json`, `pos_graduacao_v2.json` (20 cada), `router_labels_v1.json` (40) e `routing_v2_candidates_v1.json` (66, splits históricos DEV/TEST sem independência futura). `evaluation/README.md`, `protocol.md`, `protocol_v2.md` e `decisions.md` registram desenvolvimento e a revisão pos_escopo_conhecido_r1.

A auditoria de 139 JSON/JSONL históricos não teve erro de parsing; 38/40 perguntas atuais aparecem literalmente no histórico, e as 2 revisadas da pós também têm exposição em regressões. Há uso em pilotos, comparação/diagnóstico de retrieval, routing e regressões. O histórico de 2025 comprova existência/autoria anterior, mas não basta para afirmar uso em TCC I: `NOT_ESTABLISHED`. Depois desta execução, todas as 40 estão inequivocamente expostas como development/regression diagnostic data, inelegíveis como futuro TEST independente não visto. Ainda podem servir a regressão e desenvolvimento com essa identificação.

**Protocolo e elegibilidade das métricas**

Protocolo técnico fixado antes do lote em `2026-11-02T02:49:04.099323+00:00` (UTC), no HEAD `582d2ba7c8e414727f76c187d87570d80f875e76`. Isso é fixação do protocolo desta execução, não freeze científico. Casos SHA256 `ced138c759fa193f98a4f0351fcffe8febf2ccc9554eafedadc297e36a86610f`. Os 7 hashes de data/, 3 de anotações, 93 arquivos produtivos do API, fingerprints, configs e prompt hashes constam em `router_diagnostics.json.protocol`. Não há conteúdo de prompts privados nesses artefatos.

Provider normal configurado: HTTPS openrouter.ai/api/v1, LLM e Router `qwen/qwen3-30b-a3b-instruct-2507`, temperature 0.0, max_tokens 800; embedding `openai/text-embedding-3-small`, batch 64; top_k 5; timeout 30 s; routing_mode intent_v1; collection ufpi_duas_regulacoes_setor; no máximo 1 regeneração. Segredos não foram registrados. O bloqueio automático inicial de egress foi resolvido apresentando a autorização explícita das seções 40–41 do pedido e verificando o destino configurado; a mesma ação foi então aprovada. Não houve contorno da revisão de aprovação.

Execução pelo grafo normal `chatbot_ufpi_integrated_v1`, com mesma configuração/runtime/provider/índice da API, uma thread nova por caso, ordem 20 graduação + 20 pós, sem scope inferido do nome do arquivo, sem follow-up automático, sem retry adicional ou mudança de modelo/prompts/config. O lote observa a chamada e a decisão validada do Router e projeta o resultado tipado. O smoke separado usa API e UI reais. Hashes antes/depois e da árvore final confirmam código e prompts constantes durante e após o lote.

Rotulagem independente do texto: 14 EXPLICIT_POST, 19 AMBIGUOUS_DOMAIN, 7 NO_DOMAIN_BUT_SEMANTIC_CUE; demais categorias 0. AMBIGUOUS_DOMAIN não significa automaticamente “deve clarificar”, como demonstra a frequência compartilhada.

Antes de qualquer resposta, foram associados conservadoramente 36 candidatos de anotação: 20 graduação e pós 001–016 por texto exato e proveniência. Pós 017–020 foram excluídos de scoring, porque a revisão de escopo conhecido invalida transportar silenciosamente labels antigos, mesmo quando 17–18 mantêm a string. Métricas estritas de routing usam 35 (excluem também frequência); 14 expectativas candidatas de clarification; 22 answer-expected para artigos. Labels são históricos/provisórios, não revisão jurídica independente nem o resultado do Router usado como gold de si mesmo. Anotações completas, facts, evidence, alternativas, status de revisão e hashes são preservados separadamente em candidate_annotation.

Alternativas suficientes pré-declaradas: frequência aceita art. 111 ou 112 da 177, ou 20 da 956; nota pós-exame aceita art. 111 ou conjunto 117+118 da 177. Reference Article Hit usa referências finais e pelo menos um hit na alternativa; Recall@k usa candidatos brutos ordenados por rank até k=5, microcontagem sobre a alternativa de maior recall por caso. Clarificações têm 0 hit. Não são métricas de correção jurídica ou factual.

**Resultados diagnósticos — sempre numerador/denominador**

| Métrica | n/d | percentual |
|---|---:|---:|
| Route Accuracy | 26/35 | 74.29% |
| Wrong Route Rate | 8/35 | 22.86% |
| Router Error Rate | 1/35 | 2.86% |
| Unnecessary Clarification Rate | 5/14 | 35.71% |
| Clarification Recall | 12/14 | 85.71% |
| Explicit Domain Route Rate | 9/14 | 64.29% |
| Potential Deterministic Router Bypass Rate | 14/40 | 35.00% |
| Answer Completion Rate | 11/40 | 27.50% |
| ANSWER Terminal Rate | 15/40 | 37.50% |
| Fallback Rate | 4/40 | 10.00% |
| Regeneration Rate | 7/40 | 17.50% |
| Reference Article Hit Rate | 14/22 | 63.64% |
| Gold Article Recall@k | 21/34 | 61.76% |
| Evidence-Found-but-No-Answer Count | 4/40 | 10.00% |
| Concrete Wrong Domain Count | 0/35 | 0.00% |

Route Accuracy 26/35, Wrong Route Rate 8/35 e Router Error Rate 1/35 particionam os 35 candidatos. Wrong Route inclui desacordo de ação/clarificação nos 4 estados grad/post/both/clarify; não significa 8 respostas no setor acadêmico errado. Houve 0/35 wrong concrete domain observado, 8 desacordos válidos e 1 decisão inválida. Erros não são contados como clarificação legítima. Clarification Recall usa 14 labels candidatos independentes; revisão pode invalidar parte dessas expectativas.

Answer Completion 11/40 mede apenas terminal accepted/regenerated, podendo incluir abstenção; não significa 11 respostas juridicamente corretas. 15/40 ANSWER inclui os 4 fallbacks. 7/40 passaram por regeneração (3 recuperadas e 4 fallback). Evidence-Found-but-No-Answer 4/40 significa referências finais elegíveis + fallback; suficiência direta requer revisão. Denominadores e limitações estão em cada métrica JSON.

Router chamado 40 vezes para 40 perguntas normativas; ser chamado não é defeito na arquitetura atual. 14 queries têm domínio explícito, 19 são domain-ambiguous por texto e 7 têm cues sem domínio explícito. 24 clarificações legítimas observadas: 23 ambiguous_academic_level e 1 insufficient_scope_signal. Das 14 explícitas, 5 clarificaram desnecessariamente e 9 routearam para pós. Houve explicit_graduacao 4, explicit_pos 11 e invalid_model_decision 1. Latência média medida do Router: 2,214 s; por caso: 5,453 s. 14/40 são candidatos a eventual bypass determinístico, apenas para análise futura; nenhum bypass foi implementado nem efeito de um bypass foi simulado como resultado real.

**Todos os casos suspeitos identificados**

| case_id | question | expected candidato | observed/core | reason | why_suspicious |
|---|---|---|---|---|---|
| DATA-GRAD-002 | Qual é a frequência mínima que eu preciso ter nas aulas para não ser reprovado por falta? | answer | clarify/None | ambiguous_academic_level | candidate_expected_answer_but_clarified |
| DATA-GRAD-003 | Fui reprovado por média, mas minha nota parcial foi 5,0. Eu tenho direito ao Exame Final? | graduacao | clarify/None | ambiguous_academic_level | candidate_route_or_action_disagreement, candidate_expected_answer_but_clarified |
| DATA-GRAD-004 | Qual é a nota mínima que eu preciso para ser aprovado depois de realizar o Exame Final? | graduacao | graduacao/fallback | explicit_graduacao | eligible_evidence_but_conservative_fallback_candidate |
| DATA-GRAD-011 | O que é a Láurea Universitária e quais são os requisitos de excelência para recebê-la? | graduacao | clarify/None | ambiguous_academic_level | candidate_route_or_action_disagreement, candidate_expected_answer_but_clarified |
| DATA-GRAD-017 | Se eu quiser fazer matérias de períodos à frente do meu (adiantamento), eu tenho prioridade na hora da matrícula? | clarify | graduacao/fallback | explicit_graduacao | candidate_route_or_action_disagreement, eligible_evidence_but_conservative_fallback_candidate |
| DATA-GRAD-020 | O que o professor tem que apresentar no primeiro dia de aula? | clarify | ERROR/None | invalid_model_decision | candidate_route_or_action_disagreement, router_or_harness_error |
| DATA-POST-003 | Quantos créditos preciso completar no mestrado? A dissertação entra nessa conta? | pos_graduacao | clarify/None | ambiguous_academic_level | candidate_route_or_action_disagreement, candidate_expected_answer_but_clarified, unnecessary_explicit_domain_clarification |
| DATA-POST-004 | Quanto tempo tenho para terminar o mestrado? Dá para pedir mais prazo? | pos_graduacao | clarify/None | ambiguous_academic_level | candidate_route_or_action_disagreement, candidate_expected_answer_but_clarified, unnecessary_explicit_domain_clarification |
| DATA-POST-006 | Meu certificado de inglês tem quatro anos. Ainda vale para comprovar proficiência no mestrado? | pos_graduacao | clarify/None | ambiguous_academic_level | candidate_route_or_action_disagreement, candidate_expected_answer_but_clarified, unnecessary_explicit_domain_clarification |
| DATA-POST-009 | Vou fazer estágio de docência no mestrado. Quanto tempo dura, quantas horas faço e o que entrego no final? | pos_graduacao | clarify/None | insufficient_scope_signal | candidate_route_or_action_disagreement, candidate_expected_answer_but_clarified, unnecessary_explicit_domain_clarification |
| DATA-POST-010 | Já fiz matérias de pós em outra universidade. Como posso aproveitar isso no meu mestrado? | pos_graduacao | pos_graduacao/fallback | explicit_pos | eligible_evidence_but_conservative_fallback_candidate |
| DATA-POST-011 | Faço mestrado e estou doente. Qual é a diferença entre cancelar uma matéria e trancar o curso? | pos_graduacao | clarify/None | ambiguous_academic_level | candidate_route_or_action_disagreement, candidate_expected_answer_but_clarified, unnecessary_explicit_domain_clarification |
| DATA-POST-016 | Sou mestrando e já dei aula. Posso ser dispensado do estágio de docência? Se não, posso fazê-lo fora da UFPI? | pos_graduacao | pos_graduacao/fallback | explicit_pos | eligible_evidence_but_conservative_fallback_candidate |

Os 13 suspeitos estão em `router_diagnostics.json` com guard codes. Em DATA-GRAD-004 houve unallowed_article nos 2 guards; DATA-GRAD-017, unvalidated_subdivision nos 2; DATA-POST-010, unallowed_article+unvalidated_subdivision e depois unallowed_article; DATA-POST-016, unvalidated_subdivision nos 2. Geração bruta, regeneração, offsets/excertos do guard, referências, evidence_text e fallback constam em `dataset_run.jsonl`. Não há evidência de falso positivo que autorize afrouxar o guard nesta execução. DATA-GRAD-020 é ERROR/invalid_model_decision e foi preservado, sem retry seletivo.

Não se declaram as demais perguntas automaticamente corretas: **40/40 sem julgamento de correção** em `review_cases.jsonl`, com pergunta, referência candidata disponível, resposta e evidências. Não houve juiz jurídico LLM ou graduação por similaridade. Ausência de suspeita automática não comprova resposta correta. Os 4 casos pós revisados continuam disponíveis integralmente para revisão apesar da exclusão do scoring.

**Smoke operacional separado**

Seis perguntas principais e 3 respostas de domínio planejadas quando o runtime pediu clarificação; 9 requests totais. Não alteram as 40 linhas nem os denominadores do lote.

| caso | status/core | refs | palavras | reveal real |
|---|---|---:|---:|---:|
| post_trancar | ANSWER/regenerated | 5 | 118 | 3.516 s |
| post_ira_new_question | ANSWER/regenerated | 5 | 156 | 3.937 s |
| frequency_exact | CLARIFICATION/None | 0 | 11 | 0.297 s |
| frequency_scope_clarification | ANSWER/accepted | 5 | 38 | 0.969 s |
| ordinary_ajuste | CLARIFICATION/None | 0 | 11 | 0.297 s |
| ordinary_ajuste_scope_clarification | ANSWER/fallback | 5 | 20 | 0.5 s |
| explicit_validity | CLARIFICATION/None | 0 | 11 | 0.297 s |
| explicit_validity_scope_clarification | ANSWER/regenerated | 5 | 94 | 2.375 s |
| multiple_articles | ANSWER/regenerated | 5 | 87 | 2.219 s |

Todas as 30 referências renderizadas vieram dos contratos tipados, iniciaram fechadas e seus previews coincidiram com os textos tipados. Textos longos expuseram o controle completo; rerun/toggle não reanimaram nem emitiram scroll. Histórico não reanima. Não houve erro de UI nesses requests. Os 9 traces e os resultados de rerun/toggle estão em `regression_cases.json`. A prova é operacional AppTest/HTTP/SSE, sem revisão final de UX/DOM e conteúdo registrada.

**TDD, revisão e verificações**

RED de apresentação: 8 failed / 6 passed, por velocidade, preview e classificação/framing temporal. GREEN focused: 84 passed. A primeira full suite identificou uma expectativa antiga que exigia aviso de vigência em intent indeterminate; foi atualizada para prefixo neutro preservando STATUS_UNKNOWN. A revisão de código encontrou os 2 casos diretos de validade mencionados: RED 2 failed / 12 passed; GREEN temporal 24 passed. Os resultados negativos foram mantidos em `execution_summary.json`.

Full suite final antes do lote: **1099 passed, 12 skipped, 6 warnings em 76,00 s, exit 0**. Ela abrange UI/AppTest, router/normalização, structured output, temporal, transport, conversation, agent, retrieval, calculator, runtime, service/client e rag_baseline. Os skips e warnings permanecem limitações registradas; não são contados como pass. Nenhum arquivo produtivo/teste mudou desde essa suite. A verificação final dos hashes comprovou essa preservação, e os smokes reais verificaram os componentes instalados.

Ruff check final: exit 0, All checks passed. Ruff format --check: exit 0, 10 files already formatted. git diff --check: exit 0. A integridade final verifica 40 IDs/perguntas na ordem, 40 casos de revisão, 35/14/22 denominadores, preservação de fontes e ausência de mudanças após lote. Revisão de código: 1 Important de classificação temporal resolvido com RED/GREEN antes do lote; sem outro finding de implementação aberto nas mudanças revisadas. Isso não encerra os defeitos diagnósticos listados nem certifica a correção jurídica das respostas.

**Preservação e limites finais**

Snapshot lógico do índice antes/depois: **507/507 idênticos**, SHA256 `ab253a24b756d9f3d3e05aeb49220798b08d947704112327fd894a577bb2b38a`. Fingerprint canônico do registry `fbd017d0f080481bb0f89e6809b48a87317d8fc97909e7ec2d40f8240bff25ef`. Hash bruto do arquivo registry é distinto e consta no inventário. Todos os 7 arquivos data/ e 3 fontes candidatas permanecem byte a byte iguais. Os 93 arquivos da imagem API e os 2 arquivos de apresentação da imagem UI foram verificados contra o checkout final. `execution_summary.json` registra snapshots, hashes/AST de componentes protegidos e contagens do inventário inicial/final de arquivos.

Não houve freeze científico, Router bypass, tuning Router V2, reindexação, update de metadata, re-embedding, hardcode de resposta, streaming de raw draft, parsing textual de referências na UI, deploy externo, push, pull, merge, rebase, reset ou clean. Não houve mudança de modelo, temperature, embedding, top_k ou prompts durante/depois do lote. A pequena expansão de intent temporal foi justificada por RED e concluída antes dele. A reconstrução dos containers foi local, para disponibilizar a interface atual.

Limitações: bancada pequena e já exposta, gold candidato sem validação independente/PDF, decisão inválida do Router, 5/14 clarificações explícitas desnecessárias, clarificação de frequência compartilhada, 4/40 fallbacks no lote e fallback adicional de ajuste de turmas no smoke, possíveis extrapolações factuais do gerador apesar de locators válidos, e auto-scroll/timing visual no navegador. Nenhuma dessas falhas foi ocultada ou usada para tuning seletivo.

Artefatos publicados: este relatório e 9 arquivos JSON/JSONL. `decision_log.jsonl` registra decisões de protocolo e escopo; `execution_summary.json`, preservação e suítes; `review_findings.json`, achados e limitações.
