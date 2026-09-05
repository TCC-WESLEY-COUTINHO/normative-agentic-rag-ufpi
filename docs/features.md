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
```

### Critério mínimo de aceite

Cada artigo deve poder ser associado de forma inequívoca ao documento de origem.

---

## F05 — Geração e armazenamento de embeddings

**Prioridade:** P0  
**Módulo:** sistema principal

### Descrição

Gerar representações vetoriais dos artigos estruturados para possibilitar recuperação semântica.

A estratégia inicial deve manter compatibilidade metodológica com o trabalho anterior, permitindo posteriormente experimentos comparativos com diferentes modelos de embedding.

### Critério mínimo de aceite

- gerar embedding para cada artigo;
- persistir embedding e metadados;
- permitir associação entre vetor e artigo original.

---

## F06 — Recuperação vetorial de artigos

**Prioridade:** P0  
**Módulo:** sistema principal

### Descrição

Recuperar os artigos semanticamente mais relevantes para uma pergunta do usuário.

A primeira versão pode utilizar busca vetorial exaustiva, preservando a abordagem empregada no trabalho anterior enquanto o corpus permanecer pequeno.

### Critério mínimo de aceite

Dada uma consulta:

- gerar o embedding da pergunta;
- calcular similaridade com os artigos;
- retornar os `top-k` artigos;
- retornar texto e metadados associados.

---

## F07 — Geração de resposta RAG fundamentada

**Prioridade:** P0  
**Módulo:** sistema principal

### Descrição

Gerar respostas utilizando somente o contexto normativo recuperado.

A resposta deve apresentar evidências que permitam identificar a origem normativa da informação.

### Critério mínimo de aceite

A resposta deve:

- utilizar os artigos recuperados;
- identificar a resolução utilizada;
- identificar o artigo utilizado;
- evitar apresentar informação normativa sem evidência recuperada.

---

## F08 — Infraestrutura de avaliação

**Prioridade:** P0  
**Módulo:** avaliação

### Descrição

Permitir avaliação independente das principais etapas do pipeline.

A avaliação não deve considerar apenas a resposta final, mas também:

- ingestão;
- segmentação;
- recuperação;
- geração.

### Avaliações iniciais

#### Ingestão

- Article ID Recall;
- Article ID Precision;
- Hierarchy Exact Match;
- similaridade textual com corpus revisado.

#### Recuperação

- Hit@k;
- Recall@k;
- MRR.

#### Sistema completo

- qualidade da resposta;
- fidelidade ao contexto;
- latência.

### Critério mínimo de aceite

Registrar consulta, documentos recuperados, resposta produzida e métricas associadas.

---

# P1 — Contribuições principais do TCC II

## F09 — Extração de relações normativas

**Prioridade:** P1  
**Módulo:** grafo normativo

### Descrição

Identificar relações explícitas entre documentos e dispositivos normativos.

### Relações iniciais

- `ALTERA`;
- `REVOGA`;
- `RETIFICA`;
- `SUBSTITUI`;
- `REFERENCIA`.

Exemplo:

```text
Resolução 089/2018
        │
        └── ALTERA
              │
              ▼
     Resolução 177/2012
              │
              └── Art. 148
```

### Critério mínimo de aceite

Uma relação deve possuir:

- documento de origem;
- tipo da relação;
- documento de destino;
- dispositivo afetado, quando identificável.

---

## F10 — Controle de versão e vigência normativa

**Prioridade:** P1  
**Módulo:** grafo normativo / compliance

### Descrição

Representar a validade temporal dos dispositivos normativos.

Um mesmo artigo pode possuir versões distintas ao longo do tempo.

### Metadados previstos

```json
{
  "status": "vigente",
  "valid_from": "2018-06-13",
  "valid_until": null
}
```

### Estados possíveis

- vigente;
- alterado;
- revogado;
- substituído;
- situação desconhecida.

### Critério mínimo de aceite

O sistema deve conseguir distinguir uma versão vigente de uma versão que não deve mais ser considerada como regra atual.

---

## F11 — Filtro temporal e de conformidade

**Prioridade:** P1  
**Módulo:** compliance

### Descrição

Aplicar uma etapa determinística entre recuperação e geração para impedir que chunks sabidamente obsoletos sejam utilizados como evidência atual.

Fluxo:

```text
Pergunta
   ↓
Retrieval
   ↓
Verificação de vigência
   ↓
Contexto válido
   ↓
LLM
```

### Critério mínimo de aceite

Quando houver metadados suficientes de vigência, uma versão revogada ou substituída não deve ser utilizada como fundamento de uma resposta sobre a situação atual.

---

## F12 — Roteamento por domínio normativo

**Prioridade:** P1  
**Módulo:** orquestração

### Descrição

Classificar a pergunta do usuário para encaminhá-la ao domínio normativo apropriado.

### Domínios iniciais possíveis

- Graduação;
- Pós-Graduação;
- Recursos Humanos;
- outros domínios adicionados posteriormente.

### Critério mínimo de aceite

O roteador deve produzir uma saída estruturada identificando o domínio responsável pelo processamento da consulta.

---

## F13 — Agentes especialistas

**Prioridade:** P1  
**Módulo:** orquestração

### Descrição

Utilizar agentes especializados em diferentes domínios ou estratégias de recuperação.

Um agente especialista pode decidir, por exemplo, entre:

- busca vetorial;
- consulta ao grafo;
- combinação das duas estratégias.

### Critério mínimo de aceite

O Supervisor deve encaminhar a consulta a um especialista e receber uma resposta estruturada para continuar o fluxo.

---

## F14 — Recuperação baseada em grafo

**Prioridade:** P1  
**Módulo:** grafo normativo

### Descrição

Permitir consultas em que similaridade textual isolada não seja suficiente.

Exemplos:

- qual resolução alterou determinado artigo;
- quais dispositivos de uma norma foram revogados;
- qual é a versão atualmente válida de um artigo;
- quais normas dependem de outra resolução.

### Critério mínimo de aceite

Dado um dispositivo ou documento normativo, o sistema deve conseguir percorrer relações explícitas armazenadas no grafo.

---

## F15 — Abstenção por evidência insuficiente

**Prioridade:** P1  
**Módulo:** geração / compliance

### Descrição

Evitar respostas factualmente presumidas quando o corpus recuperado não fornecer evidência suficiente para uma conclusão.

### Critério mínimo de aceite

O sistema deve identificar casos em que:

- nenhuma evidência relevante foi recuperada;
- existem documentos conflitantes sem resolução de vigência;
- falta informação necessária para determinar a resposta.

Nesses casos, deve informar a insuficiência de evidências em vez de produzir uma conclusão normativa não fundamentada.

---

# P2 — Funcionalidades avançadas

## F16 — GraphRAG para consultas globais

**Prioridade:** P2  
**Módulo:** GraphRAG

### Descrição

Construir uma representação de conhecimento de nível global a partir das normas e suas relações.

Podem ser investigadas técnicas como:

- extração de entidades e relações;
- formação de comunidades;
- Leiden;
- geração de resumos de comunidades;
- respostas globais baseadas no grafo.

### Casos de uso

Exemplos:

- quais são os principais temas regulados pelas normas acadêmicas da UFPI;
- quais conjuntos de normas apresentam maior quantidade de dependências;
- como um determinado tema evoluiu entre diferentes resoluções.

### Critério mínimo de aceite

Demonstrar pelo menos um tipo de consulta global em que a recuperação baseada somente em chunks vetoriais seja insuficiente.

---

# Funcionalidades futuras

## F17 — Atualização automática do corpus normativo

**Prioridade:** Futuro

### Descrição

Investigar mecanismos para detectar automaticamente a publicação, alteração ou substituição de normas nas fontes oficiais da UFPI.

Essa funcionalidade depende do levantamento das fontes institucionais e dos mecanismos disponíveis para acesso aos documentos.

### Fluxo futuro esperado

```text
Fonte oficial
     ↓
Detecção de nova norma
     ↓
Download
     ↓
Docling
     ↓
Normalização
     ↓
Chunking por artigo
     ↓
Atualização vetorial
     ↓
Atualização do grafo
```

### Critério mínimo de aceite

Ainda não definido. A viabilidade dependerá da estrutura e disponibilidade das fontes oficiais identificadas.

---

# Priorização resumida

| ID | Feature | Prioridade |
|---|---|---|
| F01 | Ingestão automática de PDFs | P0 |
| F02 | Chunking normativo por artigo | P0 |
| F03 | Metadados hierárquicos | P0 |
| F04 | Identificação do documento | P0 |
| F05 | Geração e armazenamento de embeddings | P0 |
| F06 | Recuperação vetorial | P0 |
| F07 | Resposta RAG fundamentada | P0 |
| F08 | Infraestrutura de avaliação | P0 |
| F09 | Relações normativas | P1 |
| F10 | Versionamento e vigência | P1 |
| F11 | Filtro temporal/compliance | P1 |
| F12 | Roteamento por domínio | P1 |
| F13 | Agentes especialistas | P1 |
| F14 | Recuperação baseada em grafo | P1 |
| F15 | Abstenção | P1 |
| F16 | GraphRAG global | P2 |
| F17 | Atualização automática das normas | Futuro |

---

# Escopo da primeira versão

A primeira versão funcional deve priorizar o seguinte fluxo:

```text
PDF
 ↓
Docling
 ↓
Parser normativo
 ↓
1 artigo = 1 chunk
 ↓
Metadados
 ↓
Embedding
 ↓
Vector Store
 ↓
Retrieval
 ↓
LLM
 ↓
Resposta com resolução e artigo
```

Após a validação dessa base, a arquitetura deve evoluir para:

```text
                         ┌── Vector Retrieval
Pergunta → Supervisor ───┤
                         └── Graph Retrieval
                                  ↓
                         Compliance Filter
                                  ↓
                              Evidências
                                  ↓
                                LLM
                                  ↓
                              Resposta
```

---

# Roadmap preliminar

## Setembro

Objetivo: primeira versão funcional da base do sistema.

- consolidar ingestão;
- validar chunking normativo;
- validar metadados;
- implementar embeddings;
- implementar recuperação vetorial;
- implementar RAG básico.

## Outubro

Objetivo: implementar e definir os experimentos das principais contribuições.

- relações entre normas;
- grafo normativo;
- vigência;
- filtro temporal;
- roteamento;
- agentes;
- avaliação experimental.

## Novembro

Objetivo: consolidar resultados e redação.

- experimentos finais;
- análise dos resultados;
- comparação com baseline;
- discussão;
- redação do trabalho;
- revisão e ajustes finais.

---

# Status atual

Até o momento:

- [x] implementação anterior analisada como baseline;
- [x] repositório específico de ingestão criado;
- [x] Docling testado sobre resoluções reais da UFPI;
- [x] OCR testado em documentos sem camada textual adequada;
- [x] parser determinístico por artigo implementado;
- [x] Resolução 177/2012 processada automaticamente;
- [x] anomalias de OCR e estrutura identificadas;
- [ ] comparação quantitativa com os chunks revisados do TCC anterior;
- [ ] indexação vetorial;
- [ ] recuperação;
- [ ] RAG básico;
- [ ] grafo normativo;
- [ ] controle temporal;
- [ ] arquitetura multiagente;
- [ ] avaliação final.
