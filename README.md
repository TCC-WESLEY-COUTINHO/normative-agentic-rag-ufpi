# Normative Agentic Rag UFPI

Projeto desenvolvido no âmbito do Trabalho de Conclusão de Curso II
em Ciência da Computação da Universidade Federal do Piauí.

## Objetivo

Investigar uma arquitetura de RAG agêntico escalável para consulta
ao ecossistema normativo da UFPI, considerando estrutura documental,
relações entre normas e validade temporal.

## Repositórios relacionados

### Baseline

`rag-chatbot-ufpi`

Implementação do trabalho anterior utilizada como referência e baseline.

### Document Intelligence

`ingest_documents`

Pipeline experimental responsável por OCR, extração documental,
segmentação por artigos e enriquecimento de metadados normativos.

## Status

- [x] Estudo da implementação anterior
- [x] Pipeline inicial de ingestão com Docling
- [x] Chunking jurídico por artigos
- [x] Testes preliminares com a Resolução 177/2012
- [ ] Benchmark contra corpus manual do trabalho anterior
- [ ] Indexação vetorial
- [ ] RAG básico
- [ ] Modelagem temporal das normas
- [ ] Roteamento multiagente
- [ ] Recuperação baseada em grafo
- [ ] Avaliação experimental

## Baseline executável — graduação

Esta configuração estabelece uma baseline operacional provisória usando somente a
Resolução nº 177/2012 CEPEX/UFPI e os chunks estruturados existentes em
`code/scripts/chunks_v2.json`. As decisões de armazenamento vetorial, embedding, LLM,
chunking e parâmetros de retrieval ainda serão submetidas a avaliação experimental no TCC.

O texto enviado ao embedding concatena apenas os campos estruturais disponíveis
(norma, título, capítulo, seção, subseção e artigo) com o conteúdo original. Essa
concatenação também é provisória e não altera nem subdivide os chunks existentes.

### Pré-requisitos

- Git;
- Python 3.11 ou superior;
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/);
- uma conta no [OpenRouter](https://openrouter.ai/) e uma chave de API própria;
- acesso à internet para instalar as dependências e consultar os modelos configurados.

O código da baseline usa caminhos portáveis com `pathlib` e os mesmos módulos Python
para indexação, API e demo. Apenas os comandos de manipulação do arquivo `.env` e a
sintaxe multilinha do `curl` mudam entre PowerShell e Bash.

### Windows — PowerShell

Clone o repositório, selecione a branch da demo e instale as dependências:

```powershell
git clone https://github.com/TCC-WESLEY-COUTINHO/normative-agentic-rag-ufpi
Set-Location normative-agentic-rag-ufpi
git switch demo/terminal-ui
Set-Location code
uv sync --frozen
```

Crie o arquivo de configuração local:

```powershell
Copy-Item .env.example .env
notepad .env
```

No arquivo `.env`, preencha a variável abaixo com uma chave da sua própria conta:

```dotenv
OPENROUTER_API_KEY=<sua-chave-openrouter>
```

Não versione o `.env` nem compartilhe a chave. Para esta baseline, as demais variáveis
do `.env.example` podem permanecer com seus valores padrão ou vazias.

Indexe o corpus da graduação:

```powershell
uv run python -m rag_baseline.index --rebuild
```

No terminal 1, inicie a API:

```powershell
uv run uvicorn rag_baseline.api:app --host 127.0.0.1 --port 8080
```

Em outro PowerShell, ainda dentro de `code`, verifique a API:

```powershell
curl.exe http://127.0.0.1:8080/health
```

Envie uma consulta diretamente ao endpoint:

```powershell
curl.exe -X POST http://127.0.0.1:8080/query `
  -H "Content-Type: application/json" `
  -d '{"question":"Quais são as regras para matrícula?"}'
```

Ou execute a interface de terminal em modo normal ou detalhado:

```powershell
uv run python -m rag_baseline.demo
uv run python -m rag_baseline.demo --verbose
```

### Linux — Bash

Clone o repositório, selecione a branch da demo e instale as dependências:

```bash
git clone https://github.com/TCC-WESLEY-COUTINHO/normative-agentic-rag-ufpi
cd normative-agentic-rag-ufpi
git switch demo/terminal-ui
cd code
uv sync --frozen
```

Crie o arquivo de configuração local:

```bash
cp .env.example .env
nano .env
```

No arquivo `.env`, preencha a variável abaixo com uma chave da sua própria conta:

```dotenv
OPENROUTER_API_KEY=<sua-chave-openrouter>
```

Não versione o `.env` nem compartilhe a chave. Para esta baseline, as demais variáveis
do `.env.example` podem permanecer com seus valores padrão ou vazias.

Indexe o corpus da graduação:

```bash
uv run python -m rag_baseline.index --rebuild
```

No terminal 1, inicie a API:

```bash
uv run uvicorn rag_baseline.api:app --host 127.0.0.1 --port 8080
```

Em outro terminal, ainda dentro de `code`, verifique a API:

```bash
curl http://127.0.0.1:8080/health
```

Envie uma consulta diretamente ao endpoint:

```bash
curl -X POST http://127.0.0.1:8080/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Quais são as regras para matrícula?"}'
```

Ou execute a interface de terminal em modo normal ou detalhado:

```bash
uv run python -m rag_baseline.demo
uv run python -m rag_baseline.demo --verbose
```

Use `Ctrl+C` para encerrar a demo ou a API. O endpoint `POST /query` retorna a resposta
e as referências obtidas diretamente dos chunks recuperados. O endpoint `GET /health`
não realiza chamadas ao OpenRouter.
