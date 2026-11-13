# Protocolo agentic V1 — roteamento e elegibilidade normativa

Snapshot candidato, pendente de revisão. Este protocolo deve ser congelado
antes de qualquer nova chamada experimental. Não altera datasets, qrels ou resultados V1/V2.

## Hipóteses e condições

- **H_router:** o Router reduz contexto de norma indevida em comparação à recuperação
  conjunta sem roteamento.
- **H_clarification:** consultas sem nível suficiente provocam mais esclarecimentos
  apropriados que na baseline, que pode escolher uma regra diretamente.
- **H_version:** exclusão de normas explicitamente obsoletas reduz sua exposição ao
  gerador em perguntas atuais. Sem corpus obsoleto ingerido, esta hipótese não é testável
  por comparação real; testes com fixtures verificam somente o mecanismo.

| Condição | Escopo | Filtro de vigência |
|---|---|---|
| A `oracle` | rótulo candidato explícito | desligado |
| B `both` | ambas | desligado |
| C `router` | decisão do modelo | desligado |
| D `router-version` | decisão do modelo | ligado |
| E `oracle-version` (diagnóstico) | rótulo candidato explícito | ligado |

Em A/E, itens anotados como esclarecer não têm setor oracle. São registrados como
`oracle_not_applicable=true`, sem retrieval/geração. Em C/D, nenhuma resposta de
esclarecimento é inventada no batch. Os quatro modos preservam o texto original e
o mesmo prompt principal V2, modelo, embedding, temperatura configurada e top_k=5.
A entrada do Router contém somente pergunta e eventual esclarecimento, nunca gold.

## Datasets e identificação

Usar os 40 itens candidatos de `datasets/graduacao_v2.json` e
`datasets/pos_graduacao_v2.json`, preservando evidências e respostas. A correspondência
`answer→responder`, `clarify→esclarecer` e `sector→expected_scope` é registrada em
`datasets/router_labels_v1.json`. Itens `clarify` recebem escopo nulo. Isso não constitui
revisão nem reclassificação após observar saídas. O manifesto de cada execução
persiste a lista de IDs, rótulos derivados e SHA-256 dos arquivos originais.

`datasets/agentic_smoke_v1.json` contém quatro verificações funcionais pré-definidas:
graduação, pós, ambas e ambígua. É teste de funcionamento, sem poder confirmatório.
`datasets/temporal_candidates_v1.json` contém um caso documental do art. 62, VI,
da 956/2025; não representa recuperação de conteúdo da 658/2024.

## Registry e estratégia de recuperação

`data/normative_registry.json` exige identificação estável, fontes exatas, setor,
status e base textual para afirmações temporais. Na carga, a evidência deve coincidir
com o corpus indicado. A 658/2024 é expressamente revogada no art. 62, VI, da 956/2025.
Seu texto não foi encontrado nos dados/corpus/histórico local auditados; ela não foi
ingerida. Não se afirma alteração material de qualquer artigo da 658.

177/2012 e 956/2025 permanecem `desconhecida` quanto à certificação integral de vigência:
o snapshot da graduação contém alterações parciais; o art. 63 da pós condiciona eficácia
à publicação, cuja data oficial não foi demonstrada. Desconhecida é preservada e auditada.
O registro não certifica ausência de revogações posteriores nem resolve aplicação
intertemporal/retroatividade/direito adquirido. Artigos parcialmente revogados na
consolidação da graduação não são removidos pelo filtro V1 de normas inteiras.

Nas condições com filtro, Chroma aplica `$nin` às fontes explicitamente obsoletas,
combinado com o setor, **antes** da seleção final de cinco candidatos. Não há over-fetch,
reranking, nova indexação ou alteração de embedding. Uma segunda checagem pelo registry
remove candidatos obsoletos que escapem do pré-filtro. A auditoria distingue:
exclusões normativas prévias, candidatos efetivamente recuperados, remoções posteriores
com sua base, contexto final e `shortfall` para cinco. Pré-exclusão não é contada como
chunk recuperado/removido. Se faltarem candidatos elegíveis, reportar o número real;
nunca completar com contexto obsoleto.

Somente intenção histórica explícita (`historicamente`, `na época`, `como era`,
`qual era`, `quais eram`, `regra antiga`) libera contexto obsoleto com aviso de status
no contexto enviado ao gerador. Citar o número de uma norma antiga não libera o filtro.
A presença de `atual`, `atualmente`, `hoje`, `agora` ou `vigente` na pergunta ou no
esclarecimento dá precedência à
consulta atual. A heurística é conservadora e limitada; não constitui motor jurídico temporal.

## Métricas e denominadores

- Router: acerto de escopo/ação entre decisões, erro = 1 − acerto; matriz de confusão
  graduação/pós/ambas/esclarecer. Recall de esclarecimento divide pelos itens cujo
  rótulo exige esclarecer; precisão divide pelas decisões de esclarecer. Falha do
  Router não recebe crédito como esclarecimento correto. Falha posterior de geração
  não muda a classificação de rota. Condições manuais têm métricas de Router nulas.
- Retrieval: reutiliza Recall@1/3/5, Hit@5, Evidence-complete@5, MRR@5, nDCG@5 e
  Wrong-norm@5, por `(norm_id, artigo)`. Ambíguas ficam fora desses denominadores.
  Para comparações, ambas as normas esperadas são elegíveis no Wrong-norm. Conjuntos
  alternativos suficientes já declarados no V2 continuam válidos. Wrong-norm por
  origem não equivale a erro jurídico, especialmente no caso de frequência comum.
- Obsolete Context Rate@5: contextos conhecidos como revogados/substituídos enviados
  como atuais / contextos enviados, com microagregação e contagens explícitas.
- Compliance Violation Rate: perguntas com ao menos um desses contextos / perguntas
  em que o gerador foi chamado. Esclarecimentos sem geração não entram no denominador.
- Current-Norm Hit@5: presença de qualquer par aplicável explicitamente anotado em
  `current_evidence`; indefinido quando não há qrels temporais.
- Remoções: contagem por motivo pós-retrieval; exclusões prévias são diagnóstico separado.
  Índices sem candidatos obsoletos não demonstram eficácia temporal mesmo com taxa zero.

Reportar erros e denominadores. Manter análise por nível e categoria. Novas execuções
confirmatórias exigem revisão e congelamento anterior de amostra/configuração;
os smoke tests e os V2 de desenvolvimento não comprovam hipóteses gerais.

## Reprodução

Na pasta `code/`, com a API key já configurada e o índice conjunto existente:

```powershell
uv run python -m rag_baseline.experiment_v2 --validate-only
uv run python -m rag_baseline.experiment_v2 --condition oracle --output ../evaluation/results/agentic_A_001
uv run python -m rag_baseline.experiment_v2 --condition both --output ../evaluation/results/agentic_B_001
uv run python -m rag_baseline.experiment_v2 --condition router --output ../evaluation/results/agentic_C_001
uv run python -m rag_baseline.experiment_v2 --condition router-version --output ../evaluation/results/agentic_D_001
# Smoke funcional, separado da avaliação dos 40 itens:
uv run python -m rag_baseline.experiment_v2 --condition router-version --dataset ../evaluation/datasets/agentic_smoke_v1.json --output ../evaluation/results/agentic_smoke_001
```

Cada diretório deve ser novo. O runner verifica os IDs/textos e todos os metadados
normalizados do índice, incluindo artigo e hierarquia,
contra os corpora e falha sem alterá-lo se divergir. O manifesto registra commit,
estado sujo, hashes de código/dados/registry/prompts/lockfile, modelo principal/Router,
embedding, top_k, temperatura, condição, tempo e falhas. Preservar JSONL bruto,
recibos de uso disponíveis, referências pré/pós, exclusões e métricas. Nenhuma chave,
raciocínio interno ou nota humana automática é salva. SHA do manifesto/protocolo
permite identificar o snapshot exato mesmo antes de um commit dos resultados.
`inputs_dirty` distingue alterações nos insumos congelados de resultados novos ainda
não commitados. O indexador herdado não registra o modelo de origem de cada vetor;
essa limitação é explicitada no manifesto, sem reindexação automática nesta feature.

Os smoke D_001 e D_002 são exploração de desenvolvimento preservada. Após D_001,
o prompt exclusivo do Router recebeu exemplos das quatro ações e descrições no schema;
a validação passou a rejeitar motivo incompatível com o escopo. O prompt de geração,
os dados candidatos, modelo, embedding, temperatura e top_k permaneceram os mesmos.
Não usar a repetição de smoke após ajuste como estimativa confirmatória.

RAGAS fica como extensão opcional de avaliação; não é dependência do runtime, requisito
de execução ou validação jurídica. Não foi introduzido upgrade de dependências.
O Router segue a arquitetura multiagente já proposta no TCC I; não é atribuído a
Sonapuram. A inspiração compliance-aware temporal não implica reprodução de resultados
ou afirmações bibliográficas adicionais.

## Avaliação e futuro estudo com alunos

Dois revisores independentes devem primeiro conferir corpus, rótulos candidatos,
respostas de referência, fatos e bases normativas. Para respostas geradas, preservar:
correção 0/1/2; cobertura 0/1 por fato obrigatório; suporte 0/1 por afirmação;
mistura indevida 0/1; precisão/cobertura de citações. Campos ficam nulos até revisão.
LLM judge não substitui anotador humano.

Somente depois da revisão e execução confirmatória comparar grupos de graduação/pós:
controle consulta normas; experimental usa protótipo. Preparar medidas de correção,
tempo e referência normativa, sem revelar gold aos participantes. Nenhum recrutamento
ou coleta é feito aqui; qualquer coleta futura depende da orientação responsável e
do procedimento ético aplicável.
