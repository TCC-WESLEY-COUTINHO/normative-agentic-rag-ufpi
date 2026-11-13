# Correção pré-freeze: Scope Gate, Pending Clarification e Referências Compactas

Execução técnica concluída; sem auditoria independente deste relatório nem revisão visual final registradas. ABOUT_ASSISTANT usa resposta determinística sem provider; consultas substantivas passam por um Scope Gate LLM pequeno antes do Router V1. Pending aceita somente respostas fechadas de domínio. Referências tipadas agora começam em um único bloco, com grupos por resolução e expanders nas folhas.

Os probes reais registraram 16/16 ações esperadas, 11 chamadas de Scope, 8 de Router e 3 de retrieval. A full suite final registrou **1194 passed, 12 skipped, 6 warnings, exit 0**. O índice permaneceu **507/507 idêntico**. Esses resultados verificam comportamento operacional; não são validação jurídica nem avaliação científica final.

## Git

O pedido substituto foi recebido na branch `fix/pre-freeze-conversation-policy-compact-references`, HEAD **`7e2f1f5a7f0d7f3f1c1417dcd87a2af1021c3372`**, com **13 arquivos rastreados modificados, 93 hunks não staged**, além deste diretório de artefatos ainda não rastreado. Não foi presumida árvore limpa. A auditoria anterior à implementação está em `interrupted_work_audit.json`, incluindo status, branch, HEAD, log de 15 commits, diff integral, diff staged e classificação/disposição de cada hunk.

Todos os 93 hunks foram atribuídos à tarefa interrompida (`interrupted-task partial work`), sem alterações de usuário não relacionadas encontradas. O trabalho legítimo anterior, já commitado, foi preservado. A primeira fotografia em `preservation.json` corresponde ao início da tarefa interrompida, então limpa, no HEAD `3358b8f7ed07ebeac1f0462797d52174675405f6`, branch `fix/pre-freeze-ux-answer-reliability-v2`. Ela não deve ser confundida com o estado inicial dirty do pedido substituto, registrado separadamente em `replacement_request_initial`.

Tratamento das alterações parciais:

- Mantidos ABOUT fechado, gramática curta de pending, agrupamento tipado, testes e migração de navegação dos AppTests compatíveis com o pedido novo.
- Removido por patch específico o matcher determinístico de geografia externa. A classificação geral foi substituída pelo Scope Gate LLM; expectativas antigas de zero provider para OUT_OF_SCOPE foram adaptadas para separar Scope de provider normativo.
- Preservadas as duas correções da revisão independente: estado de texto completo após ocultar pais e normalização de pontuação Unicode.
- Scripts operacionais ainda não executados foram auditados antes de adaptação/uso; não foram commitados como implementação parcial. Não houve reset, clean, checkout em massa ou reescrita de histórico.

Branch final: **`fix/pre-freeze-conversation-policy-compact-references`**. HEAD produtivo final: **`4adaaf570c769c44da2677472a1a9bdbf9003a94`**.

| Commit local | Conteúdo |
|---|---|
| `7e2f1f5a7f0d7f3f1c1417dcd87a2af1021c3372` | `test: reproduce conversation routing and compact reference defects` — RED herdado da execução interrompida |
| `926f6c0712f1961a73d82c5eaeef47ef244729cd` | `fix: restore historical scope triage before normative routing` |
| `4adaaf570c769c44da2677472a1a9bdbf9003a94` | `feat: group typed normative evidence in compact disclosures` |
| Commit contendo este relatório | `test: verify pre-freeze scope policy and compact references` |

Arquivos produtivos finais alterados, relativamente ao baseline legítimo `3358b8f`:

- `code/src/rag_baseline/agent_graph.py`
- `code/src/rag_baseline/conversation_graph.py`
- `code/src/rag_baseline/conversation_policy.py`
- `code/src/rag_baseline/integrated_runtime.py`
- `code/src/rag_baseline/scope_gate.py` — novo
- `code/src/rag_baseline/ui_presentation.py`
- `code/src/streamlit_app.py`

São 7 arquivos produtivos e 11 de testes/fixtures. As mudanças de runtime e builder apenas injetam o Gate no grafo de conversa. Nenhum arquivo produtivo/teste mudou após a full suite final; os commits posteriores registram os mesmos bytes e os artefatos.

## Historical Fork Analysis

Foram estudados os blocos relevantes completos de `code/src/agents/chatbot_ufpi.py` e `chatbot_ufpi_v2.py`: identidade/missão, guardrails, escopo, recusa, FASE 0, construção do modelo, injeção de SystemMessage e decisão de tools. Ambos definem o Assistente Acadêmico Virtual da UFPI, especializado no RGG, com triagem anterior à busca. Conhecimento geral e serviços como cardápio do RU/nota específica do SiSU recebem recusa curta, sem busca.

O mecanismo histórico de `wrap_model` associa tools ao modelo e antepõe `SystemMessage(instructions)` via `RunnableLambda`. `acall_model` invoca o modelo selecionado por `get_model`; a presença de tool calls determina a transição para ferramentas ou END. No primeiro agente a busca é SupabaseRagSearch; no segundo há Semantic/Metadata Search. Assim, identidade e FASE 0 eram instruções recebidas pelo LLM antes da decisão de buscar, e não uma lista geral de palavras externas.

| Historical mechanism | Current equivalent | Tratamento | Justificativa |
|---|---|---|---|
| Identidade e missão acadêmica UFPI | ABOUT determinístico e identidade do Scope Gate | REUSED / ADAPTED | Mantém a missão; atualiza a cobertura para normas indexadas de graduação e pós |
| Escopo estrito, incluindo serviços UFPI não normativos | `NormativeScopeGate` antes do Router | REUSED / ADAPTED | Ser sobre UFPI não basta para estar no escopo normativo; classificação passa ao LLM |
| FASE 0 anterior às tools | Decisão tipada IN_SCOPE_NORMATIVE / OUT_OF_SCOPE / UNCERTAIN | REUSED / ADAPTED | Separa escopo geral de domínio acadêmico e mantém dúvida conservadora |
| Recusa curta sem RAG | `OUT_OF_SCOPE_RESPONSE`, emitida após o Gate | REUSED / ADAPTED | Resposta estável, sem responder conhecimento geral |
| Injeção de SystemMessage e modelo com tools | `structured_chat` com prompt próprio e schema mínimo, sem tools | ADAPTED | Gate só classifica; o pipeline atual mantém toda resposta normativa |
| Especialidade exclusivamente RGG | Escopo multi-normativo indexado | DROPPED / ADAPTED | RGG-only excluiria indevidamente pós-graduação e outras resoluções |
| Mapas de títulos/artigos, plano de query e 3–5 buscas obrigatórias | Retrieval atual, registry e VersionFilter | DROPPED do Gate | Não pertencem à triagem; não foram transplantados |
| Instruções Supabase, estrutura antiga de resposta e citações no corpo | Structured Normative Output V2 e transport tipado existentes | DROPPED do Gate | Evita duplicar responsabilidades ou enfraquecer contratos atuais |

Os dois agentes históricos permanecem byte a byte iguais. O prompt antigo inteiro não foi copiado.

## Current Root Cause

**ABOUT_ASSISTANT.** A policy fechada anterior tratava social/calculator/transforms, mas perguntas de identidade seguiam o default normativo. Por isso chegavam ao Router. A nova classe reconhece somente quatro formas fechadas com normalização de acentos, caixa, espaços e pontuação; não intercepta perguntas normativas por conterem “você”.

**OUT_OF_SCOPE.** A arquitetura evoluída encaminhava consultas substantivas ao Router V1, cujo universo de decisão é graduação/pós/ambas/esclarecimento. A FASE 0 histórica não tinha um equivalente antes dele. O matcher externo da execução interrompida cobria um exemplo e não correspondia à arquitetura exigida; foi removido em favor da triagem LLM geral.

**Pending.** A existência de pending fazia o default consumir a próxima mensagem como esclarecimento, reaproveitando pergunta/correlação antigas. Agora somente um full match de resposta curta de domínio continua a operação. Uma nova pergunta substantiva recebe sua própria pergunta e UUID antes do Gate e da facade.

**UI references.** Expanders individuais tipados já existiam, mas ficavam todos no nível principal e ocupavam uma linha por trecho. O agrupamento faltava na apresentação. A solução usa o contrato existente, sem alterar referências nem extrair proveniência do texto da resposta.

## Architecture

```text
Conversation / Action Policy
  ├─ social fechado → resposta direta
  ├─ ABOUT_ASSISTANT → resposta determinística
  ├─ calculator / grounded transforms / cancel existentes
  └─ operação normativa: nova, contextual ou continuação curta de pending
       → Scope Gate LLM (sem tools, retrieval ou resposta substantiva)
           ├─ OUT_OF_SCOPE → recusa determinística; pending preservado
           └─ IN_SCOPE_NORMATIVE / UNCERTAIN
                → Router V1
                → Temporal Intent → retrieval → VersionFilter
                → grounding → Structured Output V2 → guard → retry/fallback
                → ChatMessage final → SSE → apresentação gradual validada
```

**Scope Gate ≠ Router.** O Gate decide somente possibilidade de escopo normativo. Graduação, pós, ambas e necessidade de esclarecimento continuam no Router V1, sem mudança de seu prompt, schema ou implementação. Router V2 não foi promovido nem alterado.

A precedência real preserva cancel explícito de pending antes das outras ações fechadas, como já ocorria. Social, ABOUT e calculator retornam antes do Gate. O full match de domínio é verificado antes dos transforms, mas as classes não se sobrepõem. Transforms e resoluções contextuais existentes foram preservados.

Pequena diferença documentada: a continuação curta também passa pelo Gate, usando a **pergunta original completa**, nunca “pós” isoladamente. Isso protege pending criado antes da instalação do Gate. O custo extra dessa retriagem está contado no probe 12. A correlação original é mantida somente nessa continuação legítima.

`DEFAULT_AGENT=chatbot_ufpi_v2` permanece igual; a interface desta integração continua selecionando `chatbot_ufpi_integrated_v1`.

## Scope Gate

Novo módulo: `code/src/rag_baseline/scope_gate.py`. O `SCOPE_GATE_PROMPT` pequeno adapta identidade, missão, escopo estrito e FASE 0 histórica para normas indexadas de graduação e pós. Não contém mapas de artigos, plano de retrieval ou lista crescente de temas externos. RU/SiSU são exemplos históricos de fronteira no prompt, não um classificador por keywords.

O contrato Pydantic `ScopeClassification` tem somente `decision`, com três literais, modo strict e `extra=forbid`. `ScopeGateResult` transporta decisão, status, número de chamadas e latência. `NormativeScopeGate.classify` faz no máximo uma chamada `structured_chat`, passando a pergunta como dado JSON e o schema mínimo. Não responde, cita, busca ou escolhe domínio; respostas contendo campos extras são inválidas.

Runtime normal: provider HTTPS `openrouter.ai/api/v1`, modelo do Gate e Router **`qwen/qwen3-30b-a3b-instruct-2507`**, mesmo modelo LLM já configurado. Temperature **0.0**, max_tokens **800**, embedding **`openai/text-embedding-3-small`**, top_k **5**, routing_mode **intent_v1** permanecem iguais. Não houve tuning para obter os resultados. SHA256 do novo prompt: `af3fb65518533930490a0c9626ab85cd43bbffe2f2a57f780ad1e9cb09fa54ab`.

Falha de provider → `UNCERTAIN/provider_failure`; JSON/schema inválido → `UNCERTAIN/invalid_response`. Ambas seguem conservadoramente ao Router e registram uma tentativa, sem copiar erro privado para a UI. Builds de compatibilidade/teste sem provider usam `UNCERTAIN/not_configured`, zero chamadas; o runtime normal injeta explicitamente o provider configurado. Cancelamento assíncrono se propaga, sem ser convertido em decisão.

Os probes reais mediram **11 chamadas extras de Scope**. OUT_OF_SCOPE teve uma chamada Scope e zero Router/retrieval em **3/3** ocorrências. ABOUT teve zero chamadas em **3/3** ocorrências. O único UNCERTAIN real seguiu ao Router. Não houve retrieval no próprio Gate.

| Medida | Média | n / população |
|---|---:|---|
| Scope Gate | 1429.85 ms | 11 turns com Scope POST |
| Router | 1149.85 ms | 8 turns com Router |
| Total antes de retrieval | 2478.57 ms | 8 operações encaminhadas ao Router |

As latências por turno estão em `scope_probes.json`. Total pré-retrieval mede do início do turno ao início do primeiro retrieval; quando não há retrieval, até o fim do Router ou do Scope POST. Não inclui geração de resposta. As médias de Scope e Router usam populações diferentes e não devem ser somadas como se fossem uma média pareada.

No total houve **26 POSTs = 11 Scope + 15 normativos**. Os 15 incluem Router, embedding, geração e regeneração; não são 15 respostas. Os 8 Router calls e 3 retrieval calls são contadores distintos. Não foi calculado custo monetário nem número de tokens.

## RED

Comandos abaixo foram executados a partir de `code/`, com o Python 3.11.15 instalado em `PYTHON_RUNTIME/` e dependências existentes em `code/.venv/Lib/site-packages`. `test_results.json` preserva cada comando completo, cwd, exit code, tempo, resumo e testes que falharam; `execution_log.jsonl` preserva a ordem.

| Etapa | Comando (`python -m`) | Resultado antes da correção |
|---|---|---|
| Policy/pending/UI, fase interrompida | `pytest -q tests/rag_baseline/test_conversation_policy_pre_freeze.py tests/app/test_compact_reference_groups.py` | **19 failed, 31 passed**, exit 1 |
| Estado de texto completo, revisão | `pytest -q tests/app/test_compact_reference_groups.py -k hidden_parent` | **2 failed**, exit 1 |
| Pontuação Unicode, revisão | `pytest -q tests/rag_baseline/test_conversation_policy_pre_freeze.py -k unicode_terminal` | **3 failed**, exit 1 |
| Scope Gate, pedido substituto | `pytest -q tests/rag_baseline/test_scope_gate_pre_freeze.py --tb=short` | **40 failed**, exit 1 |

O RED novo do Gate falhou nos testes por componente ainda ausente; não foi erro de coleção. Ele cobre schema mínimo, erros/UNCERTAIN, perguntas externas claras, RU/SiSU, negativos normativos sem UFPI explícita, bypass de ABOUT/social, interrupções e independência da nova operação. O provider é controlado nesses testes: eles verificam contrato e fluxo; a classificação do modelo real é observada nos probes separados.

Os resultados da execução interrompida foram mantidos como histórico. O antigo `full_final` de 1154 passed foi explicitamente marcado como **superseded_by scope_full_final**. O antigo `regression_cases.after` determinístico não é apresentado como arquitetura final; o estado final é `after_scope_gate`.

## GREEN

| Verificação | Resultado |
|---|---|
| Gate isolado, mesmo comando RED | **40 passed**, exit 0 |
| Policy/memory após gramática curta | **96 passed**, exit 0 |
| UI compacta, incluindo estado e compatibilidade | **6 passed**, exit 0 |
| Runtime/injeção do Gate | **112 passed, 2 warnings**, exit 0 |
| Focused final: AppTest, Gate, conversation, memory/transport, agent, calculator, facade, runtime e Router | **539 passed, 4 warnings em 36.90 s**, exit 0 |
| Ruff check final, 18 arquivos de código/testes e 3 runners | **All checks passed**, exit 0 |
| Ruff format --check final | **21 files already formatted**, exit 0 |
| git diff --check | exit 0 |

Comando focused final:

```text
python -m pytest -q tests/app tests/rag_baseline/test_scope_gate_pre_freeze.py tests/rag_baseline/test_conversation_policy_pre_freeze.py tests/rag_baseline/test_conversation_memory_followups.py tests/rag_baseline/test_conversation_memory_transport.py tests/rag_baseline/test_agent_normative_integration.py tests/rag_baseline/test_typed_normative_transport.py tests/rag_baseline/test_calculator_tool_routing.py tests/rag_baseline/test_calculator_transport.py tests/rag_baseline/test_normative_tool_facade.py tests/rag_baseline/test_integrated_runtime.py tests/rag_baseline/test_router_agentic.py
```

As falhas intermediárias não foram ocultadas: 11 testes antigos da UI precisaram navegar os novos controles; uma expectativa antiga consumia “não sei” como domínio e foi ajustada à gramática nova; duas expectativas com datas soltas foram atualizadas porque elas não são respostas de domínio nem intenção de cálculo. Dois testes de runtime contavam qualquer structured call como Router; o fake agora conta Scope e Router separadamente. Os contadores reais também foram medidos separadamente.

As primeiras tentativas de Ruff nos runners apontaram importação/UTC conforme a configuração de `code/`; foram corrigidas somente nesses artefatos. Todos os resultados, inclusive tentativas com o mesmo label e exit 1, permanecem no JSON. O resultado final é a última ocorrência verde, não a primeira ocorrência do label.

A revisão técnica independente encontrou dois P2 de UI/normalização, ambos corrigidos com RED→GREEN. O revisor executou 40 testes do Gate e verificou o cliente OpenRouter real com transporte HTTP simulado: um POST, modelo configurado, schema apenas `decision`, sem tools. Na revisão final dos probes e hashes não restou finding de implementação dentro deste escopo. Registro: `review_findings.json`.

## Probe Matrix

Smoke real pelo builder normal `build_integrated_agent_runtime`, grafo `chatbot_ufpi_integrated_v1`, provider e índice normais, com checkpointer InMemorySaver e projeção tipada oficial `project_integrated_state`. Não usou fake de resposta. Observadores contam chamadas/tempos sem modificar decisões. Execução única: `2026-11-02T04:21:51.314914+00:00` a `04:22:46.255269+00:00`. Os 16 turnos incluem as sequências de pending; não são 16 perguntas independentes.

| # / question | direct action / ação final | scope decision | Scope provider | Router | retrieval | pending effect | final result type |
|---|---|---|---:|---:|---:|---|---|
| 1. quem é você? | ABOUT_ASSISTANT | — | 0 | 0 | 0 | ausente | direct |
| 2. o que você faz? | ABOUT_ASSISTANT | — | 0 | 0 | 0 | ausente | direct |
| 3. quantos anos tem a cidade mais antiga do piauí? | OUT_OF_SCOPE | OUT_OF_SCOPE | 1 | 0 | 0 | ausente | recusa direct |
| 4. qual o cardápio do RU? | OUT_OF_SCOPE | OUT_OF_SCOPE | 1 | 0 | 0 | ausente | recusa direct |
| 5. posso trancar uma disciplina? | NORMATIVE_RAG | IN_SCOPE_NORMATIVE | 1 | 1 | 0 | criado | CLARIFICATION |
| 6. Quanto tempo tenho para terminar o mestrado? | NORMATIVE_RAG | IN_SCOPE_NORMATIVE | 1 | 1 | 1 | ausente | ANSWER / accepted |
| 7. essa resolução ainda vale? | NORMATIVE_RAG | UNCERTAIN | 1 | 1 | 0 | criado | CLARIFICATION |
| 8. Posso cancelar uma disciplina? | NORMATIVE_RAG | IN_SCOPE_NORMATIVE | 1 | 1 | 0 | criado | CLARIFICATION |
| 9. obrigado | SAFE_DIRECT | — | 0 | 0 | 0 | preservado | direct |
| 10. quem é você? | ABOUT_ASSISTANT | — | 0 | 0 | 0 | preservado | direct |
| 11. quantos anos tem a cidade mais antiga do piauí? | OUT_OF_SCOPE | OUT_OF_SCOPE | 1 | 0 | 0 | preservado | recusa direct |
| 12. pós | CONTINUE_CLARIFICATION | IN_SCOPE_NORMATIVE | 1 | 1 | 1 | consumido | ANSWER / accepted |
| 13. Posso cancelar uma disciplina? | NORMATIVE_RAG | IN_SCOPE_NORMATIVE | 1 | 1 | 0 | criado em nova thread | CLARIFICATION |
| 14. Faço mestrado e estou doente. Qual é a diferença entre cancelar uma matéria e trancar o curso? | NORMATIVE_RAG | IN_SCOPE_NORMATIVE | 1 | 1 | 1 | abandonado; nova operação | ANSWER / regenerated |
| 15. Posso cancelar uma disciplina? | NORMATIVE_RAG | IN_SCOPE_NORMATIVE | 1 | 1 | 0 | criado em nova thread | CLARIFICATION |
| 16. cancele | CLEAR_PENDING | — | 0 | 0 | 0 | limpo | direct |

As recusas não responderam idade/cardápio. As duas perguntas normativas novas dos casos 5–6 chegaram ao Router, como exigido, sem exigir resposta jurídica correta como aceitação desta fase. O caso 14 também chegou ao retrieval pela pergunta nova. A resposta final e todas as métricas/correlações categóricas estão em `scope_probes.json`; payloads de modelo e drafts não foram registrados.

`regression_cases.json.after_scope_gate` acrescenta 22 turns com provider controlado sobre o grafo/facade/Router/retrieval reais. Nesse arquivo, `provider_calls` histórico conta somente provider **normativo** e `scope_gate_provider_calls` conta o Gate separadamente; no smoke real `provider_calls` já é a soma. Essa diferença está rotulada para evitar subcontar o custo novo.

## Pending

O helper faz full match da resposta inteira, após normalização, reutilizando `question_sector` para domínio. Aceita graduação/graduacao/na graduação, pós/pos/pós-graduação/pos-graduacao/na pós, ambas/ambos/os dois/as duas. Não aceita frases substantivas apenas por conterem “mestrado”, “graduação” ou “pós”. Não há classificador LLM para consumir pending.

O objeto `PendingClarification` não tem um segundo campo de ID próprio: **correlation_id identifica a operação pendente**. Estados reais antes/depois:

| Operação | pending id / correlation antes | original_question usada no Router | correlation emitida | Resultado |
|---|---|---|---|---|
| Interrupções e depois “pós” (8–12) | `a2b8aec6-0f2d-416f-919a-e629b931a6a8` | `Posso cancelar uma disciplina?`, clarification `pós` | mesma `a2b8aec6-0f2d-416f-919a-e629b931a6a8` | social/ABOUT/OOS preservaram o objeto; após resposta normativa, pending=null |
| Nova pergunta substantiva (13–14) | `d7c2e191-c227-4704-81b4-3586e77f2777` | somente a nova pergunta sobre mestrado/doença, clarification=null | nova `acbb8deb-6c5a-46fb-8dba-d5c3da2bb722` | pergunta antiga não concatenada nem reutilizada; pending=null após ANSWER |
| Cancel explícito (15–16) | `8238ffb5-8164-4abb-ae40-9b449fcc3301` | nenhuma chamada | string vazia | pending=null; Scope/Router/retrieval/provider=0 |

Se uma nova operação normativa terminar em nova CLARIFICATION, ela substitui pending por sua pergunta/correlação; ANSWER/ERROR encerram o pending anterior conforme o fluxo existente. OUT_OF_SCOPE, social e ABOUT retornam antes dessa atualização e preservam integralmente memória/pending. Não há commit intermediário de pergunta/draft na memória conversacional.

## UI

A árvore é construída exclusivamente dos objetos `NormativeReference`: identidade `norm_id`, rótulo `source`, `article`, `validated_subdivision` e `evidence_text`. Subdivisão só aparece se já validada. Nenhum regex extrai norma/artigo de answer, message.content, display text ou evidence. Um teste injeta “Art. 999 da Resolução 123/2099” no answer e comprova que isso não aparece como referência.

A função pura `group_references` preserva a primeira ocorrência de resolução e a ordem relativa dentro de cada uma. Não faz deduplicação: dois trechos do mesmo artigo e até duas ocorrências idênticas continuam acessíveis com chaves distintas. Os objetos/textos originais não são modificados. Agrupar aproxima trechos da mesma resolução; não se afirma preservar a intercalação global original entre resoluções.

O cenário AppTest principal recebe cinco referências na ordem 956/34, 177/112, 956/35, 177/115, 956/38. Fechado, há **um botão/bloco principal**, sem folhas nem evidências na árvore. Ao abrir, aparecem **dois grupos**, primeiro 956/2025 com 34, 35, 38, depois 177/2012 com 112, 115. Todas as cinco referências são alcançáveis. Outro teste preserva sete ocorrências incluindo duplicatas e múltiplos trechos do mesmo artigo.

Os contadores usam **“trechos”**, pois o contrato não garante uma referência por artigo: “2 resoluções / 5 trechos” evita apresentar uma contagem de artigos distintos incorreta. O nível folha continua intitulado `art. N` e eventual subdivisão tipada.

Composição nativa: botão + session state/container no nível principal e por resolução; `st.expander` apenas nas folhas, inicialmente fechado. Foi inspecionada a implementação instalada do Streamlit **1.40.2** e caracterizado em AppTest o erro `Expanders may not be nested inside other expanders`. A composição final evita aninhar expanders. Não houve frontend paralelo nem dependência JS nova.

Chaves incluem conversa/thread, mensagem, norm_id e identidade/posição da referência, evitando colisões mesmo para duplicatas. `_reference_disclosures` preserva abertura dos grupos separadamente dos widgets; `_reference_full_text` mantém a escolha de texto completo quando o pai é ocultado e reaberto. Nova conversa limpa esses estados; respostas diferentes não compartilham toggles. A revisão independente verificou a perda inicial de checkbox e exigiu sua correção RED→GREEN.

Preview de **600 caracteres**, controle “Mostrar trecho completo”, evidência integral original, revelação gradual de **2 palavras / 50 ms / máximo 6 s**, scroll e proteção de texto final foram preservados. Abrir/fechar grupos ou texto completo não chama `st.write_stream` novamente nem o helper de scroll. Somente a resposta final validada segue geração→guard→retry/fallback→ChatMessage→SSE; Scope não é transmitido como texto parcial. O smoke projeta exclusivamente o resultado final e não expôs drafts.

AppTest verifica árvore, estado e chamadas de helpers. Aparência real, altura percebida, timing e posição efetiva de scroll no DOM não têm verificação em navegador registrada. O ambiente local reconstruído está healthy: UI **http://localhost:8501**, API **http://127.0.0.1:8080**, readiness verdadeira e 507 registros. Isso é disponibilização local, não deploy externo.

## Preservation

| Item | Antes | Depois |
|---|---|---|
| Registros do índice | **507** | **507** |
| Snapshot lógico SHA256 | `ab253a24b756d9f3d3e05aeb49220798b08d947704112327fd894a577bb2b38a` | idêntico |
| Registry canônico | `fbd017d0f080481bb0f89e6809b48a87317d8fc97909e7ec2d40f8240bff25ef` | idêntico |
| Arquivo registry SHA256 | `34928be0d8456462804468a339e51394cf15d9ab99370ebdcb5e783d0f36012b` | idêntico |
| 104 arquivos existentes protegidos | hashes em `files_before` | todos idênticos em `files_after` |
| API instalada | 94 arquivos produtivos Python | todos iguais ao checkout usado nos probes |

`preservation.json` registra hashes completos de todos os arquivos considerados e permite verificar cada componente, além da fotografia do índice antes/depois. Exemplos protegidos:

| Componente | SHA256 antes = depois |
|---|---|
| Router V2 `adaptive_router.py` | `41b3e56fcc83b33998b614ab13fe37f2e71c42e90a5010d3827aea9a62aff186` |
| Agente histórico `chatbot_ufpi.py` | `487a7075de3f562d847311038e0cc6c63563156240e33d154b0dbf7a569e8095` |
| Agente histórico `chatbot_ufpi_v2.py` | `782a490ea23fd878bfe346e1f43cef6e7a61d49e8a7ececb0ccb0e28c69d837a` |

Router V1 (`router.py`), Router V2 e seu probe/rank-mass, Temporal Intent (`agentic.py`), VersionFilter (`versioning.py`), grounding, guard/locators (`normative_output.py`, `content_locators.py`), prompts normativos, retrieval/config, registry, os 7 arquivos de data/ e corpora permaneceram byte a byte iguais. Modelos, temperature, embedding, top_k e estratégias dense_vector/metadata_exact/vector_filtered não mudaram. O único prompt novo é o Scope Gate autorizado.

As alterações permitidas no snapshot são exatamente seis arquivos existentes de composição/policy/UI e o novo `scope_gate.py`. O serviço, transport SSE, registry de agentes/default e core normativo não foram reescritos. Os 94 hashes de produção coletados dentro da API real também foram comparados ao checkout, e os dois arquivos de UI instalados foram conferidos. Env/mounts dos containers locais foram preservados sem salvar segredos.

## Full Regression

Comando final, cwd `code/`: **`python -m pytest -q -rs`**. Registro `scope_full_final`: **1194 passed, 12 skipped, 6 warnings em 79.42 s, exit 0**. Abrange também os testes de retrieval, structured output, temporal e serviço fora do recorte focused. Nenhum teste anteriormente verde ficou vermelho na execução final.

Skips preservados, sem contá-los como pass:

- 2 em `tests/integration/test_docker_e2e.py`, linhas 7 e 19: exigem `--run-docker`.
- 1 em `tests/rag_baseline/test_citation_failure_regression.py`, linha 34: exige `CITATION_REGRESSION_RUN`.
- 9 em `tests/rag_baseline/test_router_failure_regression.py`, linha 73: exigem `ROUTER_REGRESSION_RUN`.

Warnings preservados:

- 2 warnings de serializer Pydantic em fixtures deliberadamente inválidas de payload da UI.
- 1 RuntimeWarning de coroutine AsyncMock não awaited em `tests/client/test_client.py::test_astream`.
- 2 deprecações `__fields__` de LangChain/Pydantic em runtime.
- 1 deprecação de timeout de Starlette TestClient em e2e de serviço.

Não foram habilitados probes históricos extras, nem corrigidos warnings fora de escopo. O smoke real com os containers locais e provider configurado é evidência operacional separada dos testes skipped. A verificação de hashes e do diff final confirma que produção/testes permaneceram iguais desde essa suite.

## Limitations

Esta entrega não é validação jurídica, avaliação científica final ou freeze. ANSWER/accepted/regenerated indica passagem pelo contrato operacional e pelos guards, não correção factual/jurídica completa.

Os Scope probes são **development scope regression**, pequenos e conhecidos; não estimam precisão/recall universal, robustez a toda pergunta ou independência científica. Os testes isolados com provider controlado verificam fluxo/contrato; não provam classificação semântica do modelo. As 40 perguntas históricas continuam expostas ao desenvolvimento e inelegíveis como futuro TEST independente não visto. Não foram rerodadas como avaliação final nem usadas para tuning dos fallbacks.

A dupla chamada Scope LLM→Router LLM aumenta custo/latência; foram mensuradas 11 chamadas extras nesta sequência, inclusive retriagem do pending. Otimizar ou fundir essas chamadas pertence a outra etapa e não foi implementado. Provider inválido/indisponível segue como UNCERTAIN, de modo que conhecimento geral pode alcançar o Router sob falha; essa é a política conservadora explícita, auditável e coberta por testes.

Não há revisão visual final registrada. AppTest não certifica aparência nem scroll físico do navegador. As respostas substantivas não têm auditoria independente registrada.

## Findings Remaining

**Nenhum finding técnico de implementação aberto dentro do escopo revisado.** Os dois P2 encontrados foram resolvidos e reavaliados independentemente. Permanecem a limitação de generalização do Gate e a ausência de revisão visual e de conteúdo registrada, descritas acima.

Os defeitos anteriores do diagnóstico de 40 casos — clarificações desnecessárias, decisão inválida de Router, fallbacks e possíveis extrapolações factuais — não foram corrigidos silenciosamente nem declarados resolvidos. Também não se usa o êxito operacional da nova pergunta sobre mestrado/doença como aprovação jurídica da resposta gerada.

Não houve deploy externo, freeze científico, novo final test set, reindexação, alteração de metadata/chunks ou re-embedding.

Artefatos: `REPORT.md`, `test_results.json`, `scope_probes.json`, `regression_cases.json`, `preservation.json`, `review_findings.json`, `interrupted_work_audit.json`, `execution_log.jsonl` e os três runners técnicos reproduzíveis `audit.py`, `runtime_smoke.py`, `local_runtime.py`.
