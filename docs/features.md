# Features do Projeto

## Visão geral

Este documento apresenta o levantamento inicial das funcionalidades do projeto de TCC II:

**Arquitetura de RAG Agêntico Escalável e Baseada em Grafos para o Ecossistema Normativo da UFPI**

As funcionalidades foram priorizadas com o objetivo de separar:

- **P0 — MVP:** funcionalidades necessárias para uma primeira versão funcional;
- **P1 — Contribuição principal:** funcionalidades centrais para a evolução proposta em relação ao trabalho anterior;
- **P2 — Avançadas:** funcionalidades desejáveis, condicionadas ao tempo disponível;
- **Futuro:** funcionalidades fora do escopo imediato do protótipo.

A implementação parte da estratégia validada no TCC anterior, na qual o **artigo é utilizado como unidade principal de recuperação**, enriquecido com metadados hierárquicos da norma.

---

# P0 — MVP

## F01 — Ingestão automática de documentos normativos

**Prioridade:** P0  
**Módulo:** `ingest_documents`

### Descrição

Permitir a ingestão automatizada de resoluções e outros documentos normativos da UFPI a partir de arquivos PDF.

O pipeline utiliza o Docling como camada inicial de Document Intelligence para extração de texto, OCR, layout e estrutura documental.

### Critério mínimo de aceite

- receber um PDF como entrada;
- processar documentos com ou sem camada textual utilizável;
- gerar uma representação textual estruturada;
- preservar os artefatos intermediários para auditoria.

---

## F02 — Segmentação normativa por artigo

**Prioridade:** P0  
**Módulo:** `ingest_documents`

### Descrição

Reproduzir a estratégia utilizada no TCC anterior:

> **1 artigo normativo = 1 chunk**

Cada chunk deve conter o artigo completo, incluindo seus dispositivos subordinados, como:

- parágrafos;
- incisos;
- alíneas.

O chunking genérico do Docling não será utilizado como unidade final de recuperação quando provocar fragmentação ou agrupamento inadequado de artigos.

### Critério mínimo de aceite

- detectar definições de artigos;
- não confundir referências a artigos com novos chunks;
- manter parágrafos, incisos e alíneas associados ao artigo correto;
- gerar um identificador do artigo.

---

## F03 — Enriquecimento com metadados hierárquicos

**Prioridade:** P0  
**Módulo:** `ingest_documents`

### Descrição

Associar a cada artigo seu contexto hierárquico dentro da norma.

### Metadados mínimos

- documento/resolução;
- título;
- capítulo;
- seção;
- subseção;
- artigo.

Quando disponível, também preservar informações de proveniência, como página de origem.

### Critério mínimo de aceite

Cada chunk deve possuir metadados estruturados permitindo identificar sua posição na norma.

---

## F04 — Identificação do documento normativo

**Prioridade:** P0  
**Módulo:** `ingest_documents`

### Descrição

Registrar informações básicas sobre a norma da qual o artigo foi extraído.

### Metadados previstos

- tipo do documento;
- número;
- ano;
- data;
- órgão emissor;
- domínio;
- fonte.

Exemplo:

```json
{
  "document_type": "resolucao",
  "number": 177,
  "year": 2012,
  "domain": "graduacao"
}
