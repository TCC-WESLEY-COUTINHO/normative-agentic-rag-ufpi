# Instalação e execução local

O protótipo usa a condição **v3.4** (`cited_v3`, corpus `duas-regulacoes-v4`) e a camada conversacional A″-J v2. É um protótipo de pesquisa, sem vínculo de serviço oficial com a UFPI. Consulte os [resultados e limitações](RESULTADOS.md).

## Requisitos e configuração

- Docker com Compose v2: Docker Desktop no Windows/macOS ou Docker Engine no Linux/WSL 2.
- Chave da OpenRouter: as chamadas de geração, interpretação, roteamento e embeddings têm custo para o titular.
- Índice Chroma no diretório `.local/index/`, com a coleção `ufpi_duas_regulacoes_setor_v4`.
- Para desenvolvimento sem Docker: Python 3.12 e `uv`.

Na raiz do repositório:

```powershell
Copy-Item .env.example .env
```

Em Linux/WSL: `cp .env.example .env`. Preencha `OPENROUTER_API_KEY` e uma senha própria em `POSTGRES_PASSWORD`. O `.env` não deve ser versionado nem copiado para as imagens. O arquivo [`.env.example`](../.env.example) descreve todas as variáveis, inclusive as opções de provedor e de agentes legados.

| Variável | Uso |
|---|---|
| `OPENROUTER_API_KEY` | Credencial do provedor da configuração avaliada |
| `POSTGRES_PASSWORD` | Senha dos checkpoints; deve coincidir com a usada na criação do volume |
| `INDEX_DIR` | Diretório do índice montado pelo Docker; padrão `.local/index` |
| `CHROMA_PERSIST_DIR` | Mesmo diretório do índice na execução sem Docker |
| `INTERFACE_PORT` | Porta da interface; padrão `8501` |
| `AUTH_SECRET` | Bearer da API, quando definido; veja [autenticação](API.md#autenticação) |
| `PROTOTYPE_GIT_COMMIT` | Commit informado ao build para a identidade; sem ele, `unknown` |
| `TCC2_WSL_DISTRO` | Distribuição usada pelo launcher Windows quando utiliza Docker no WSL |

O [compose da demonstração](../compose.demo.yaml) fixa estes valores; entradas homônimas no `.env` não os alteram:

```text
CONVERSATION_INTERPRETER=jev
CONVERSATION_INTERPRETER_CONFIG={"transition_policy":"v2"}
RETRIEVAL_TOP_K=5
ROUTING_MODE=intent_v1
GENERATION_MODE=cited_v3
CORPUS_PROFILE=duas-regulacoes-v4
```

## Construir o índice v4

O índice não é versionado. Pode ser fornecido em `.local/index/` ou em outro diretório indicado por `INDEX_DIR`. Ele deve conter `chroma.sqlite3` e os diretórios de segmentos da coleção v4; a coleção histórica `ufpi_duas_regulacoes_setor` não atende a esse perfil.

Os quatro corpora canônicos estão em [`evaluation/corpora/`](../evaluation/corpora/). Para indexá-los, após configurar o `.env`, na raiz:

```bash
docker compose -f compose.demo.yaml build backend
docker compose -f compose.demo.yaml run --rm --no-deps backend \
  python -m rag_baseline.index --profile duas-regulacoes-v4 --rebuild
```

`--rebuild` reconstrói o índice do perfil selecionado. A operação usa embeddings pagos e exige o mesmo modelo configurado no backend. Sem Docker, a partir de `code/`, depois de `uv sync --frozen`, configure `OPENROUTER_API_KEY` no ambiente ou em `code/.env`: o `.env` da raiz não é carregado automaticamente nesse diretório. Defina também `CHROMA_PERSIST_DIR` para o mesmo diretório de `INDEX_DIR` e execute:

```bash
uv run --frozen python -m rag_baseline.index --profile duas-regulacoes-v4 --rebuild
```

## Subir e parar com Docker

No Windows, a partir da raiz:

```powershell
.\scripts\start-local.cmd
# Para parar, preservando os volumes:
.\scripts\stop-local.cmd
```

No Linux/WSL, use `./scripts/start-local.sh` e `./scripts/stop-local.sh`.

O launcher localiza a raiz, verifica Docker, `.env` e índice sem imprimir segredos, executa `docker compose -f compose.demo.yaml up --build -d --wait` e aguarda os healthchecks. No Windows, tenta Docker Desktop ou Docker Engine no WSL (distribuição padrão `Ubuntu-24.04`); no WSL, mantém uma sessão minimizada para evitar o encerramento do Docker ao fechar o último terminal.

A interface fica em <http://127.0.0.1:8501>.

| Serviço | Imagem | Rede |
|---|---|---|
| `postgres` | `postgres:17.10-alpine` | Apenas rede interna, sem porta no host |
| `backend` | `tcc2-prototype-backend` | Sem porta no host; healthcheck exige agente pronto e configuração esperada |
| `interface` | `tcc2-prototype-interface` | Porta publicada em `127.0.0.1:8501` |

Os containers do protótipo executam sem root. Os checkpoints ficam no volume `postgres_data`; o backend cria as tabelas na primeira subida. Os experimentos usaram SQLite, e esse armazenamento não integra a configuração comparada. O launcher verifica intérprete, política, modelos, K e endpoint. A imagem inclui os corpora canônicos e os arquivos históricos exigidos pelo registro normativo; o build v3.4 não exige o manifesto congelado da v2.

Para o teste de infraestrutura sem chamadas a provedores, com o backend sem saída de rede:

```bash
docker compose -f compose.demo.yaml -f deploy/compose.smoke.yaml up -d --wait
```

## Desenvolvimento sem Docker

O caminho testado da release é Docker. Os comandos abaixo são o caminho de desenvolvimento documentado; não foram reexecutados nesta atualização de documentação.

No PowerShell:

```powershell
cd code
uv sync --frozen
$env:PYTHONPATH="src"
$env:CONVERSATION_INTERPRETER="jev"
$env:CONVERSATION_INTERPRETER_CONFIG='{"transition_policy":"v2"}'
$env:GENERATION_MODE="cited_v3"
$env:CORPUS_PROFILE="duas-regulacoes-v4"
$env:CHROMA_PERSIST_DIR="..\.local\index"
uv run python ..\deploy\backend\prototype_launcher.py
```

Coloque a credencial em `code/.env` ou no ambiente. A API usa a porta `8080`, configurável por `HOST`/`PORT`. Em outro terminal, também em `code/`:

```powershell
$env:PYTHONPATH="src"
$env:AGENT_URL="http://127.0.0.1:8080"
uv run streamlit run src/streamlit_app.py --server.address 127.0.0.1
```

Sem `CONVERSATION_INTERPRETER`, a camada é a de A′. Com `jev`, mas sem `transition_policy=v2`, a política é v1. Para a geração e o corpus históricos, selecione `GENERATION_MODE=free_text_v2`, `CORPUS_PROFILE=duas-regulacoes` e um índice da coleção correspondente. Veja as [diferenças entre condições](PROVENIENCIA.md#condições-e-tags).

## Outros modos e operação

O guia [Linux e operação](DEPLOY_LINUX.md) concentra os comandos de API isolada (`deploy/compose.api.yaml`), PostgreSQL externo (`deploy/compose.external-postgres.yaml`), provedor compatível (`deploy/compose.openai-compatible.yaml`), backup, logs e diagnóstico. O modo de provedor alternativo usa índice próprio, troca a camada conversacional e informa `evaluated_configuration: false`; seus resultados não foram medidos nesta versão.

Consulte a [API](API.md) para integração e o [roteiro de implantação controlada](tcc2/IMPLANTACAO_AWS.md) para servidor. O roteiro foi executado em uma implantação controlada na AWS (uma instância EC2 com Docker Compose, Caddy com HTTPS e oauth2-proxy com login Google restrito a contas institucionais, além de um acesso de convidado protegido), com a versão v2 em 2026-11-12, atualizada para a v3.4 em 2026-11-20. O acesso não é público.
