# Assistente normativo RAG da UFPI: protótipo do TCC II (A″-J v2)

Protótipo de pesquisa de um assistente conversacional baseado em geração aumentada por recuperação (RAG) para consultar quatro resoluções acadêmicas da Universidade Federal do Piauí.

O sistema faz quatro coisas em etapas separadas:

1. decide se a pergunta é normativa;
2. identifica o nível de ensino (graduação ou pós-graduação) e pede esclarecimento quando ele não está claro;
3. seleciona a versão aplicável da norma;
4. verifica a resposta gerada antes de entregá-la.

A versão deste repositório é a **A″-J v2**, a arquitetura selecionada no TCC II. Ela acrescenta à baseline uma camada de interpretação conversacional (Jev) e uma política determinística de transição (v2).

> **Protótipo experimental, para demonstração e avaliação.** Não é um serviço institucional da UFPI nem fonte normativa para decisões acadêmicas. As respostas podem conter afirmações sem suporte no texto das normas; confirme sempre no documento oficial.

## Sumário

1. [Contexto acadêmico](#1-contexto-acadêmico)
2. [Problema de pesquisa](#2-problema-de-pesquisa)
3. [Arquitetura implementada](#3-arquitetura-implementada)
4. [Requisitos e configuração](#4-requisitos-e-configuração)
5. [Execução com Docker em um comando](#5-execução-com-docker-em-um-comando)
6. [Execução local sem Docker](#6-execução-local-sem-docker)
7. [Estrutura do repositório](#7-estrutura-do-repositório)
8. [Versões congeladas](#8-versões-congeladas)
9. [Resultados experimentais, por questão de pesquisa](#9-resultados-experimentais-por-questão-de-pesquisa)
10. [Reprodução das métricas e testes offline](#10-reprodução-das-métricas-e-testes-offline)
11. [Limitações conhecidas](#11-limitações-conhecidas)
12. [Referências](#12-referências)
13. [Licenças, créditos e proveniência](#13-licenças-créditos-e-proveniência)

## 1. Contexto acadêmico

Trabalho de Conclusão de Curso II em Ciência da Computação (UFPI). Autor: Wesley de Sousa Coutinho. Orientador: Prof. Armando Soares Sousa.

Ponto de partida: o protótipo de Melo e Sousa para a Resolução 177/2012 (Regulamento Geral da Graduação), construído com LangGraph. Este trabalho amplia o acervo para quatro resoluções e trata de três problemas que a proximidade semântica não resolve:

- **Nível de ensino:** graduação e pós-graduação têm regras próprias e numeração de artigos coincidente.
- **Versão:** a Resolução 658/2024 foi revogada, e o art. 68, § 4º, da 177/2012 foi alterado.
- **Suficiência:** o modelo pode acrescentar condições, prazos ou afirmações de vigência ausentes do texto.

O código anterior não foi reescrito do zero. A proveniência está na seção 13.

## 2. Problema de pesquisa

> Como se comporta, e com quais limitações, um assistente para normas universitárias quando as decisões de escopo, nível de ensino e versão são separadas da geração da resposta, e esta é verificada antes da entrega?

| Questão | Tema |
|---|---|
| QP1 | Escopo e nível de ensino |
| QP2 | Esclarecimento |
| QP3 | Versão normativa |
| QP4 | Verificação da resposta |
| QP5 | Percepção de estudantes |

Os resultados estão na seção 9 e, em detalhe, em [`docs/tcc2/AVALIACAO_TCCII_JEV_V2.md`](docs/tcc2/AVALIACAO_TCCII_JEV_V2.md).

## 3. Arquitetura implementada

Diagrama e detalhes: [`docs/tcc2/ARQUITETURA_A2J_V2.md`](docs/tcc2/ARQUITETURA_A2J_V2.md).

```
Interface web (Streamlit) ─► API FastAPI ─► grafo conversacional (LangGraph)
   memória da thread ─► interpretação Jev (Runnable LangChain) ─► política de transição v2
   ─► política de conversa e pendência (R1/R2) ─► Scope Gate ─► nível declarado ou Router V1
   ─► recuperação (Chroma, K=5, BM25 complementar) ─► VersionFilter ─► contexto temporal
   ─► geração ─► NormativeOutputGuard v5 (uma nova tentativa ou resposta de contingência)
   ─► resposta com referências normativas tipadas
```

- **LangGraph:** orquestra dois grafos.
  - Conversacional, com checkpointer LangGraph (PostgreSQL na demonstração; SQLite nos testes e experimentos): `conversation_entry` → `conversation_interpretation` (Jev + política v2) → `conversation_turn`. O nó `conversation_turn` aplica a política de conversa, chama o Scope Gate e aciona o pipeline normativo pela `NormativeRagFacade`.
  - Normativo: `route_query` → `clarify`/`reroute` → `retrieve` → `version_filter` → `generate`.
- **LangChain:** o intérprete é um `Runnable` (`RunnableLambda`), desacoplado do provedor. O grafo funciona com qualquer `Runnable` compatível, inclusive um roteirizado nos testes.
- **Jev:** modelo `typesafe/jev-1.14`, chamado pela Decisions API da OpenRouter (versão alpha). Lê a mensagem e a pendência e classifica a intenção: esclarecimento, pergunta nova, declaração de nível, mista ou incerta.
- **Memória e política v2:** a pendência e o nível declarado ficam por thread, no checkpointer. A política v2 decide de forma determinística, a partir da leitura do Jev, se retoma a pergunta pendente, trata a mensagem como pergunta nova ou pede esclarecimento. Ela nunca consome uma pergunta nova como resposta, não usa o nível de terceiros e não retoma a pendência depois de um cancelamento.
- **Scope Gate e roteamento:** o Scope Gate classifica a mensagem como normativa, fora de escopo ou incerta, sem escolher o nível. Um nível ou norma citados explicitamente dispensam o Router V1 (`intent_v1`), que decide entre graduação, pós, ambas ou pedido de esclarecimento.
- **Chroma e recuperação:** coleção `ufpi_duas_regulacoes_setor`, com 507 registros de artigo das Resoluções 177/2012, 1.056/2026, 956/2025 e 658/2024. Embeddings `openai/text-embedding-3-small`. Estratégias `dense_vector`, `metadata_exact` e `vector_filtered`.
- **VersionFilter:** aplica o registro normativo declarativo (`data/normative_registry.json`). Exclui normas revogadas, substitui a redação alterada e preserva a redação histórica quando ela é pedida. Separa ano documental (`document_year`) de aplicabilidade (`requested_year`).
- **NormativeOutputGuard v5:** regras programáticas sobre norma e artigo autorizados, subdivisões, afirmações temporais e números sem suporte. Permite no máximo uma nova tentativa; persistindo a violação, entrega uma resposta de contingência. Opera sobre a forma do texto, não sobre o sentido.
- **Interface web:** Streamlit, com o personagem Bisco.
  - Envia perguntas e continua conversas.
  - Responde a pedidos de esclarecimento e reinicia a sessão em "Nova conversa".
  - Mostra as referências normativas retornadas e sinaliza respostas inconclusivas (contingência) e erros.

## 4. Requisitos e configuração

- Docker com Compose v2: Docker Desktop no Windows ou macOS, ou Docker Engine no Linux ou no WSL 2.
- Chave da OpenRouter (`OPENROUTER_API_KEY`). As chamadas são pagas pelo titular da chave.
- Índice Chroma com o corpus (`.local/index/chroma.sqlite3`, cerca de 200 MB). O índice não é versionado; veja abaixo.

Configuração:

```powershell
Copy-Item .env.example .env   # Windows
# cp .env.example .env        # Linux
```

Preencha `OPENROUTER_API_KEY` e `POSTGRES_PASSWORD` (senha do PostgreSQL dos checkpoints, definida por você) no `.env`. O `.env` nunca é copiado para as imagens nem versionado.

A configuração avaliada é fixada no `compose.demo.yaml` e não pode ser alterada pelo `.env`:

```
CONVERSATION_INTERPRETER=jev
CONVERSATION_INTERPRETER_CONFIG={"transition_policy":"v2"}
RETRIEVAL_TOP_K=5
ROUTING_MODE=intent_v1
```

**Checkpoints.** O estado das conversas (pendência e nível declarado por thread) fica num PostgreSQL. O `compose.demo.yaml` o sobe como container, com volume `postgres_data`, só na rede interna e sem porta no host. O backend cria as tabelas na primeira subida. O armazenamento dos checkpoints não faz parte da configuração avaliada: os experimentos usaram SQLite, e o launcher só verifica intérprete, política, modelos, K e endpoint. Para usar um PostgreSQL externo (serviço gerenciado), veja a tabela **Outros modos** abaixo.

**Índice.** Coloque a cópia do índice usada nos experimentos em `.local/index/`, ou aponte `INDEX_DIR` para ela. Identidade da cópia: 507 registros, impressão digital de conteúdo `a38c9abadbbe…` (ids, documentos, metadados e embeddings arredondados). Para reconstruir a partir do corpus versionado (`evaluation/corpora/`), use os comandos de indexação de `code/` com o perfil `duas-regulacoes`. A reconstrução tem custo de embeddings, e uma reindexação pode não reproduzir a mesma impressão digital.

## 5. Execução com Docker em um comando

Windows (PowerShell ou Prompt), a partir de qualquer diretório:

```powershell
.\scripts\start-local.cmd
```

O script:

1. localiza a raiz do projeto;
2. verifica o Docker (Docker Desktop ou, na falta dele, Docker Engine na distro WSL `Ubuntu-24.04`, configurável em `TCC2_WSL_DISTRO`);
3. verifica o `.env` e o índice, sem imprimir segredos;
4. executa `docker compose -f compose.demo.yaml up --build -d --wait`;
5. espera os healthchecks e mostra a URL.

No WSL, ele mantém uma sessão aberta numa janela minimizada (`tcc2-wsl-keepalive`), porque o WSL encerra o Docker quando a última sessão termina.

**Interface:** <http://127.0.0.1:8501>

Para parar (os volumes são preservados, sem `down -v`):

```powershell
.\scripts\stop-local.cmd
```

Linux, WSL ou EC2: `./scripts/start-local.sh` e `./scripts/stop-local.sh`.

**Serviços**

| Serviço | Imagem | Rede e porta |
|---|---|---|
| `postgres` | `postgres:17.10-alpine` | Só a rede interna (sem saída para a internet), sem porta no host |
| `backend` | `tcc2-prototype-backend` | Sem porta no host; saudável quando o agente está pronto e a configuração é a avaliada (Jev + v2, modelos, K e endpoint) |
| `interface` | `tcc2-prototype-interface` | Única porta publicada, em `127.0.0.1:8501` |

Os containers do protótipo rodam sem root. O build do backend falha se algum arquivo-fonte do backend diferir do manifesto congelado da v2.

**Teste offline** (sem saída de rede no backend; nenhuma chamada a provedores):

```bash
docker compose -f compose.demo.yaml -f deploy/compose.smoke.yaml up -d --wait
```

**Outros modos**, detalhados em [`docs/DEPLOY_LINUX.md`](docs/DEPLOY_LINUX.md):

| Modo | Override | Uso |
|---|---|---|
| Só a API | `deploy/compose.api.yaml` | Publica o backend em `127.0.0.1:8080` para outros clientes ([`docs/API.md`](docs/API.md)) |
| PostgreSQL externo | `deploy/compose.external-postgres.yaml` | Checkpoints num PostgreSQL fora do compose (por exemplo, serviço gerenciado em nuvem), com `POSTGRES_HOST` no `.env`; o container `postgres` não sobe |
| Provedor compatível com a OpenAI | `deploy/compose.openai-compatible.yaml` | Geração e embeddings em qualquer endpoint compatível: local (Ollama, vLLM com proxy) ou remoto (OpenAI etc.), com índice próprio e a camada conversacional de A′, porque o Jev só existe na OpenRouter. **Não é a configuração avaliada**: a identidade informa `evaluated_configuration: false`. Nenhuma resposta por outro provedor foi gerada nesta versão. Variáveis na seção 2 do `.env.example`; outros provedores dos agentes do serviço na seção 3 |

## 6. Execução local sem Docker

Suportada para desenvolvimento, a partir de `code/`, com `uv`. O caminho testado da release é o Docker; os comandos abaixo não foram reexecutados nesta versão.

```powershell
cd code
uv sync --frozen
$env:PYTHONPATH="src"
$env:CONVERSATION_INTERPRETER="jev"
$env:CONVERSATION_INTERPRETER_CONFIG='{"transition_policy":"v2"}'
$env:CHROMA_PERSIST_DIR="..\.local\index"
uv run python ..\deploy\backend\prototype_launcher.py          # API na porta 8080 (HOST/PORT)
# Em outro terminal, também em code\, com PYTHONPATH="src" e AGENT_URL="http://127.0.0.1:8080":
uv run streamlit run src/streamlit_app.py --server.address 127.0.0.1   # interface na porta 8501
```

A chave vai em `code/.env` (`OPENROUTER_API_KEY=`). Sem `CONVERSATION_INTERPRETER`, o código executa a camada conversacional de A′; com `jev` mas sem `{"transition_policy":"v2"}`, executa a política v1. Nenhuma das duas é a versão selecionada. Equivalente em Linux: [`docs/DEPLOY_LINUX.md`](docs/DEPLOY_LINUX.md) §6.

## 7. Estrutura do repositório

| Caminho | Conteúdo |
|---|---|
| `code/src/rag_baseline/` | Pipeline normativo, camada conversacional e intérprete (`conversation_interpretation/`) |
| `code/src/service/`, `core/`, `agents/`, `memory/`, `schema/` | API FastAPI, configuração, registro de agentes, checkpointer e contratos de transporte |
| `code/src/streamlit_app.py`, `chat_ui/`, `static/bisco/`, `client/` | Interface web (Bisco: `bisco.js`, `bisco_rig.json` e camadas do rig) e cliente HTTP |
| `code/legacy/ufpinho/` | Interface anterior (UFpinho), arquivada |
| `code/compose*.yaml`, `code/docker/`, `code/.env.example`, `code/scripts/*_local.*` | Serviço e launchers **legados** (agente `chatbot_ufpi_v2`; container de API antigo). Mantidos porque testes do código congelado os verificam; não servem ao protótipo atual |
| `code/tests/` | Testes offline (sem provedor; intérpretes roteirizados) |
| `data/` | Registro normativo, PDF da Res. 177/2012 e questões de avaliação do trabalho anterior |
| `evaluation/corpora/` | Corpora estruturados (Resoluções 177/2012, 1.056/2026, 956/2025, 658/2024) |
| `evaluation/datasets/` | Gold normativo v2 e **gold revisado `*_reviewed_v2.json`** ([`REVIEWED_V2.md`](evaluation/datasets/REVIEWED_V2.md)), conjuntos temporais e de regressão |
| `evaluation/results/` | Resultados de experimentos anteriores ao TCC II final (registros históricos) |
| `evaluation/adaptive_rag/` | Executor usado nas comparações entre condições |
| `deploy/` | Dockerfiles, launcher, healthcheck, manifesto de integridade e override de teste offline |
| `compose.demo.yaml`, `scripts/` | Demonstração local em um comando |
| `docs/tcc2/` | Avaliação por QP, arquitetura, roteiro AWS e manifesto da release |
| `docs/DEPLOY_LINUX.md`, `docs/API.md` | Execução em Linux (completo, só API, modelo local, sem Docker) e referência da API |

## 8. Versões congeladas

| Tag | Estado | O que contém |
|---|---|---|
| `exp-baseline-2026-11-04` | Baseline experimental (`8fb690e5`) | — |
| `tcc2-cond-A` | Condição A | `8fb690e5` + executor de avaliação |
| `tcc2-cond-A1` | Condição A′ | R1 + R2 |
| `tcc2-cond-v1` | Condição A″-J v1 | Jev + política v1 |
| `tcc2-cond-v2` | **Condição A″-J v2** | Jev + política v2 (`code/src` com tree `4262de06…`) |
| branches `main` e `release/tcc2-prototype` | v2, interface Bisco, Docker e documentação | O código do backend é idêntico ao da tag `tcc2-cond-v2` |

Cada tag reproduz, em checkout novo, os bytes registrados nos manifestos SHA-256 da condição. No `.gitattributes`, os arquivos LF dessas condições estão marcados com `-text`.

## 9. Resultados experimentais, por questão de pesquisa

Todos os resultados são **exploratórios** e vêm de conjuntos de desenvolvimento. Não há avaliação confirmatória nem revisão normativa qualificada.

Origem de cada resultado:

- **[v2]:** medido diretamente na v2.
- **[A]:** medido na baseline ou em versões anteriores.
- **[comum]:** componente idêntico em A e v2; o resultado não foi remedido na v2.

**QP1 — escopo e nível**

- **[A]** Router V1: 16/23 corretas, 0/23 rotas erradas, esclarecimento indevido 7/14.
- **[v2]** Domínio correto 1,00 e 0 confusões de nível em 40 perguntas isoladas.
- **[v2]** Defeito **G4-014**: um nível persistido é injetado em "e na grad?".

**QP2 — esclarecimento (camada nova)**

60 cenários sintéticos × 3, com o checkpoint decisivo rotulado pelo pesquisador.

| Métrica | A | v2 | Δ [IC 95 %] |
|---|---:|---:|---|
| Decisão conversacional correta | 0,483 | 0,650 | +0,167 [+0,033; +0,283] |
| Idem, regra literal de contaminação (sensibilidade) | — | — | +0,150 [+0,017; +0,267] |
| Pergunta pretendida encaminhada à recuperação | 0,333 | 0,550 | +0,217 [+0,100; +0,333] |

- Falso consumo de pergunta nova: 0/417 nas duas condições.
- Consistência: A 1,00; v2 0,90.
- Respostas que atendem à pergunta pretendida (15 por condição): A 6, v2 5; 8 e 8 contando as parciais. **Não há ganho demonstrado na resposta final.**

**QP3 — versão**

- **[A] / [comum]** Contexto obsoleto entregue: 0/15 e 0/20 com filtro, contra 6/25 sem filtro. Regressão controlada: exposição 0/12, preservação histórica 6/6.
- Falhas registradas: TEMP-POS-004 e TEMP-GRAD-005.
- A v2 não teve experimento temporal próprio.

**QP4 — verificação**

- **[A] / [comum]** Na versão congelada, **5 de 11** respostas com afirmação sem suporte.
- GEN-01: 12/30 aceitas na primeira geração, 14/30 após nova tentativa, 4/30 em contingência.
- As variantes de "RAG adaptativo" (suficiência, recuperação complementar, validação semântica) não mostraram ganho.
- A fidelidade da v2 não foi medida.

**QP5 — usuários**

- Plataforma de demonstração preparada.
- **Pesquisa de campo não realizada.**

**Recuperação [v2] e [A]** (40 perguntas isoladas, gold [`reviewed_v2`](evaluation/datasets/REVIEWED_V2.md), 20 itens que chegam à recuperação): Recall@5 1,000 e MRR@5 0,975, iguais em A e v2.

## 10. Reprodução das métricas e testes offline

Testes offline, a partir de `code/`. Não chamam provedores; usam intérpretes roteirizados.

```bash
uv sync --frozen
PYTHONPATH="src:.." uv run pytest tests -p no:cacheprovider -q
uv run ruff check src tests
```

Integridade:

- `python deploy/backend/frozen_sources.py verify <raiz> deploy/backend/backend_sources.lfnorm.json` compara as fontes do backend com o manifesto congelado. O mesmo passo roda no build da imagem.
- Qualquer tag `tcc2-cond-*` pode ser conferida com o manifesto SHA-256 da respectiva condição.

As métricas das seções 9 e `docs/tcc2/` foram recalculadas offline a partir dos registros brutos de execução (C1, C2, C3) e das anotações fechadas do pesquisador (H-1, H-2). Esses registros e anotações estão preservados fora deste repositório e não fazem parte desta versão pública. O gold usado está versionado em `evaluation/datasets/*_reviewed_v2.json`.

## 11. Limitações conhecidas

- **G4-014:** um nível de ensino persistido pode ser aplicado a uma pergunta curta sobre outro nível ("e na grad?").
- **Afirmações sem suporte:** o validador opera sobre formas linguísticas, não sobre implicação; respostas aceitas ainda podem conter afirmações sem suporte.
- **Cenários de avaliação:** conversacionais, de autoria por modelo de linguagem, usados no desenvolvimento; sem generalização demonstrada.
- **Revisor:** o próprio pesquisador; sem segundo anotador e sem revisão normativa qualificada.
- **Determinismo:** a v2 é menos determinística (consistência 0,90); a geração a T = 0 também varia.
- **Critério E6:** dentro da gramática fechada de esclarecimentos, a v2 acertou menos que A′.
- **Dependência externa:** a Decisions API (alpha) e os modelos da OpenRouter podem mudar. A demonstração não fixa a rota de provedor da geração; os experimentos fixaram um provedor.
- **Scope Gate:** recusas induzidas por prefixos conversacionais.
- **Acervo:** limitado a quatro resoluções; parte vem de OCR; o estado de vigência das normas é declarado como "desconhecido" quando a publicação não foi comprovada.

## 12. Referências

- Lewis, P. et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. NeurIPS, 2020.
- Gao, Y. et al. Retrieval-Augmented Generation for Large Language Models: A Survey. 2023.
- Es, S. et al. Ragas: Automated Evaluation of Retrieval Augmented Generation. EACL (demo), 2024.
- Murugaraj, K. et al. RAGVUE: a diagnostic view for explainable RAG evaluation. EACL (demo), 2026.
- Min, S. et al. AmbigQA: Answering Ambiguous Open-domain Questions. EMNLP, 2020.
- Livathinos, N. et al. Docling: an efficient open-source toolkit for AI-driven document conversion. 2025.
- Melo, G. T.; Sousa, A. S. Protótipo de Assistente Virtual Baseado em RAG para Consulta às Normas da UFPI: um estudo de caso. UFPI.

As referências completas e conferidas estão no texto do TCC II.

## 13. Licenças, créditos e proveniência

- **Base de engenharia:** `code/` deriva do *agent-service-toolkit* (Joshua Carroll, licença MIT, `code/LICENSE`).
- **Trabalho anterior:** o assistente para a Resolução 177/2012 é de Guilherme Torres Melo e Armando Soares Sousa. Seu histórico está preservado neste repositório. Os resultados daquele trabalho pertencem a ele e não descrevem este protótipo.
- **Implementação do TCC II:** Wesley de Sousa Coutinho, sob orientação de Armando Soares Sousa. Inclui o acervo multinormativo, o registro e o filtro de versões, o validador, a camada conversacional (R1/R2, Jev, políticas v1/v2), a interface e a infraestrutura de demonstração.
- **Normas:** as resoluções da UFPI são atos públicos, obtidos de fontes institucionais. Os textos são fornecidos apenas para pesquisa; a versão oficial prevalece.
- **Fontes e imagens:** a fonte Google Sans segue a licença OFL (`code/src/static/fonts/`). O personagem Bisco foi criado para este protótipo e não é marca da UFPI; a versão anterior (UFpinho) está arquivada em `code/legacy/ufpinho`.
- **Licença das contribuições do TCC II:** a definir pelo pesquisador antes da publicação.
- **Artigos e livros em `articles/`:** são material de estudo de terceiros e não devem ser redistribuídos (veja `docs/tcc2/RELEASE_MANIFEST.md`).
