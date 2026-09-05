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
