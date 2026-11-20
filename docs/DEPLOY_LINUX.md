# Execução local em Linux

Este guia mostra como rodar o protótipo do TCC II na condição v3.4, com geração ancorada em citação, corpus canônico v4 e arquitetura conversacional A″-J v2, numa máquina Linux ou no WSL 2. Os componentes podem ser usados separadamente, de três formas:

| Modo | Serviços | Para quê |
|---|---|---|
| Protótipo completo | backend + interface | Demonstração, com a configuração avaliada (Jev + política v2) |
| Só a API | backend, com porta publicada | Integração com outros clientes por HTTP |
| Provedor compatível com a OpenAI | backend (+ interface), com outro provedor de LLM e embeddings, local (Ollama, vLLM) ou remoto (OpenAI etc.) | Rodar com outra chave ou sem provedor externo. **Não é a configuração avaliada** |

A execução sem Docker também é possível (§6).

Para servidor exposto à rede, veja [`tcc2/IMPLANTACAO_AWS.md`](tcc2/IMPLANTACAO_AWS.md). A API está descrita em [`API.md`](API.md).

## 1. Requisitos

- Linux x86_64 (ou WSL 2) com Docker Engine e o plugin Compose v2 (`docker compose version`).
- 4 GB de RAM livres para o backend (Chroma em processo) e cerca de 3 GB de disco para as imagens.
- Para a configuração avaliada: chave da OpenRouter (geração, embeddings, Scope Gate/Router e Jev). As chamadas são pagas pelo titular.
- Índice Chroma em `.local/index/` (veja §2).

## 2. Configuração

Na raiz do repositório:

```bash
cp .env.example .env
chmod 600 .env
# Edite .env e preencha OPENROUTER_API_KEY e POSTGRES_PASSWORD, por exemplo:
#   POSTGRES_PASSWORD=$(openssl rand -hex 24)
```

O `.env` só é lido pelo backend e nunca é copiado para as imagens. A condição v3.4 e a configuração conversacional são fixadas em `compose.demo.yaml`:

```
CONVERSATION_INTERPRETER=jev
CONVERSATION_INTERPRETER_CONFIG={"transition_policy":"v2"}
RETRIEVAL_TOP_K=5
ROUTING_MODE=intent_v1
GENERATION_MODE=cited_v3
CORPUS_PROFILE=duas-regulacoes-v4
```

Valores com os mesmos nomes no `.env` não a alteram.

**Índice.** Coloque em `.local/index/` um índice com a coleção `ufpi_duas_regulacoes_setor_v4` (`chroma.sqlite3` e os diretórios de segmentos), ou aponte `INDEX_DIR` para ele. Para construir a partir dos quatro corpora canônicos versionados, com custo de embeddings:

```bash
docker compose -f compose.demo.yaml run --rm --no-deps backend \
  python -m rag_baseline.index --profile duas-regulacoes-v4 --rebuild
```

O índice histórico da v2 tinha 507 registros na coleção `ufpi_duas_regulacoes_setor` e impressão digital `a38c9aba…`; essa coleção não atende ao perfil v4.

## 3. Protótipo completo (backend + interface)

```bash
./scripts/start-local.sh      # equivale a: docker compose -f compose.demo.yaml up --build -d --wait
```

Interface: <http://127.0.0.1:8501>.

```bash
./scripts/stop-local.sh       # docker compose -f compose.demo.yaml down (preserva os volumes)
```

- O backend não publica porta no host.
- Os checkpoints das conversas ficam no container `postgres` (volume `postgres_data`), que só está na rede interna do compose, sem porta no host e sem saída para a internet. O backend espera o PostgreSQL ficar saudável e cria as tabelas na primeira subida.
- A imagem inclui as fontes da v3.4 e os corpora canônicos v4; a trava do manifesto congelado da v2 foi removida do build.
- O launcher recusa iniciar com qualquer configuração diferente da avaliada: Jev + v2, os modelos, `RETRIEVAL_TOP_K`, temperatura, limite de tokens e o endpoint da OpenRouter. O log informa os campos que diferem.

**No WSL**, a distro encerra o Docker quando a última sessão termina. Mantenha um terminal do WSL aberto, ou use `scripts\start-local.cmd` no Windows, que abre uma janela de keepalive.

## 4. Só a API

O override `deploy/compose.api.yaml` publica o backend em `127.0.0.1:8080` (variáveis `API_BIND_ADDRESS` e `API_PORT`):

```bash
docker compose -f compose.demo.yaml -f deploy/compose.api.yaml up -d --build --wait backend
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/prototype/identity
```

Para subir também a interface, omita o nome do serviço. Exemplos de chamada em [`API.md`](API.md). Ao publicar em outra interface de rede, defina `AUTH_SECRET` no `.env` (a API passa a exigir `Authorization: Bearer`). O `compose.demo.yaml` já repassa a mesma variável à interface, que envia o cabeçalho nas chamadas ao backend.

Para parar:

```bash
docker compose -f compose.demo.yaml -f deploy/compose.api.yaml down
```

## 4.1. PostgreSQL externo

Para guardar os checkpoints num PostgreSQL fora do compose (por exemplo, um serviço gerenciado), use o override `deploy/compose.external-postgres.yaml`. O container `postgres` não sobe, e o backend conecta no endereço do `.env`:

```bash
cat >> .env <<'EOF'
POSTGRES_HOST=<endereço do PostgreSQL>
POSTGRES_PORT=5432
POSTGRES_DB=tcc2
POSTGRES_USER=tcc2
EOF
# POSTGRES_PASSWORD já está no .env
docker compose -f compose.demo.yaml -f deploy/compose.external-postgres.yaml up -d --build --wait
```

- O banco e o usuário precisam existir. O backend cria as tabelas do checkpointer na primeira subida.
- A conexão usa o `sslmode` padrão do libpq (`prefer`): usa TLS quando o servidor oferece, sem verificar o certificado.
- O PostgreSQL deve aceitar conexões só do servidor do backend (firewall ou grupo de segurança), nunca da internet.

## 5. Provedor compatível com a OpenAI (local ou remoto)

O pipeline normativo usa a API compatível com a OpenAI: `/v1/chat/completions`, com `response_format: json_schema`, e `/v1/embeddings`, com URL e chave configuráveis. O override `deploy/compose.openai-compatible.yaml` aponta geração e embeddings para qualquer provedor desse tipo:

- servidor local: Ollama, ou vLLM atrás de um proxy compatível;
- serviço remoto: OpenAI direta, Groq, Together etc.

As variáveis ficam no `.env`, na seção 2 do `.env.example`:

| Variável | Uso |
|---|---|
| `COMPAT_LLM_BASE_URL` | URL base do provedor. Padrão: Ollama no host, `http://host.docker.internal:11434/v1` |
| `COMPAT_LLM_API_KEY` | Chave do provedor. Padrão: `local`. A `OPENROUTER_API_KEY` do `.env` não é enviada a ele |
| `COMPAT_LLM_MODEL`, `COMPAT_ROUTER_MODEL` | Modelo de geração e, opcionalmente, do Scope Gate e do Router |
| `COMPAT_EMBEDDING_MODEL` | Modelo de embeddings |
| `COMPAT_INDEX_DIR` | Índice gerado com esse modelo de embeddings. Padrão: `.local/index-compat` |
| `COMPAT_CONVERSATION_INTERPRETER`, `COMPAT_CONVERSATION_INTERPRETER_CONFIG` | Camada conversacional. Padrão: `none` (A′) |

**Limitações deste modo**

- **Não é a configuração avaliada no TCC.** Os resultados não foram medidos. A identidade publica `evaluated_configuration: false` e a lista `differences_from_evaluated`.
- **O Jev só existe na Decisions API da OpenRouter.** A camada conversacional padrão passa a ser a de A′ (gramática fechada). Alternativa: o intérprete LLM estruturado com o modelo do provedor (`COMPAT_CONVERSATION_INTERPRETER=structured_llm` e `COMPAT_CONVERSATION_INTERPRETER_CONFIG={"llm_model":"<modelo>"}`), avaliado só na Etapa 6, sem a política v2.
- **O mesmo endpoint precisa servir chat e embeddings.** Ollama e OpenAI servem os dois. Com vLLM, use um proxy que encaminhe cada rota.
- **Cada modelo de embeddings exige o próprio índice.** O índice dos experimentos foi gerado com `openai/text-embedding-3-small` via OpenRouter. Com a OpenAI direta e `text-embedding-3-small`, os vetores devem ser os mesmos, mas a compatibilidade não foi verificada: na dúvida, reindexe.
- **O modelo de geração precisa seguir o JSON schema do Scope Gate e do Router.** Modelos pequenos podem falhar; nesse caso o sistema pede esclarecimento ou responde que não foi possível consultar.

**Exemplo com Ollama no host:**

```bash
ollama pull qwen2.5:7b-instruct
ollama pull nomic-embed-text
cat >> .env <<'EOF'
COMPAT_LLM_MODEL=qwen2.5:7b-instruct
COMPAT_EMBEDDING_MODEL=nomic-embed-text
EOF
```

O Ollama precisa escutar numa interface acessível ao Docker (por exemplo, `OLLAMA_HOST=0.0.0.0`). O container alcança o host por `host.docker.internal`.

**Exemplo com a OpenAI direta:**

```bash
cat >> .env <<'EOF'
COMPAT_LLM_BASE_URL=https://api.openai.com/v1
COMPAT_LLM_API_KEY=<chave da OpenAI>
COMPAT_LLM_MODEL=gpt-4o-mini
COMPAT_EMBEDDING_MODEL=text-embedding-3-small
EOF
```

**Indexar (uma vez por modelo de embeddings) e subir:**

```bash
docker compose -f compose.demo.yaml -f deploy/compose.openai-compatible.yaml run --rm --no-deps \
  backend python -m rag_baseline.index --profile duas-regulacoes-v4 --rebuild
docker compose -f compose.demo.yaml -f deploy/compose.openai-compatible.yaml up -d --build --wait
# acrescente -f deploy/compose.api.yaml para publicar a API
```

**O que foi verificado deste modo, sem provedor disponível:**

- o launcher aceita a configuração e a identifica como não avaliada;
- com índice, o backend fica pronto;
- sem provedor acessível, um turno responde "Não foi possível consultar o provedor normativo." e o serviço continua saudável;
- a reindexação carrega os quatro corpora e falha de forma limpa sem provedor.

Nenhuma resposta foi gerada por outro provedor nesta versão.

## 6. Sem Docker

A partir de `code/`, com Python 3.12 e `uv`:

```bash
cd code
uv sync --frozen
export PYTHONPATH=src
export CONVERSATION_INTERPRETER=jev
export CONVERSATION_INTERPRETER_CONFIG='{"transition_policy":"v2"}'
export GENERATION_MODE=cited_v3
export CORPUS_PROFILE=duas-regulacoes-v4
export CHROMA_PERSIST_DIR="$(pwd)/../.local/index"
export SQLITE_DB_PATH="$(pwd)/../.local/checkpoints.db"   # padrão sem Docker: checkpoints em SQLite
# Para usar PostgreSQL: DATABASE_TYPE=postgres e POSTGRES_HOST/PORT/DB/USER/PASSWORD
export OPENROUTER_API_KEY=...          # ou em code/.env
uv run python ../deploy/backend/prototype_launcher.py      # API em 0.0.0.0:8080 (HOST/PORT)
```

Em outro terminal, também em `code/`:

```bash
export PYTHONPATH=src AGENT_URL=http://127.0.0.1:8080
uv run streamlit run src/streamlit_app.py --server.address 127.0.0.1
```

Para outro provedor sem Docker, exporte `OPENROUTER_BASE_URL`, `OPENROUTER_API_KEY` (a chave desse provedor), `LLM_MODEL`, `EMBEDDING_MODEL`, um `CHROMA_PERSIST_DIR` gerado com esse modelo de embeddings, `CONVERSATION_INTERPRETER=none` e `PROTOTYPE_ALLOW_UNEVALUATED_CONFIG=true`.

Este caminho não foi reexecutado na versão atual; o caminho testado é o Docker.

## 7. Operação

| Ação | Comando |
|---|---|
| Estado | `docker compose -f compose.demo.yaml ps` |
| Logs (sem segredos) | `docker compose -f compose.demo.yaml logs -f backend` |
| Versão em execução | `curl -s http://127.0.0.1:8080/prototype/identity` (modo API) ou `docker exec tcc2-demo-backend-1 python /app/deploy/healthcheck.py` |
| Teste offline (backend sem internet) | `docker compose -f compose.demo.yaml -f deploy/compose.smoke.yaml up -d --wait` |
| Estado das conversas | PostgreSQL no volume `tcc2-demo_postgres_data`; `down -v` o apaga. Backup: `docker compose -f compose.demo.yaml exec postgres pg_dump -U tcc2 tcc2 > checkpoints.sql` |
| Atualizar | `git pull` (ou checkout de uma tag) e `./scripts/start-local.sh`, que reconstrói as imagens |

**Diagnóstico de falhas comuns**

| Sintoma | Causa |
|---|---|
| Backend `unhealthy` com `reason_code` `index_unavailable` ou `index_empty` | Índice ausente ou vazio no diretório montado |
| `provider_not_configured` | `OPENROUTER_API_KEY` vazio |
| `required variable POSTGRES_PASSWORD is missing` | `POSTGRES_PASSWORD` vazio no `.env` |
| Backend reinicia logo após "PostgreSQL" ou `password authentication failed` | Senha do `.env` diferente da usada na criação do volume `postgres_data` |
| Container reinicia com "configuração recusada" | O `.env` alterou modelos, URL ou outro parâmetro da configuração avaliada (o log lista as diferenças). Para outro provedor, use `deploy/compose.openai-compatible.yaml` |
| Interface responde, mas toda pergunta falha | O backend não alcança o provedor (rede, chave ou servidor local) |
