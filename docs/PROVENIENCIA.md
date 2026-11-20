# Arquitetura, versões e proveniência

O protótipo de pesquisa do TCC II consulta normas acadêmicas da UFPI. Não é um serviço oficial da instituição. A condição padrão é **v3.4**, com geração ancorada em citação (`cited_v3`), corpus canônico (`duas-regulacoes-v4`) e camada conversacional **A″-J v2**.

## Acervo e arquitetura atual

| Norma | Papel no acervo |
|---|---|
| Resolução 177/2012 CEPEX/UFPI | Regulamento Geral da Graduação |
| Resolução 1.056/2026 | Altera o art. 68 da Resolução 177/2012 |
| Resolução 956/2025 CEPEX/UFPI | Pós-graduação stricto sensu, vigente |
| Resolução 658/2024 | Pós-graduação, revogada pela 956/2025 |

O fluxo da condição v3.4 segue estas etapas:

1. **Conversa:** respostas fixas sobre o próprio assistente, habilitadas por `ASSISTANT_IDENTITY=on`, precedem a interpretação e preservam a pendência; com `off`, reproduz-se a camada conversacional congelada. Nos demais turnos, Jev e a política determinística de transição v2 tratam a mensagem e a pendência da thread.
2. **Escopo:** o controle de escopo recusa perguntas fora do tema, sem decidir o nível de ensino.
3. **Nível:** graduação/pós explícita usa um atalho; ambiguidade passa pelo roteador ou resulta em pedido de esclarecimento.
4. **Recuperação:** busca vetorial exata e lexical BM25, com `k = 5`.
5. **Tempo:** o filtro de versão e o contexto temporal tratam redação vigente, alterações, revogações e consultas históricas.
6. **Geração ancorada:** o modelo de linguagem produz afirmações, cada uma acompanhada de citação literal de um trecho recuperado.
7. **Verificação:** um verificador determinístico confere literalidade, números e prazos, dispositivo, nível, norma e negações acrescentadas. Afirmações sem suporte são omitidas e viram ressalvas; se não resta conclusão verificada, o sistema se abstém.
8. **Saída:** o guard precede a resposta com referências tipadas de norma, artigo e dispositivo. A verificação de forma não garante implicação semântica.

Os grafos conversacional e normativo, a integração LangGraph/LangChain, a memória por thread e os arquivos dos componentes estão descritos em [Arquitetura A″-J v2](tcc2/ARQUITETURA_A2J_V2.md). O diagrama histórico desse guia descreve a geração da v2; as etapas de geração e verificação acima registram a diferença da v3.4. A v2 de texto livre continua selecionável por configuração.

Na camada conversacional, o intérprete Jev lê a mensagem e a pendência. A política v2 decide entre retomar, tratar uma pergunta nova ou esclarecer, controlando o consumo da pendência e o uso do nível declarado. O estado fica no checkpointer: PostgreSQL na demonstração, SQLite nos testes e experimentos. Os detalhes de execução ficam em [Instalação](INSTALACAO.md), e os campos de transporte em [API](API.md).

## Condições e tags

| Identificação | Condição | Mudança |
|---|---|---|
| `exp-baseline-2026-11-04` | Baseline experimental (`8fb690e5`) | Ponto de congelamento histórico |
| `tcc2-cond-A` | A | Baseline congelada com executor de avaliação |
| `tcc2-cond-A1` | A′ | R1: gramática de esclarecimentos naturais; R2: nível declarado persistido |
| `tcc2-cond-v1` | A″-J v1 | A′ com intérprete Jev e política de transição v1 |
| `tcc2-cond-v2` | A″-J v2 | Política de transição v2; geração histórica de texto livre com guard |
| `tcc2-cond-v3.4` | v3.4, padrão | Geração ancorada em citação e corpus canônico v4, mantendo a camada conversacional v2 |
| `release/tcc2-prototype` | Branch histórica de integração | Condição v2 com interface Bisco, Docker e documentação |
| `release/tcc2-v3.4` | Branch de integração v3.4 | Padrões `cited_v3` / `duas-regulacoes-v4`, interface e infraestrutura |

As tags identificam estados históricos do projeto; não afirmam que seus objetos Git estejam incluídos em todo snapshot público. Os manifestos SHA-256 registram os bytes das condições A, A′, v1 e v2; as regras `-text` em `.gitattributes` preservam as representações congeladas. A árvore histórica de `code/src` na v2 é `4262de06…`.

Entre A e v2, as mudanças são conversacionais; os resultados dessas condições não devem ser atribuídos à geração da v3.4. As variantes de RAG adaptativo, recuperação com K = 10/reordenação, Router V2 e intérprete estruturado A2L foram investigadas e não promovidas à configuração selecionada. As [evidências históricas por QP](tcc2/AVALIACAO_TCCII_JEV_V2.md) preservam seus limites e as falhas registradas.

## Problema e questões de pesquisa

O trabalho investiga como se comporta, e com quais limitações, um assistente universitário quando escopo, nível de ensino e versão normativa são separados da geração, e a resposta é verificada antes da entrega.

| Questão | Tema |
|---|---|
| QP1 | Escopo e nível de ensino |
| QP2 | Esclarecimento |
| QP3 | Versão normativa |
| QP4 | Verificação da resposta |
| QP5 | Avaliação com usuários |

Os problemas incluem regras diferentes para graduação/pós com artigos de numeração coincidente, alterações/revogações e condições ou prazos acrescentados sem suporte. Os [resultados atuais](RESULTADOS.md) e a [avaliação histórica](tcc2/AVALIACAO_TCCII_JEV_V2.md) identificam separadamente as evidências. A plataforma preparada não equivale a pesquisa de campo realizada.

## Estrutura do repositório

| Caminho | Conteúdo |
|---|---|
| [`code/src/rag_baseline/`](../code/src/rag_baseline/) | Pipeline normativo e interpretação conversacional |
| [`code/src/service/`](../code/src/service/), `core/`, `agents/`, `memory/`, `schema/` | API, configuração, agentes, checkpointer e contratos |
| [`code/src/streamlit_app.py`](../code/src/streamlit_app.py), `chat_ui/`, `static/bisco/`, `client/` | Interface Bisco e cliente HTTP |
| [`code/tests/`](../code/tests/) | Testes offline, sem provedor |
| [`data/`](../data/) | Registro normativo, PDF da graduação e questões do trabalho anterior |
| [`evaluation/corpora/`](../evaluation/corpora/) | Textos estruturados das quatro resoluções |
| [`evaluation/datasets/`](../evaluation/datasets/) | Golds candidatos/revisados, conjuntos temporais e regressões |
| [`evaluation/results/`](../evaluation/results/) | Evidências históricas preservadas na publicação |
| [`evaluation/adaptive_rag/`](../evaluation/adaptive_rag/) | Executor de comparações anteriores |
| [`deploy/`](../deploy/), [`compose.demo.yaml`](../compose.demo.yaml), [`scripts/`](../scripts/) | Imagens, launcher, healthcheck e demonstração local |
| [`docs/tcc2/`](tcc2/) | Arquitetura histórica, avaliação por QP e roteiro de implantação |

O [layout de artefatos](../evaluation/ARTIFACT_LAYOUT.md) distingue projeções publicadas e dados históricos não incluídos. O índice Chroma e segredos não são versionados.

## Créditos e licenças

- **Base de engenharia:** `code/` deriva do *agent-service-toolkit*, de Joshua Carroll, sob a [licença MIT existente](../code/LICENSE), preservada sem alteração.
- **Trabalho anterior:** o assistente para a Resolução 177/2012 foi desenvolvido por Guilherme Torres Melo e Armando Soares Sousa. Seu histórico e seus resultados pertencem ao trabalho anterior.
- **TCC II:** Wesley de Sousa Coutinho, Bacharelado em Ciência da Computação da UFPI, sob orientação do Prof. Armando Soares Sousa. As contribuições incluem acervo multinormativo, filtro de versões, verificação, camada conversacional, interface e infraestrutura. Essas contribuições estão sob a [licença MIT](../LICENSE). Os textos das resoluções do acervo são documentos oficiais da UFPI e não são cobertos por essa licença.
- **Normas:** atos públicos obtidos de fontes institucionais, fornecidos para pesquisa; prevalecem os documentos oficiais.
- **Identidade visual:** Bisco foi criado para o protótipo e não é marca da UFPI. A fonte Google Sans segue a licença OFL em [`code/src/static/fonts/`](../code/src/static/fonts/).

## Referências do trabalho

Referências já presentes na documentação do projeto; as entradas completas e conferidas estão no texto do TCC II:

- Lewis, P. et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. NeurIPS, 2020.
- Gao, Y. et al. Retrieval-Augmented Generation for Large Language Models: A Survey. 2023.
- Es, S. et al. Ragas: Automated Evaluation of Retrieval Augmented Generation. EACL (demo), 2024.
- Murugaraj, K. et al. RAGVUE: a diagnostic view for explainable RAG evaluation. EACL (demo), 2026.
- Min, S. et al. AmbigQA: Answering Ambiguous Open-domain Questions. EMNLP, 2020.
- Livathinos, N. et al. Docling: an efficient open-source toolkit for AI-driven document conversion. 2025.
- Melo, G. T.; Sousa, A. S. Protótipo de Assistente Virtual Baseado em RAG para Consulta às Normas da UFPI: um estudo de caso. UFPI.
