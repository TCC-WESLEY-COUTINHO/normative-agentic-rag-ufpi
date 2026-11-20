# Runtime integrado (`chatbot_ufpi_integrated_v1`)

Montagem do agente do protótipo do TCC II, em `src/rag_baseline/integrated_runtime.py`. É o agente que a interface web chama explicitamente. O `DEFAULT_AGENT` do serviço continua o legado `chatbot_ufpi_v2`, que não é usado pelo protótipo.

## Inicialização

- O lifespan do serviço (`src/service/service.py`) abre o checkpointer (SQLite por padrão, em `SQLITE_DB_PATH`) e monta o runtime uma vez.
- Requisitos: `OPENROUTER_API_KEY` (ou a chave do endpoint compatível configurado em `OPENROUTER_BASE_URL`), o registro normativo e, em `CHROMA_PERSIST_DIR`, uma coleção não vazia do perfil configurado: `ufpi_duas_regulacoes_setor_v4` no padrão (`duas-regulacoes-v4`), construída com `python -m rag_baseline.index --profile duas-regulacoes-v4 --rebuild`.
- A inicialização não indexa, não gera embeddings e não chama provedores.
- Caminhos relativos de `CHROMA_PERSIST_DIR` e `NORMATIVE_REGISTRY_PATH` são resolvidos a partir de `code/`. O registro padrão é `data/normative_registry.json`, ao lado de `code/`, e depende dos corpora de `evaluation/corpora/`.
- `SQLITE_DB_PATH` relativo é resolvido a partir do diretório corrente; prefira um caminho absoluto.

O padrão é a condição v3.4: geração ancorada em citação (`GENERATION_MODE=cited_v3`) e perfil de corpus `duas-regulacoes-v4` (as mesmas quatro resoluções em texto canônico). A condição v2 continua selecionável explicitamente com `GENERATION_MODE=free_text_v2` e `CORPUS_PROFILE=duas-regulacoes`, com o índice `ufpi_duas_regulacoes_setor`. Modelos, `RETRIEVAL_TOP_K`, temperatura e `ROUTING_MODE` vêm de `BaselineSettings` (`config.py`). O campo `model` de uma requisição não substitui os modelos internos.

## Camada conversacional

| Configuração | Condição |
|---|---|
| `CONVERSATION_INTERPRETER` ausente ou `none` | A′: gramática fechada R1 e nível declarado R2; sem nó de interpretação |
| `CONVERSATION_INTERPRETER=jev` | A″-J v1: Jev, Decisions API da OpenRouter, com política de transição v1 |
| `CONVERSATION_INTERPRETER=jev` + `CONVERSATION_INTERPRETER_CONFIG={"transition_policy":"v2"}` | **Camada conversacional A″-J v2, mantida na v3.4** |
| `CONVERSATION_INTERPRETER=structured_llm` | Intérprete por LLM com saída estruturada (`ChatOpenAI.with_structured_output`), no endpoint configurado. Avaliado só na Etapa 6, sem a política v2 |

`ASSISTANT_IDENTITY` (`on` por padrão, ou `off`) controla as respostas fixas a perguntas sobre o próprio assistente (`assistant_identity.py`), dadas em `conversation_entry`, antes da interpretação e do Scope Gate, sem chamada a modelo nem recuperação. O turno é auditado com `conversation_action="ASSISTANT_IDENTITY"` e `action_reason_code="assistant_identity_<intenção>"` (`name`, `identity`, `mission`, `operation`, `creator`); a pendência e o nível declarado são preservados. Com `off`, o detector não é consultado e o grafo é o da v3.4 congelada; use `off` para reproduzir avaliações.

`CONVERSATION_INTERPRETER_CONFIG` aceita os campos de `InterpreterConfig` (`conversation_interpretation/factory.py`): `transition_policy`, `jev_model`, limiares, `llm_model`, `timeout_seconds`, `provider`. Uma falha técnica do intérprete devolve o controle ao comportamento de A′ no mesmo turno.

Na v3.4, a consulta normativa usa `cited_generation.py` para gerar afirmações com citações literais e `citation_verifier.py` / `content_locators.py` para verificá-las antes do guard de saída. A verificação de forma não garante implicação semântica. Veja o [fluxo e os componentes](../README.md#fluxo-de-uma-pergunta).

Na demonstração em Docker, o launcher `deploy/backend/prototype_launcher.py` exige a configuração selecionada da v3.4 (Jev + política v2, `cited_v3`, perfil e coleção v4, modelos, K, temperatura, limite de tokens e endpoint), a menos que `PROTOTYPE_ALLOW_UNEVALUATED_CONFIG=true`. Ele também publica `GET /prototype/identity`.

## Prontidão e falhas

- `GET /health` e `GET /agents/chatbot_ufpi_integrated_v1/readiness` informam `ready`, `index_records` e `reason_code`, sem chamar provedores.
- A prontidão é calculada na inicialização: reinicie o serviço depois de trocar o índice ou o registro.
- Falhas de configuração esperadas (`provider_not_configured`, `registry_invalid`, `index_unavailable`, `index_empty`) deixam o agente indisponível (HTTP 503), sem desviar para outro agente.
- Uma falha do banco de estado da aplicação impede a inicialização.

## Recursos e concorrência

- O runtime usa o checkpointer da aplicação, é dono do cliente do provedor e de leases do Chroma.
- O Chroma 1.0.x não tem `Client.close` público; um adaptador testado encerra os sistemas próprios no último lease. Revise-o ao atualizar o Chroma.
- Supõe-se um lifespan por processo. Turnos simultâneos na mesma thread e carga não foram avaliados.
- O serviço não implementa autenticação de usuários; `AUTH_SECRET` protege apenas a API como um todo.

## Espera na interface

O Streamlit 1.40 não permite substituir a ação de envio de `st.chat_input`. Durante
a espera, um `st.button` nativo com o callback de cancelamento ocupa exatamente a
posição de enviar. O contêiner permanece fora do fluxo, com posicionamento absoluto;
`chat_ui/wait.js` calcula sua posição pelo retângulo do botão nativo e acompanha
redimensionamentos. Nenhum nó gerenciado pelo Streamlit é movido no DOM.

O controle tem alvo de 44 × 44 px, ícone de parar, tooltip “Parar” e nome acessível
“Parar a espera da resposta”. O botão permanece montado, desativado e invisível
quando ocioso, para preservar sua identidade entre reexecuções. Ao terminar a espera,
o envio reaparece; se o foco estava em Parar, ele retorna ao campo de pergunta.

O tempo decorrido aparece junto de “Analisando sua pergunta…”, com largura reservada
e algarismos tabulares. A atualização visual usa o relógio monotônico do navegador;
o polling do resultado continua no servidor, sem acrescentar elementos ao rodapé.
O cancelamento encerra a espera local: o serviço pode continuar processando a
consulta, e respostas tardias não são incorporadas à conversa cancelada.
