# Código do assistente normativo (`code/`)

Código Python do protótipo do TCC II: pipeline normativo, camada conversacional (A″-J v2), API FastAPI e interface Streamlit (Bisco). Para executar, use o [README da raiz](../README.md) (Docker em um comando) ou o [guia de Linux](../docs/DEPLOY_LINUX.md). A arquitetura está em [`docs/tcc2/ARQUITETURA_A2J_V2.md`](../docs/tcc2/ARQUITETURA_A2J_V2.md); a API, em [`docs/API.md`](../docs/API.md).

## Organização

| Caminho | Conteúdo |
|---|---|
| `src/rag_baseline/` | Pipeline normativo e camada conversacional |
| `src/rag_baseline/conversation_interpretation/` | Intérpretes (Jev, LLM estruturado, regras) e políticas de transição v1 e v2 |
| `src/rag_baseline/integrated_runtime.py` | Montagem do agente `chatbot_ufpi_integrated_v1` ([detalhes](docs/integrated-runtime.md)) |
| `src/service/`, `src/core/`, `src/memory/`, `src/schema/`, `src/agents/` | API FastAPI, configuração, checkpointer, contratos de transporte e registro de agentes |
| `src/streamlit_app.py`, `src/chat_ui/`, `src/static/`, `src/client/` | Interface web e cliente HTTP |
| `tests/` | Testes offline: não chamam provedores; usam intérpretes e provedores roteirizados |
| `legacy/ufpinho/` | Interface anterior, arquivada |

Os principais módulos do pipeline normativo em `src/rag_baseline/`:

| Módulo | Função |
|---|---|
| `conversation_graph.py` | Grafo conversacional |
| `scope_gate.py` | Scope Gate |
| `router.py` | Router V1 |
| `agentic.py` | Grafo normativo |
| `retrieval_policy.py`, `retrieval_service.py`, `lexical_retrieval.py` | Recuperação |
| `versioning.py`, `grounding.py` | VersionFilter e contexto temporal |
| `service.py`, `normative_output.py`, `evidence_support.py` | Geração e validador v5 |
| `output_contracts.py`, `tool_contracts.py` | Contratos |

## Ambiente

```bash
uv sync --frozen          # dependências fixadas em uv.lock (Python 3.12)
```

As variáveis do pipeline estão em `src/rag_baseline/config.py`: `OPENROUTER_*`, modelos, `RETRIEVAL_TOP_K`, `CHROMA_PERSIST_DIR`. As da camada conversacional, `CONVERSATION_INTERPRETER` e `CONVERSATION_INTERPRETER_CONFIG`, estão em `integrated_runtime.py`. Sem as duas últimas, o código executa a camada de A′. Com `jev` e sem `{"transition_policy":"v2"}`, executa a política v1.

## Testes e qualidade

A partir de `code/`:

```bash
PYTHONPATH="src:.." uv run pytest tests -p no:cacheprovider -q
uv run ruff check src tests
```

A raiz do repositório entra no `PYTHONPATH` porque um teste importa `evaluation/`. Resultado da versão atual: 2925 aprovados, 12 ignorados (Docker e regressões opcionais) e 13 `xfail` estritos (defeitos da política v1, mantidos de propósito).

## Ferramentas de terminal (desenvolvimento)

| Comando (com `uv run`, a partir de `code/`) | Função |
|---|---|
| `python -m rag_baseline.index --profile duas-regulacoes [--rebuild]` | Indexa os quatro corpora na coleção `ufpi_duas_regulacoes_setor`. Gera embeddings pelo endpoint configurado, com custo |
| `uvicorn rag_baseline.api:app --port 8080` e `python -m rag_baseline.demo [--setor graduacao\|pos_graduacao\|ambos\|automatico] [--verbose]` | API mínima de consulta (`/query`) e terminal Rich, anteriores à camada conversacional. Úteis para inspecionar recuperação, rota e filtro de versões numa pergunta isolada |

`rag_baseline.chat` é alias de `demo`. As ferramentas de terminal não passam pelo intérprete Jev nem pela memória de conversa.

## Componentes legados

Estes arquivos pertencem ao serviço anterior ao TCC II (agente `chatbot_ufpi_v2`) e são mantidos porque testes do código congelado os verificam:

- `compose.yaml`, `compose.prod.yaml`, `docker/`, `.env.example`;
- `compose.operational.yaml` e `scripts/*_local.*`;
- `scripts/chunks*.py`, que geram os chunks da Resolução 177/2012 usados no trabalho anterior;
- `scripts/create_chroma_db.py`, exemplo do template.

Os agentes `chatbot_ufpi` e `chatbot_ufpi_v2` (e suas ferramentas em `src/agents/tools*.py`) permanecem no código congelado da v2, mas não fazem parte do protótipo: dependiam de um banco vetorial externo que não é versionado nem suportado, então não podem ser executados a partir do repositório.

O registro de agentes (`src/agents/agents.py`) também mantém agentes de exemplo do template original (*agent-service-toolkit*, Joshua Carroll, MIT), que não fazem parte do protótipo. `langgraph.json` aponta para um desses exemplos.
