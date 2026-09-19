# Resumo Analítico do Artigo: [Título Completo e Subtítulo do Artigo]

### 1. Informações Bibliográficas (Catalogação)

* **Nome do Arquivo:** `SobrenomeAutor-2024-Algumas-Palavras-Chave.md`
* **Referência Completa (ABNT):** SOBRENOME, Nome do Autor. Título do artigo: subtítulo se houver. **Nome da Revista**, Cidade, v. [X], n. [Y], p. [Z-W], [mês], 2024.
* **Link/DOI:** [<https://doi.org/[número_do_doi>](https://doi.org/[número_do_doi])
* **Palavras-chave do Artigo:** [Palavra-chave 1], [Palavra-chave 2], [Palavra-chave 3].
* **Minhas Palavras-chave:** RAG, TCC, Chatbot UFPI, Avaliação de LLM, Referencial Teórico.

-----

### 2. Análise do Conteúdo (O que o artigo diz?)

* **Problema Central:** O artigo aborda o desafio de [descrever o problema, por exemplo, a baixa precisão dos LLMs em domínios de conhecimento específico e a ocorrência de alucinações].
* **Objetivo Principal:** O objetivo dos autores foi [descrever o objetivo, por exemplo, desenvolver e avaliar uma nova arquitetura RAG que melhora a fidelidade factual das respostas em documentos institucionais].
* **Metodologia Aplicada:** Os pesquisadores implementaram um pipeline RAG utilizando o modelo [Nome do LLM, ex: Llama 3] para geração e o modelo [Nome do Embedding, ex: BGE-large-en-v1.5] para embeddings. Os documentos foram segmentados em chunks de [tamanho] tokens com [overlap] de sobreposição. A avaliação foi realizada comparando o sistema contra [um baseline ou outro modelo] usando as métricas [ex: ROUGE-L, BLEU, e um questionário de avaliação humana].
* **Resultados e Conclusões Principais:**
  * * A arquitetura proposta superou o baseline em [X]% na métrica de precisão factual.
  * * A análise qualitativa demonstrou que o sistema foi capaz de [descrever um achado importante, ex: responder corretamente a 8 de 10 perguntas complexas sobre os documentos].
  * Os autores concluíram que [descrever a conclusão principal, ex: a adição de um módulo de reranking é crucial para a performance em domínios com documentos densos].

-----

### 3. Conexão com o meu TCC (Como isso me ajuda?)

* **Relevância Direta para o Projeto (Score: 1-5):** [5/5 - Essencial]. O artigo é diretamente aplicável, pois testa uma metodologia de `chunking` que posso replicar para os documentos e protocolos da UFPI.
* **Contribuições Teóricas para o Referencial:** Posso utilizar este artigo para fundamentar a seção [número da seção] do meu referencial teórico, especialmente para definir [conceito X] e justificar a escolha da arquitetura [tipo de arquitetura].
* **Ideias Práticas para Implementação:**
  * **Arquitetura RAG:** Adotar a estratégia de `chunking` mencionada e testar o modelo de embedding [Nome do Embedding] que apresentou bons resultados no artigo.
  * **Features do Chatbot:** Implementar um sistema de citação de fontes similar ao descrito na seção [número da seção], mostrando ao usuário exatamente de qual documento a resposta foi extraída.
  * **Avaliação do Protótipo:** Utilizar o mesmo questionário de avaliação humana (ou uma versão adaptada) descrito no apêndice do artigo para validar os resultados do meu protótipo.
  * **Desafios a Evitar:** Os autores mencionam a dificuldade em lidar com tabelas. Devo prestar atenção especial a isso durante o pré-processamento dos documentos da UFPI.
* **Citações e Trechos Chave (com nº da página):** "A eficácia de um sistema RAG está intrinsecamente ligada à qualidade da sua etapa de recuperação de informação." (SOBRENOME DO AUTOR, 2024, p. 5).

-----

### 4. Avaliação Crítica e Próximos Passos

* **Pontos Fortes do Artigo:** Metodologia experimental bem definida e resultados claramente apresentados. A disponibilização do código-fonte pelos autores é um grande diferencial.
* **Limitações e Pontos Fracos:** O estudo foi realizado apenas com documentos em inglês, o que pode ser uma limitação ao aplicar os resultados diretamente para o português. O dataset utilizado é de um domínio diferente (ex: jurídico) do meu (acadêmico).
* **Dúvidas Geradas:** Como a performance do modelo de embedding se comportaria com os termos e jargões específicos da UFPI? Seria necessário um fine-tuning?
* **Próximos Passos:**
  * [X] Reler o artigo para a escrita do Capítulo X.
  * [X] Procurar os artigos citados por este autor (referências).
  * [ ] Apenas catalogar, baixa prioridade.
  * [ ] Usar imediatamente no desenvolvimento do protótipo.
