# Resultados exploratórios e limitações

Todos os resultados abaixo são **exploratórios**, obtidos em conjuntos de desenvolvimento. Amostras pequenas e uma repetição em parte das rodadas limitam as conclusões. Não há demonstração de generalização para dúvidas acadêmicas em geral. O sistema é um protótipo de pesquisa, não um serviço oficial da UFPI.

O contraste é entre **v3.4**, com geração ancorada em citação e corpus canônico v4, e **v2**, com texto livre e guard de saída. As [condições e sua proveniência](PROVENIENCIA.md) devem acompanhar a leitura das métricas.

## C2: perguntas isoladas

Conjunto oficial C2: **40 perguntas**, com a mesma recuperação nas duas condições, **uma repetição**, no mesmo dia, índice e executor. Os desfechos de resposta usam as **22 perguntas que pedem resposta**.

| Métrica | v3.4 | v2 |
|---|---:|---:|
| Ação correta | 0,925 | 0,900 |
| Respostas aceitas sem contingência | 0,818 | 0,636 |
| Contingência | 0,091 | 0,273 |
| Recall@5 | 0,886 | 0,886 |
| MRR@5 | 0,909 | 0,909 |
| Referência cita o dispositivo do gold | 100 % | 100 % |

A coincidência da referência com o dispositivo do gold e as métricas de recuperação não demonstram, sozinhas, correção do sentido da resposta.

## Conjunto sintético

São **40 perguntas**, em conjunto pré-registrado. **Esse conjunto orientou o desenvolvimento da v3.4**, com risco de sobreajuste.

| Métrica | v3.4 | v2 |
|---|---:|---:|
| Fração de frases sem suporte ou contraditas | 0,024 | 0,116 |
| Ação correta | 0,817 | 0,758 |

A diferença da fração de frases sem suporte ou contraditas é **−0,092**, com **IC 95 % [−0,190; −0,019]**. Esse resultado exploratório não deve ser interpretado como estimativa para perguntas novas em geral.

## Conjunto complexo

São **31 perguntas**, com síntese, exceção, caso concreto, alteração no tempo, premissa falsa, ausência de resposta nas normas, ambiguidade e comparação, publicadas em [`gold_v3_complexo.json`](../evaluation/datasets/gold_v3_complexo.json) ([descrição e construção](../evaluation/datasets/README_GOLD_V3.md)). **A v3.4 não superou a v2 neste conjunto.**

| Métrica | v3.4 | v2 |
|---|---:|---:|
| Frases com conteúdo entregues | 41 | 123 |
| Completude | 0,34 | 0,49 |
| Fração de frases sem suporte | 0,122 | 0,098 |
| Recusas corretas quando as normas não regulam o assunto | 3/4 | 1/4 |

O intervalo de confiança da comparação de frases sem suporte é largo, sem diferença demonstrável. A v3.4 entrega menos conteúdo e erra mais em exceções. Perguntas temporais e de comparação continuam difíceis para as duas condições. Maior cautela na saída não representa ganho geral de qualidade.

## Procedimento de anotação

A fidelidade por frase foi anotada com um procedimento de rotulagem preliminar automatizada, com decisão do pesquisador nos casos de divergência; o protocolo completo está no texto do TCC.

## Limitações

- **Verificação de forma:** o verificador confere literalidade da citação, números e prazos, dispositivo, nível, norma da evidência e negações acrescentadas. Não confere implicação semântica; erros de sentido podem passar.
- **Tempo e comparação:** distinguir redações, alterações e níveis de ensino continua sendo um ponto fraco.
- **Conteúdo omitido:** afirmações reprovadas são omitidas e viram ressalvas; sem conclusão verificada, o sistema se abstém. Isso pode reduzir a completude.
- **Validade externa:** conjuntos pequenos, de desenvolvimento; parte das rodadas tem uma repetição. O conjunto sintético foi usado para orientar a implementação.
- **Dependências externas:** a Decisions API é alpha, e os modelos e a API do provedor podem mudar. A demonstração não fixa a rota de provedor da geração, enquanto os experimentos fixaram um provedor; uma nova execução pode variar.
- **Acervo:** restrito às quatro resoluções; parte dos textos provém de OCR. Quando a publicação não foi comprovada, o estado de vigência é declarado como desconhecido.

## Evidência histórica e reprodução

As evidências anteriores de escopo, esclarecimento, versão e verificação continuam em [Avaliação histórica por questão de pesquisa](tcc2/AVALIACAO_TCCII_JEV_V2.md). Elas identificam A, A′ e A″-J v1/v2; seus números, denominadores e golds não são intercambiáveis com a comparação v3.4 × v2 acima.

Os dados brutos finais e as anotações não integram este snapshot público. O guia de [reprodução](REPRODUCAO.md) separa as verificações offline disponíveis dos recálculos que dependem de insumos externos ao repositório.
