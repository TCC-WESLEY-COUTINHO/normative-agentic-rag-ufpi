# Piloto 001 — RAG com graduação e pós-graduação

> **Registro histórico.** Configuração, resultados, contagens de testes e estados descritos referem-se à execução documentada, anterior à v3.4. Para a versão atual, consulte o [guia de evidências e reprodução](../../README.md).

## Resultado e alcance

Foram concluídos 40 pares (80 respostas), sem erro de API, com os dois regulamentos no índice conjunto. O Recall@5 médio caiu de **0,875 para 0,850**: diferença conjunto menos isolado de **−2,5 pontos percentuais**, com intervalo bootstrap percentil 95% **[−7,5; 0,0] p.p.**. O intervalo inclui zero. Há uma perda localizada de cobertura de evidência anotada; este piloto **não demonstra insuficiência geral de RAG**, nem superioridade de uma abordagem agêntica. Não foi calculada acurácia normativa das respostas.

Execução em 19/10/2026 UTC, aproximadamente 377,6 segundos, código/protocolo/datasets congelados no commit `b1888816cdc995eff1ddc92a06f6587db74c78a4`. Dados originais em [rows.jsonl](rows.jsonl), resumo automático em [summary.json](summary.json) e configuração/hashes/recibos em [manifest.json](manifest.json). Este relatório é posterior à execução e não altera as hipóteses prévias.

## Condições realmente executadas

- 376 chunks da graduação e 62 da pós; índice conjunto com **438 chunks**, separado do banco interativo.
- 20 perguntas candidatas por nível, sempre com norma/nível explícitos; mesmas perguntas e embeddings nas duas condições.
- Controle isolado com norma correta fornecida por construção (oracle), comparado ao conjunto sem filtro ou reranker.
- Embedding `openai/text-embedding-3-small`; geração `qwen/qwen3-30b-a3b-instruct-2507`; temperatura 0; top-k 5; máximo 800 tokens; uma execução por condição.
- 18 hashes do manifesto conferidos contra os arquivos utilizados; 80 combinações distintas pergunta/condição; métricas de todas as linhas e resumo recalculados e conferidos. As contagens 376/62/438 foram verificadas na indexação.

Os SHA-256 registram bytes do ambiente Windows da execução. Conversão automática LF/CRLF pelo Git pode alterar hashes em outro checkout mesmo sem mudança textual; registrar essa diferença de ambiente, sem afirmar que hashes divergentes coincidem. O commit identifica a versão lógica dos arquivos, enquanto os hashes identificam os bytes utilizados neste piloto.

## Recuperação

Recall é cobertura dos pares `(norma, artigo)` anotados, não porcentagem de respostas corretas. Completo significa todas as evidências anotadas presentes no top-5; mistura significa fração de chunks de outra norma.

| Nível (perguntas por condição) | Condição | Recall@5 | MRR@5 | nDCG@5 | Evidência completa@5 | Mistura de norma@5 |
|---|---|---:|---:|---:|---:|---:|
| Graduação (20) | Isolado | 0,850 | 0,756 | 0,756 | 0,800 | 0,000 |
| Graduação (20) | Conjunto | 0,850 | 0,756 | 0,756 | 0,800 | 0,020 |
| Pós (20) | Isolado | 0,900 | 0,835 | 0,851 | 0,900 | 0,000 |
| Pós (20) | Conjunto | 0,850 | 0,767 | 0,788 | 0,850 | 0,430 |
| Geral (40) | Isolado | 0,875 | 0,795 | 0,803 | 0,850 | 0,000 |
| Geral (40) | Conjunto | 0,850 | 0,761 | 0,772 | 0,825 | 0,225 |

O índice conjunto recuperou ao menos uma evidência anotada em 35/40 perguntas, contra 36/40 no isolado. Recuperou todas em 33/40, contra 34/40. Em 39 pares o Recall@5 foi idêntico; em um par diminuiu; nenhum melhorou nessa métrica. Igualdade de recall não implica igualdade de ranking, contexto ou resposta.

| Contraste pareado conjunto − isolado | Diferença de Recall@5 | IC bootstrap 95% | Pares |
|---|---:|---:|---:|
| Geral (primário) | −2,5 p.p. | [−7,5; 0,0] p.p. | 40 |
| Graduação (suplementar) | 0,0 p.p. | [0,0; 0,0] p.p. | 20 |
| Pós (suplementar) | −5,0 p.p. | [−15,0; 0,0] p.p. | 20 |

O suplemento [per_norm_summary.json](per_norm_summary.json) foi calculado depois da execução porque o runner original registrava somente IC macro. Usa 5.000 reamostragens, semente 956, o mesmo estimador por nível, sem novas chamadas remotas ou alteração dos dados. O intervalo degenerado da graduação reflete os deltas observados todos iguais a zero; não demonstra equivalência populacional. Nenhum teste confirmatório ou p-valor é alegado. Os intervalos são condicionais à amostra intencional e podem ser otimistas porque perguntas compartilham artigos.

## Registro dos casos

As respostas e os contextos integrais permanecem em `rows.jsonl`. As métricas de recuperação não estabelecem correção normativa das respostas.

## Limitações descobertas na inspeção

**Identificação de fonte não uniforme no contexto do LLM.** A graduação chega como `Regulamento Geral da Graduação da UFPI`, sem o número 177/2012 no campo fonte; a pós chega como `Resolução CEPEX/UFPI nº 956/2025`. Os IDs e os embeddings identificam ambas, mas o formatador de contexto não mostra esses IDs. Na GRAD-004, por exemplo, o modelo alega não haver a resolução pedida, mesmo vendo artigos do corpus atribuído a ela. Isso afeta interpretação de geração e é uma limitação da apresentação das fontes; não deve ser atribuída ao mecanismo RAG em geral. Corrigir de modo uniforme requer novo protocolo/execução, preservando este piloto.

**Gold ainda candidato.** Perguntas/referências foram auditadas contra texto extraído; essa auditoria não certifica equivalência aos PDFs nem correção normativa. Qrels são parciais; faltam julgamentos de artigos alternativos. O snapshot da pós não contém o art. 30. O corpus de graduação inclui referências a alterações posteriores; este trabalho não certifica vigência jurídica nem equivalência ao texto original de 2012.

**Generalização limitada.** Conjuntos de desenvolvimento intencionais, 20 por nível, tamanhos de corpus/dificuldades/cardinalidades de evidência distintos, uma geração por condição e busca aproximada. Não comparar 90% da pós com 85% da graduação como medida direta de dificuldade equivalente. O contraste pareado dentro de cada nível é mais defensável. Não se mediu roteamento aprendido, detecção de escopo, perguntas irrespondíveis, suficiência para uso real ou qualquer sistema agêntico.

**Mistura não equivale a erro.** Os 43% de chunks da graduação nas consultas da pós no índice conjunto não são 43% de respostas incorretas. Acurácia de resposta, cobertura factual e qualidade de citações não foram avaliadas. Token F1 disponível por linha é sobreposição lexical, não validação semântica.

## Uso, verificação e revisão

Recibos registrados: 80 gerações (170.580 tokens totais, soma do campo `usage.cost` = 0,02011722) e 8 requisições de embedding (99.947 tokens, soma = 0,00199894). Esses são valores informados pelo provedor, não estimativa a partir de tabela atual de preços nem medição completa de custo computacional. O tempo total inclui rede, embeddings, indexação e concorrência; não constitui benchmark de latência entre arquiteturas.

Validação local via uv: `uv run --no-sync pytest -q` terminou com **120 passed, 2 skipped, 4 warnings**. Avisos: duas ocorrências de depreciação Pydantic em dependência LangChain; coroutine de AsyncMock não aguardada em `test_astream`; depreciação de timeout de TestClient em `test_agent_stream`. Não houve falha. Ruff do pós-processador e seu teste passou. Testes locais novos ficam ignorados por solicitação do usuário; os testes já rastreados foram preservados.

Há 80 entradas em [review_template.json](review_template.json), com campos de revisão nulos. Entregar cópias independentes a dois avaliadores sem a chave [blinding_key.json](blinding_key.json), sem respostas identificadas por condição e sem este relatório. A chave é pública para auditoria: cegamento operacional depende do controle do material entregue. Avaliadores devem consultar os PDFs completos e registrar divergências/adjudicação.

## Conclusão utilizável no TCC

Neste piloto exploratório, a inclusão da segunda resolução reduziu a cobertura média das evidências anotadas em 2,5 p.p., concentrada em uma pergunta da pós, e introduziu documentos de outra norma nos contextos. O intervalo descritivo inclui ausência de diferença. Foram identificadas falhas de recuperação e indícios qualitativos de generalização indevida a partir de contexto incompleto, além de um problema de apresentação de fontes. Os resultados justificam investigar melhorias, **mas não comprovam que apenas RAG é insuficiente nem que agentes resolveriam os problemas**.

A etapa confirmatória exige gold revisado, metadados de fonte uniformes, perguntas novas independentes, critérios de suficiência previamente definidos e comparação controlada com alternativas simples (filtro, híbrido, reranking) antes de atribuir ganho a agentes. Fundamentação metodológica e referências estão no [protocolo](../../protocol.md), [registro de decisões](../../decisions.md) e [BibTeX](../../references.bib).
