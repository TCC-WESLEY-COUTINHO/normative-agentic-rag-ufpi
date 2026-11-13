# Runtime integrado (`chatbot_ufpi_integrated_v1`)

Montagem do agente do protótipo do TCC II, em `src/rag_baseline/integrated_runtime.py`. É o agente que a interface web chama explicitamente. O `DEFAULT_AGENT` do serviço continua o legado `chatbot_ufpi_v2`, que não é usado pelo protótipo.

## Inicialização

- O lifespan do serviço (`src/service/service.py`) abre o checkpointer (SQLite por padrão, em `SQLITE_DB_PATH`) e monta o runtime uma vez.
- Requisitos: `OPENROUTER_API_KEY` (ou a chave do endpoint compatível configurado em `OPENROUTER_BASE_URL`), o registro normativo e uma coleção `ufpi_duas_regulacoes_setor` não vazia em `CHROMA_PERSIST_DIR`.
- A inicialização não indexa, não gera embeddings e não chama provedores.
- Caminhos relativos de `CHROMA_PERSIST_DIR` e `NORMATIVE_REGISTRY_PATH` são resolvidos a partir de `code/`. O registro padrão é `data/normative_registry.json`, ao lado de `code/`, e depende dos corpora de `evaluation/corpora/`.
- `SQLITE_DB_PATH` relativo é resolvido a partir do diretório corrente; prefira um caminho absoluto.

O perfil de corpus é `duas-regulacoes` (quatro resoluções). Modelos, `RETRIEVAL_TOP_K`, temperatura e `ROUTING_MODE` vêm de `BaselineSettings` (`config.py`). O campo `model` de uma requisição não substitui os modelos internos.

## Camada conversacional

| Configuração | Condição |
|---|---|
| `CONVERSATION_INTERPRETER` ausente ou `none` | A′: gramática fechada R1 e nível declarado R2; sem nó de interpretação |
| `CONVERSATION_INTERPRETER=jev` | A″-J v1: Jev, Decisions API da OpenRouter, com política de transição v1 |
| `CONVERSATION_INTERPRETER=jev` + `CONVERSATION_INTERPRETER_CONFIG={"transition_policy":"v2"}` | **A″-J v2, a configuração avaliada e selecionada** |
| `CONVERSATION_INTERPRETER=structured_llm` | Intérprete por LLM com saída estruturada (`ChatOpenAI.with_structured_output`), no endpoint configurado. Avaliado só na Etapa 6, sem a política v2 |

`CONVERSATION_INTERPRETER_CONFIG` aceita os campos de `InterpreterConfig` (`conversation_interpretation/factory.py`): `transition_policy`, `jev_model`, limiares, `llm_model`, `timeout_seconds`, `provider`. Uma falha técnica do intérprete devolve o controle ao comportamento de A′ no mesmo turno.

Na demonstração em Docker, o launcher `deploy/backend/prototype_launcher.py` exige a configuração avaliada (Jev + v2, modelos, K, temperatura, limite de tokens e endpoint), a menos que `PROTOTYPE_ALLOW_UNEVALUATED_CONFIG=true`. Ele também publica `GET /prototype/identity`.

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
