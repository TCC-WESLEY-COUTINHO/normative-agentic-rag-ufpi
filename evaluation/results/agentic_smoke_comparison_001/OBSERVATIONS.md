# Smoke funcional A/B/C/D — candidato, sem inferência confirmatória

As quatro condições finais usaram o código `5213881993618edff095a053d265426ae6e6a5b7`,
os mesmos quatro itens de `agentic_smoke_v1.json`, índice conjunto de 438 chunks,
modelo principal e Router `qwen/qwen3-30b-a3b-instruct-2507`, embedding
`openai/text-embedding-3-small`, temperatura zero e top_k=5. Os quatro manifestos
registram `inputs_dirty=false`; seus insumos e JSONL foram conferidos por SHA-256.
O prompt principal V2 permaneceu inalterado. Uma execução por condição; sem participantes.

| Condição | Falhas | Rotas corretas | Recall@5 médio | Wrong-norm@5 por origem | Gerações |
|---|---:|---:|---:|---:|---:|
| [A — oracle](../agentic_smoke_A_001/manifest.json) | 0/4 | não usa Router | 0,50 | 0 | 3 |
| [B — ambas](../agentic_smoke_B_001/manifest.json) | 0/4 | não usa Router | 0,50 | 0,0667 | 4 |
| [C — Router](../agentic_smoke_C_001/manifest.json) | 0/4 | 4/4 | 0,50 | 0 | 3 |
| [D — Router + vigência](../agentic_smoke_D_003/manifest.json) | 0/4 | 4/4 | 0,50 | 0 | 3 |

As métricas de retrieval têm denominador **três perguntas respondíveis**. A pergunta
ambígua é excluída delas. A/E não têm setor oracle para a ambígua e não geram resposta
nesse item; B consulta ambas e chama o gerador; C/D identificam esclarecimento sem
recuperar contexto nem gerar resposta normativa. Precisão e recall de esclarecimento
em C/D são 1/1; a matriz de confusão tem um caso em cada diagonal das quatro classes.
Esses números não estimam desempenho populacional.

## Diagnóstico por pergunta

- `SMOKE-001`, graduação: Router selecionou graduação; os cinco contextos eram desse
  setor, mas o art. 111 candidato não foi recuperado. Recall@5=0 em A/B/C/D.
- `SMOKE-002`, defesa na pós: Router selecionou pós; o art. 3 candidato apareceu
  na quarta posição. Recall@5=1 em todas as condições.
- `SMOKE-003`, comparação de frequência: Router selecionou ambas; o art. 20 da pós
  foi recuperado, e o art. 111 da graduação não. Recall@5=0,5 em todas as condições.
- `SMOKE-004`, cancelamento sem nível: C/D solicitaram esclarecimento, com zero
  contextos entregues ao gerador; não se inventou resposta de aluno.

Wrong-norm mede origem do contexto, não erro jurídico. O único contexto de outro
setor em B nas perguntas respondíveis foi o art. 20 da pós na consulta de frequência
da graduação; os snapshots compartilham o limiar de frequência. Não tratar essa
redução de origem cruzada como prova de melhora da correção normativa.

## Vigência e evidência documental

A 658/2024 não está ingerida. Obsolete Context Rate@5 e Compliance Violation Rate
foram zero, e a contagem de remoções posteriores foi zero. Isso **não testa H_version**:
não havia contexto da norma obsoleta no índice. A exclusão prévia de sua fonte está
auditada separadamente em D. Current-Norm Hit@5 não se aplica aos quatro itens do smoke.
Os testes de vigência com fixtures verificam o mecanismo, sem simular uma ingestão real.

O art. 62, VI, da 956/2025 foi conferido no corpus e visualmente na página 18 do PDF
local (numeração impressa 17): lista expressamente a Resolução 658, de 22 de abril de
2024, entre as revogadas. O art. 63 condiciona a entrada em vigor à publicação;
a data de assinatura não foi usada como prova da publicação.

Fonte local: `ingest_documents/data/raw/samples/Resolução n 956 de Dezembro PRPG_2025.pdf`;
SHA-256 `d4b0861f5c3211fcf59c702577cfadc4633b16301dfa23748bfce410ef37ab9a`.
Essa conferência documental não substitui a revisão independente do dataset.
Não foi comprovada substituição material de artigos da 658, nem criada resposta
baseada em texto ausente dessa norma.

## Exploração anterior preservada

[D_001](../agentic_smoke_D_001/summary.json) teve 3/4 rotas corretas: a comparação
foi encaminhada para esclarecer. Também apresentou motivos categóricos incompatíveis
com algumas rotas. Depois desse resultado, o prompt exclusivo do Router recebeu
exemplos e descrições de schema, e sua validação passou a rejeitar motivos incoerentes.
[D_002](../agentic_smoke_D_002/summary.json) teve 4/4 rotas corretas, mas representa
snapshot intermediário com fontes modificadas, identificado pelos hashes do manifesto.
Não foi usado como condição D final na tabela. Nenhum desses resultados foi sobrescrito.

O gabarito, qrels, corpora, modelo principal, embedding, temperatura, top_k e prompt
de geração não foram ajustados em função das saídas. O smoke após ajuste de Router
continua sendo desenvolvimento; não constitui teste independente de generalização.

## Limites e próxima avaliação

Quatro exemplos funcionais são insuficientes para testar as hipóteses. As respostas
não receberam notas humanas: todos os campos de julgamento permanecem nulos. RAGAS
não foi executado. O indexador legado não conserva recibo do modelo que originou cada
vetor; a configuração atual foi registrada e a identidade textual/metadados do índice
foi validada, sem alegar certificação da origem dos vetores.

Revisar primeiro os datasets candidatos e evidências com avaliadores;
congelar depois uma execução confirmatória A/B/C/D dos itens revisados. Para avaliar
H_version, obter e ingerir legitimamente o texto anterior antes de congelar os casos.
Somente após essas etapas preparar o estudo com participantes, segundo orientação
e procedimento ético aplicável. Protocolo e denominadores em
[protocol_agentic_v1.md](../../protocol_agentic_v1.md). Resultados completos, agrupados
por setor/categoria/norma, e hashes em [comparison.json](comparison.json).
