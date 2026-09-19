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

No PowerShell, execute a partir da raiz do repositório:

```powershell
Set-Location code
uv sync
Copy-Item .env.example .env
```

Preencha somente `OPENROUTER_API_KEY` no arquivo `.env`. Em seguida, indexe o corpus:

```powershell
uv run python -m rag_baseline.index --rebuild
```

Inicie a API independente do aplicativo legado:

```powershell
uv run uvicorn rag_baseline.api:app --host 127.0.0.1 --port 8080
```

Consulte o estado da coleção:

```powershell
curl.exe http://127.0.0.1:8080/health
```

Envie uma pergunta:

```powershell
curl.exe -X POST http://127.0.0.1:8080/query `
  -H "Content-Type: application/json" `
  -d '{"question":"Quais são as regras para matrícula?"}'
```

O endpoint `POST /query` retorna a resposta e referências obtidas diretamente dos
chunks recuperados. O endpoint `GET /health` não realiza chamadas ao OpenRouter.
