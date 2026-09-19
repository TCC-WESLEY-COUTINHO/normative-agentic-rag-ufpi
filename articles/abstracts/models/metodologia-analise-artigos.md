# Metodologia de Análise e Catalogação de Artigos Científicos

## Introdução

Durante o desenvolvimento do meu trabalho de conclusão de curso sobre chatbots educacionais baseados em RAG (Retrieval-Augmented Generation), percebi a necessidade de estabelecer um sistema estruturado para analisar e catalogar a literatura científica. A experiência de ler dezenas de artigos sem um método organizado resultou em informações perdidas e tempo desperdiçado na busca por referências específicas durante a escrita.

## Estrutura de Análise Documental

O modelo apresentado a seguir foi concebido para maximizar a eficiência na análise de artigos científicos, garantindo que cada leitura contribua efetivamente para o desenvolvimento do trabalho acadêmico. A estrutura é dividida em quatro seções principais, cada uma com objetivos específicos e critérios de avaliação claros.

-----

### Estrutura de Resumo Analítico para Artigos do TCC

Esta estrutura foi desenvolvida como um template padronizado para análise de artigos científicos, permitindo uma catalogação sistemática e eficiente da literatura relevante.

-----

#### **1. Informações Bibliográficas (Catalogação)**

* **Nome do Arquivo:**
  * Seguir o padrão: `AutorSobrenome-Ano-PalavrasChaveDoTitulo.md`
  * *(Ex: `Zhang-2023-RAG-Education-Chatbots.md`, `Johnson-2024-Retrieval-Augmented-Generation.md`)*
* **Referência Completa (ABNT):**
  * SOBRENOME, Nome. Título do artigo. **Nome da Revista**, Cidade, v. X, n. Y, p. Z-W, mês, ano.
* **Link/DOI:**
  * [Link para o artigo ou DOI]
* **Palavras-chave do Artigo:**
  * [Listar as 3-5 palavras-chave fornecidas pelos autores]
* **Minhas Palavras-chave:**
  * *(Ex: RAG, Chatbot universitário, Recuperação de informação, Avaliação de chatbot, Protocolos acadêmicos)*

-----

#### **2. Análise do Conteúdo (O que o artigo diz?)**

* **Problema Central:**
  * Qual é o problema principal que os autores estão tentando resolver? (Descreva em 1-2 frases).
* **Objetivo Principal:**
  * Qual é o objetivo declarado do artigo? O que eles se propuseram a construir, analisar ou provar?
* **Metodologia Aplicada:**
  * Como eles fizeram isso? Descreva de forma concisa os métodos, a arquitetura, os dados utilizados e os experimentos realizados.
  * *(Ex: "Desenvolveram um pipeline RAG usando o modelo LLaMA-2, com embeddings do tipo `Sentence-BERT`. Os documentos foram segmentados em chunks de 256 tokens. A avaliação foi feita com o dataset X e métricas Y e Z.")*
* **Resultados e Conclusões Principais:**
  * Quais foram os achados mais importantes? (Use bullet points para clareza).
  * - 
  * - 
  * A hipótese inicial foi confirmada? Qual foi a conclusão final dos autores?

-----

#### **3. Conexão com o meu TCC (Como isso me ajuda?)**

Esta seção representa o coração da metodologia, onde a análise crítica se transforma em conhecimento aplicável ao projeto específico.

* **Relevância Direta para o Projeto (Score: 1-5):**
  * Atribua uma nota de 1 (pouco relevante) a 5 (essencial) e justifique brevemente.
  * *(Ex: "Nota 5. O artigo detalha uma técnica de chunking específica para documentos institucionais, o que é diretamente aplicável aos protocolos da UFPI.")*
* **Contribuições Teóricas para o Referencial:**
  * Quais conceitos, definições ou frameworks deste artigo eu posso usar no meu referencial teórico (Capítulo 2)?
  * *(Ex: "A definição de 'RAG Híbrido' na página 4. O modelo de avaliação de satisfação do usuário da seção 5. A discussão sobre os desafios de 'hallucination' em chatbots institucionais.")*
* **Ideias Práticas para Implementação:**
  * Que ideias técnicas ou práticas posso "emprestar" para o meu chatbot?
  * **Arquitetura RAG:** [Estratégia de chunking, modelo de embedding, modelo de LLM, etc.]
  * **Features do Chatbot:** [Como lidar com perguntas ambíguas, como apresentar fontes, etc.]
  * **Avaliação do Protótipo:** [Métricas de avaliação (ex: ROUGE, BLEU), ideias para testes com usuários, questionários de satisfação.]
  * **Desafios a Evitar:** [O artigo mencionou algum problema que eu posso antecipar e evitar?]
* **Citações e Trechos Chave (com nº da página):**
  * Copie e cole aqui 2-3 frases ou parágrafos que você considera cruciais, já com a página. Isso economizará um tempo imenso na hora de escrever.
  * *(Ex: "A principal dificuldade na implementação de RAG em domínios específicos é a correta segmentação de documentos com formatação complexa, como tabelas e fluxogramas." (AUTOR, ANO, p. 12))*

-----

#### **4. Avaliação Crítica e Próximos Passos**

* **Pontos Fortes do Artigo:**
  * O que o artigo faz bem? (Metodologia robusta, resultados claros, abordagem inovadora).
* **Limitações e Pontos Fracos:**
  * Quais as limitações do estudo? (Amostra pequena, contexto muito específico, tecnologia já datada).
* **Dúvidas Geradas:**
  * O que não ficou claro? O que eu preciso pesquisar mais a fundo depois de ler este artigo?
* **Próximos Passos:**
  * [ ] Reler o artigo para a escrita do Capítulo X.
  * [ ] Procurar os artigos citados por este autor (referências).
  * [ ] Apenas catalogar, baixa prioridade.
  * [ ] Usar imediatamente no desenvolvimento do protótipo.

-----

### Template Resumido para Copiar e Colar

```markdown
### Resumo Analítico do Artigo: [Título do Artigo]

**1. Informações Bibliográficas**
* **Nome do Arquivo:**
* **Referência (ABNT):**
* **Link/DOI:**
* **Palavras-chave:**
* **Minhas Tags:**

**2. Análise do Conteúdo**
* **Problema Central:**
* **Objetivo Principal:**
* **Metodologia:**
* **Resultados e Conclusões:**

**3. Conexão com o TCC (Chatbot RAG - UFPI)**
* **Relevância Direta (1-5):**
* **Contribuições Teóricas:**
* **Ideias para Implementação:**
* **Citações Chave (página):**

**4. Avaliação Crítica e Próximos Passos**
* **Pontos Fortes:**
* **Limitações:**
* **Dúvidas:**
* **Próximos Passos:**

```

## Considerações Finais

A implementação desta metodologia transformou significativamente minha eficiência na pesquisa acadêmica. O que antes era uma leitura desorganizada e frequentemente improdutiva, tornou-se um processo sistemático de construção de conhecimento. Cada artigo analisado seguindo esta estrutura contribui não apenas para o referencial teórico, mas também para o desenvolvimento prático do projeto.

A experiência demonstrou que investir tempo na criação de um sistema de catalogação robusto no início da pesquisa economiza horas preciosas durante a fase de escrita. Além disso, a análise crítica sistemática permite identificar rapidamente lacunas na literatura e oportunidades para contribuições originais.

Esta metodologia pode ser adaptada para diferentes áreas de pesquisa, mantendo a estrutura fundamental mas ajustando os critérios de relevância e as categorias de análise conforme necessário. O importante é manter a consistência na aplicação e a disciplina na documentação de cada análise realizada.
