# Código do assistente normativo (`code/`)

Código Python do protótipo do TCC II na versão **v3.4**. Ele reúne:

- a camada conversacional (intérprete Jev com política de transição v2);
- o pipeline normativo, com **geração ancorada em citação** e **verificação determinística** da resposta;
- a API FastAPI;
- a interface Streamlit (Bisco).

Para executar, use o [README da raiz](../README.md) (Docker em um comando) ou o [guia de Linux](../docs/DEPLOY_LINUX.md). A arquitetura está em [`docs/tcc2/ARQUITETURA_A2J_V2.md`](../docs/tcc2/ARQUITETURA_A2J_V2.md), e a API em [`docs/API.md`](../docs/API.md).

## Fluxo de uma pergunta

Interpretação da conversa (Jev + transição v2) → identidade do assistente → **Scope Gate** → nível de ensino (atalho ou Router V1) → recuperação vetorial (Chroma, K=5) + lexical (BM25) → **VersionFilter** e contexto temporal → **geração com citações literais** → **verificador** → resposta com referências, ressalvas ou abstenção.

## Organização

| Caminho | Conteúdo |
|---|---|
| `src/rag_baseline/` | Pipeline normativo e camada conversacional |
| `src/rag_baseline/conversation_interpretation/` | Intérpretes (Jev, LLM estruturado, regras) e políticas de transição v1 e v2 |
| `src/rag_baseline/integrated_runtime.py` | Montagem do agente `chatbot_ufpi_integrated_v1`, usado pelo protótipo ([detalhes](docs/integrated-runtime.md)) |
| `src/service/`, `src/core/`, `src/memory/`, `src/schema/`, `src/agents/` | API FastAPI, configuração, checkpointer, contratos de transporte e registro de agentes |
| `src/streamlit_app.py`, `src/chat_ui/`, `src/static/`, `src/client/` | Interface web (Bisco) e cliente HTTP |
| `scripts/` | Corpora dos perfis históricos e utilitário que regenera a referência congelada da identidade |
| `tests/` | Testes offline: não chamam provedores; usam intérpretes e provedores roteirizados |

Principais módulos de `src/rag_baseline/`:

| Módulo | Função |
|---|---|
| `conversation_graph.py`, `conversation_policy.py` | Grafo conversacional e política de turnos (pendências, nível declarado, memória) |
| `assistant_identity.py` | Respostas fixas sobre o próprio assistente ("qual é o seu nome?", "como você funciona?"), antes do Scope Gate |
| `scope_gate.py` | Scope Gate: decide se a pergunta é normativa |
| `router.py`, `agentic.py` | Router V1 de nível de ensino e grafo normativo |
| `retrieval_policy.py`, `retrieval_service.py`, `lexical_retrieval.py` | Recuperação vetorial e lexical |
| `versioning.py`, `grounding.py` | VersionFilter e contexto temporal (redação vigente e alterações) |
| `cited_generation.py`, `citation_contracts.py` | Geração v3.4: afirmações com citação literal do trecho recuperado |
| `citation_verifier.py`, `content_locators.py` | Verificador determinístico: citação literal, números e prazos, dispositivo, nível, norma da evidência, negação acrescentada e ato alterador |
| `service.py`, `normative_output.py`, `evidence_support.py` | Montagem da resposta por unidade de regra, ressalvas e guard de saída |
| `output_contracts.py`, `tool_contracts.py`, `calculator_contracts.py` | Contratos de saída, de ferramentas e da calculadora de datas |
| `profiles.py`, `config.py` | Perfis de corpus e configuração do pipeline |

## Configuração

```bash
uv sync --frozen          # dependências fixadas em uv.lock (Python 3.12)
```

Os padrões já correspondem à v3.4. Em `src/rag_baseline/config.py`:

| Variável | Padrão | Efeito |
|---|---|---|
| `GENERATION_MODE` | `cited_v3` | Geração ancorada em citação (v3.4). `free_text_v2` reproduz a geração v2 |
| `CORPUS_PROFILE` | `duas-regulacoes-v4` | Corpus canônico v4, coleção `ufpi_duas_regulacoes_setor_v4` |
| `RETRIEVAL_TOP_K` | `5` | Trechos recuperados por consulta |
| `CHROMA_PERSIST_DIR`, `OPENROUTER_*` | — | Índice local e provedor do modelo de linguagem |

Em `src/rag_baseline/integrated_runtime.py`:

| Variável | Valor da v3.4 | Efeito |
|---|---|---|
| `CONVERSATION_INTERPRETER` | `jev` | Sem ela, executa a camada conversacional de A′ |
| `CONVERSATION_INTERPRETER_CONFIG` | `{"transition_policy":"v2"}` | Sem a política v2, executa a v1 |
| `ASSISTANT_IDENTITY` | `on` | Respostas sobre o próprio assistente. `off` reproduz exatamente a v3.4 congelada ([detalhes](docs/integrated-runtime.md)) |

## Índice

A partir de `code/`, com `CHROMA_PERSIST_DIR` apontando para o diretório do índice:

```bash
uv run python -m rag_baseline.index --profile duas-regulacoes-v4 --rebuild
```

A indexação gera embeddings pelo endpoint configurado e tem custo. O modelo de embeddings deve ser o mesmo usado pelo backend.

## Testes e qualidade

A partir de `code/`:

```bash
PYTHONPATH="src:.." uv run pytest tests -p no:cacheprovider -q
uv run ruff check src tests
```

A raiz do repositório entra no `PYTHONPATH` porque alguns testes importam `evaluation/`. Os `xfail` estritos documentam, de propósito, defeitos conhecidos da política v1.

A equivalência com a v3.4 congelada, com `ASSISTANT_IDENTITY=off`, é verificada contra uma referência gravada a partir da tag `tcc2-cond-v3.4`. Para regenerá-la: `uv run --frozen python scripts/regenerate_identity_off_frozen.py`.

## Ferramentas de terminal (desenvolvimento)

| Comando (com `uv run`, a partir de `code/`) | Função |
|---|---|
| `uvicorn rag_baseline.api:app --port 8080` | API mínima de consulta (`/query`), anterior à camada conversacional |
| `python -m rag_baseline.demo [--setor graduacao\|pos_graduacao\|ambos\|automatico] [--verbose]` | Terminal Rich para inspecionar recuperação, rota e filtro de versões numa pergunta isolada |

`rag_baseline.chat` é alias de `demo`. As ferramentas de terminal não passam pelo intérprete Jev nem pela memória de conversa.

## Componentes históricos

Os agentes `chatbot_ufpi`, `chatbot_ufpi_v2` e `chatbot_ufpi_agentic`, com suas ferramentas em `src/agents/tools*.py`, continuam registrados para compatibilidade com as condições anteriores. O protótipo usa `chatbot_ufpi_integrated_v1`.

Os corpora `scripts/chunks_v2.json` e `scripts/chunks_resolucao_956_2025_v1.json` atendem aos perfis históricos e aos testes. O texto de origem do trabalho anterior está em [`data/RGG_markdown.txt`](../data/RGG_markdown.txt).

A base de engenharia deriva do *agent-service-toolkit*, de Joshua Carroll, sob a [licença MIT preservada](LICENSE). As contribuições do TCC II estão sob a [licença MIT da raiz](../LICENSE).
