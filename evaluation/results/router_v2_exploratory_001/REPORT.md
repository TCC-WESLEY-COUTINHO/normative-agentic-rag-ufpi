# Router V1 × V2-D × V2-L — experimento exploratório

> **Registro histórico.** Configuração, resultados, contagens de testes e estados descritos referem-se à execução documentada, anterior à v3.4. Para a versão atual, consulte o [guia de evidências e reprodução](../../README.md).

28/10/2026. As duas cascatas recuperaram rotas nos casos F1 conhecidos, mas
**nenhuma melhorou o resultado geral do TEST candidato**. V1 acertou 16/23;
V2-D, 12/23; V2-L, 13/23. A redução de esclarecimentos indevidos veio acompanhada
de roteamento indevido de perguntas ambíguas. V1 continua sendo o padrão.
Os resultados não constituem avaliação jurídica, validação dos rótulos ou inferência confirmatória.

## Estado inicial, commits e congelamento

Estado inicial observado: branch `fix/agentic-failure-analysis-v1`, HEAD
`832d41da6ecfaba009dc3653fe87666d9fa47517`, árvore limpa. Antes das alterações
foram conferidos status, branch, HEAD, dez commits, diff, diff cached e diff stat.
Não foi necessário checkpoint. A branch local
`feat/adaptive-router-v2-experiment` partiu exatamente desse HEAD.

Os insumos e hipóteses foram commitados antes das chamadas DEV. Commits locais:

1. `6623588` — probe, políticas, integração, testes, dataset e protocolo.
2. `340811b` — normalização de caminhos de objetos Git no preflight Windows.
3. `5ea05ce` — calibração DEV, threshold e errata de compatibilidade do preflight.
4. O commit de evidência que contém este relatório reúne TEST, estabilidade,
   demos e preservação final; seu hash é informado na entrega.

Duas tentativas abortaram **antes de chamadas externas e da criação dos diretórios
de execução**: [preflight 1](preflight_001.json), [preflight 2](preflight_002.json).
A primeira corrigiu `HEAD:path`; a segunda corrigiu também o argumento de
`git hash-object`, que recebia barras Windows e produzia falso dirty por CRLF.
Ambos os estilos de caminho foram conferidos contra o blob real commitado.

DEV executou em `340811b`. Seu [manifesto](dev_001/manifest.json), capturas e
[threshold original](dev_001/frozen_threshold.json) permanecem byte a byte iguais.
Antes de qualquer chamada TEST, o último commit local de calibração foi emendado
para incluir a correção de compatibilidade. O commit local anterior à emenda era
`2dd3ffa7086eb21a7d90624b2ab1c352e28ee088`; não havia publicação remota.
O [artefato compatível](dev_001/frozen_threshold_windows_v1.json) registra o hash
do original, das linhas DEV, o commit efetivo, a única diferença de hash no runner
e a manutenção de políticas, prompts, dados, configuração e threshold **0,65**.
TEST e estabilidade executaram em `5ea05ce`. Não houve recalibração nem observação
TEST usada nessa correção. Os manifestos registram `production_inputs_dirty=false`.

## Hipóteses, políticas e fronteira do probe

O [protocolo pré-experimental](../../protocol_router_v2_v1.md) registrou:

- H_ROUTER: recuperação exploratória pode ajudar decisões não resolvidas pela intenção.
- H_D: distribuição determinística pode ser mais estável e menos custosa que outro LLM.
- H_L: um judge com metadados pode distinguir melhor ambiguidades semânticas.

R0=`intent_v1`: fonte, prompt, schema, parser e fallback originais preservados.
R1=`adaptive_distribution_v2` e R2=`adaptive_llm_v2`: primeiro executam V1.
Uma rota direta válida, inclusive `ambas`, encerra a decisão sem probe/judge.
Esclarecimento ou fallback ativa o probe; não existe classificador anterior ao V1.

No experimento pareado há **uma chamada V1 compartilhada**, e, se necessária,
uma chamada de embedding e uma consulta global top-10. R1 e R2 recebem exatamente
o mesmo `ProbeResult`; hashes e payloads foram conferidos em todos os 126 pares.
São **378 linhas no total**, três por par: 129 DEV, 69 TEST e 180 de
estabilidade. Cada série registra as chamadas físicas compartilhadas separadamente.

O probe lê a coleção existente, sem filtro temporal, geração, reescrita ou
reindexação. `ProbeHit` contém rank, ID, norma, setor e distância. `ProbeResult`
preserva a ordem e inclui counts, melhores ranks/distâncias, massas, shares,
top-1, domínios presentes/dominante, quantidade desconhecida, gap e estatísticas.
Setores desconhecidos permanecem na auditoria, fora dos agregados por domínio.
Texto completo de chunk não integra o objeto entregue aos decisores.

`rank_mass(d) = Σ 1/rank`; `share(d) = mass(d)/Σ mass` dos setores conhecidos.
O parâmetro Chroma observado é **cosine**: menor distância é melhor. Distâncias
são diagnósticas; não foram convertidas em `1-distance` nem em confiança calibrada.
Dominância também não é probabilidade do nível acadêmico do usuário.

R1 resolve para o único domínio conhecido. Havendo dois, usa o dominante somente
se share >= threshold, inclusive no limite; caso contrário esclarece. Probe vazio
ou sem setores conhecidos esclarece. A política nunca cria `ambas` a partir de
mistura de hits.

R2 recebe exatamente `{"query": pergunta_original, "probe": metadados_estruturados}`.
Não recebe respostas, gold, expected_scope/action, texto integral de chunks,
Version Filter ou saída de generator. Usa o mesmo
`qwen/qwen3-30b-a3b-instruct-2507` de V1, temperatura zero e máximo de 800 tokens.
O schema tem `scope`, `needs_clarification`, `reason_code` e `clarification_question`.
Motivos: `probe_supports_graduacao`, `probe_supports_pos`, `cross_domain_request`,
`conflicting_probe_evidence` e `insufficient_probe_evidence`.
`ambas` exige solicitação textual explícita; a validação posterior tem cobertura
lexical limitada e não é um classificador semântico geral. Saída inválida/erro
retorna esclarecimento conservador e entra nas métricas como falha.

Na integração LangGraph, somente o vetor da query pode seguir ao retrieval final:
top-5, escopo decidido e Version Filter existente. Um probe ativado gera um único
embedding, reutilizado no retrieval final. Hits/textos do probe não seguem ao
generator. O teste de integração verifica esses limites. As chamadas científicas
desta comparação medem **somente roteamento**, sem retrieval final ou geração.

## Dataset candidato e separação

[Dataset derivado](../../datasets/routing_v2_candidates_v1.json): 66 perguntas,
43 DEV e 23 TEST. SHA-256:
`c435ce6e732bc5a1837b3f4f529dd300604d032180a66d177cc4231006249264`.

| Categoria | DEV | TEST |
|---|---:|---:|
| explicit_graduacao | 11 | 3 |
| explicit_pos | 16 | 8 |
| cross_domain | 4 | 3 |
| ambiguous | 12 | 9 |
| Total | 43 | 23 |

Origens: 40 perguntas V2 e rótulos herdados de `router_labels_v1`, dez temporais,
quatro smokes, cinco controles F1, dois contraexemplos de regressão e seis
paráfrases candidatas multidomínio preparadas antes das chamadas. Uma duplicata
foi agrupada: SMOKE-004 preserva CONTROL-AMBIGUOUS como alias. Perguntas antigas
não foram reformuladas; o dataset guarda origem/ID, categoria, ação, escopo e split.
As categorias explícitas incluem sinais inequívocos herdados, como IRA.

Todos os temporais, smokes, controles e contraexemplos ficam em DEV. Em particular,
TEMP-POS-003/004 e TEMP-GRAD-005/001 não são teste independente. Demais itens foram
separados por hash/alternância estratificada, com seed registrada, antes das APIs.
Paráfrases estão marcadas. Duplicatas são agrupadas antes do split.

TEST ficou fora da calibração, mas há exposição anterior dos conjuntos legados e
famílias de paráfrases compartilhadas entre splits. Não há independência estatística
demonstrada nem gold independente. Nenhum rótulo foi alterado em função de resultados.

## Calibração somente DEV

Cada candidato usa os mesmos probes observados; não houve nova API por threshold.
Seleção: maior macro-F1 das quatro classes, menor WRR, menor UCR, maior recall de
esclarecimento e, persistindo empate, menor threshold. [Tabela completa](dev_001/calibration.json).

| Threshold | Accuracy | WRR | Clarification precision | Clarification recall | UCR | Macro-F1 |
|---:|---:|---:|---:|---:|---:|---:|
| 0,55 | 74,42% | 25,58% | 100% | 16,67% | 0% | 0,730031 |
| 0,60 | 74,42% | 23,26% | 66,67% | 16,67% | 3,23% | 0,730477 |
| **0,65** | **76,74%** | **20,93%** | **75%** | **25%** | **3,23%** | **0,763105** |
| 0,70 | 76,74% | 20,93% | 75% | 25% | 3,23% | 0,763105 |
| 0,75 | 76,74% | 20,93% | 75% | 25% | 3,23% | 0,763105 |
| 0,80 | 76,74% | 20,93% | 75% | 25% | 3,23% | 0,763105 |

Threshold congelado: **0,65**, pelo último desempate; hash DEV:
`de9521726e551bf51ca57eead9ddb27892f01ba97920164b3475753a378d4e57`.
TEST não foi usado na escolha. O runner confere hashes e configuração efetiva,
incluindo modelos, endpoint, temperatura e limites, além do artefato commitado.

As [linhas brutas DEV](dev_001/rows.jsonl) registram o candidato operacional inicial
0,55 e todas as decisões candidatas estão nos [pares](dev_001/pairs.jsonl).
O resumo DEV e as tabelas abaixo usam exclusivamente as
[linhas derivadas do candidato selecionado](dev_001/selected_policy_rows.json),
sem editar capturas brutas. As latências das fases compartilhadas permanecem as
observadas; a seleção não repete chamadas externas.

## Resultado DEV — 43 perguntas

| Métrica | V1 | V2-D | V2-L |
|---|---:|---:|---:|
| Route Accuracy | 34/43 = 79,07% | 33/43 = 76,74% | 32/43 = 74,42% |
| Wrong Route Rate | 0/43 = 0% | 9/43 = 20,93% | 9/43 = 20,93% |
| Clarification Precision | 12/21 = 57,14% | 3/4 = 75% | 1/3 = 33,33% |
| Clarification Recall | 12/12 = 100% | 3/12 = 25% | 1/12 = 8,33% |
| Unnecessary Clarification Rate | 9/31 = 29,03% | 1/31 = 3,23% | 0/31 = 0% |
| Macro-F1 | 0,836818 | 0,763105 | 0,715881 |
| Saídas inválidas/falhas | 0 | 0 | 2 |
| Probe Activation Rate | n/a | 21/43 = 48,84% | 21/43 = 48,84% |
| Probe Resolution Rate | n/a | 17/21 = 80,95% | 18/21 = 85,71% |
| Probe-Assisted / Decision Accuracy | n/a | 11/21 = 52,38% | 10/21 = 47,62% |
| Route Stability | ver série DEV separada | ver série DEV separada | ver série DEV separada |
| LLM calls/query | 1 | 1 | 1,4884 |
| Retrieval e embedding calls/query, cada | 0 | 0,4884 | 0,4884 |
| Latência média, s | 2,510 | 3,016 | 4,154 |

## Resultado TEST — 23 perguntas

| Métrica | V1 | V2-D | V2-L |
|---|---:|---:|---:|
| Route Accuracy | 16/23 = 69,57% | 12/23 = 52,17% | 13/23 = 56,52% |
| Wrong Route Rate | 0/23 = 0% | 10/23 = 43,48% | 9/23 = 39,13% |
| Clarification Precision | 9/16 = 56,25% | 0/1 = 0% | 0/1 = 0% |
| Clarification Recall | 9/9 = 100% | 0/9 = 0% | 0/9 = 0% |
| Unnecessary Clarification Rate | 7/14 = 50% | 1/14 = 7,14% | 1/14 = 7,14% |
| Macro-F1 | 0,691364 | 0,558036 | 0,583333 |
| Saídas inválidas/falhas | 0 | 0 | 1 |
| Probe Activation Rate | n/a | 16/23 = 69,57% | 16/23 = 69,57% |
| Probe Resolution Rate | n/a | 15/16 = 93,75% | 15/16 = 93,75% |
| Probe-Assisted / Decision Accuracy | n/a | 5/16 = 31,25% | 6/16 = 37,50% |
| Route Stability | n/a, uma execução | n/a, uma execução | n/a, uma execução |
| LLM calls/query | 1 | 1 | 1,6957 |
| Retrieval e embedding calls/query, cada | 0 | 0,6957 | 0,6957 |
| Latência média, s | 2,588 | 3,255 | 4,496 |

Dados e matrizes completas: [DEV](dev_001/summary.json), [TEST](test_001/summary.json),
[comparação e pares de melhora/piora](comparison.json). Matriz: quatro classes
gold e coluna adicional `error`. Falha não vale como esclarecimento correto.
WRR conta rota não nula errada sobre todos os itens; abstensão indevida aparece em
UCR. Logo, WRR zero do V1 não equivale a resolver todos os itens nem avaliar respostas.

Os dois judges inválidos DEV foram POS2-018 (scope ambas com needs_clarification=true)
e SMOKE-004 (scope null com needs_clarification=false/pergunta null).
No TEST, POS2-011 recebeu ambas para uma pergunta de mestrado, sem pedido dos
dois domínios: a validação rejeitou. Não houve erro de transporte nessas chamadas.

## Estabilidade — subconjunto DEV, 10 execuções completas por pergunta

Novo V1 em cada rodada; probe/judge novos quando ativados, sem cache. Este é um
conjunto conhecido de regressão, separado dos 43 itens DEV da tabela principal e
do TEST. Cada célula informa acertos/10; entre parênteses, frequência modal.

| Caso | V1 | V2-D | V2-L |
|---|---:|---:|---:|
| TEMP-POS-003 | 7/10 (70%) | 10/10 (100%) | 10/10 (100%) |
| TEMP-POS-004 | 6/10 (60%) | 10/10 (100%) | 10/10 (100%) |
| TEMP-GRAD-005 | 7/10 (70%) | 10/10 (100%) | 10/10 (100%) |
| TEMP-GRAD-001 | 5/10 (50%) | 10/10 (100%) | 10/10 (100%) |
| CONTROL-POS | 10/10 (100%) | 10/10 (100%) | 10/10 (100%) |
| SMOKE-004 | 10/10 (100%) | 10/10 (100%) | 0/10 (70%) |
| Expected Route Rate total | 45/60 = 75% | 60/60 = 100% | 50/60 = 83,33% |
| Route Stability média | 75% | 100% | 95% |
| Entropia média, bits | 0,622255 | 0 | 0,146882 |

R1 é determinístico sobre um probe fixo (teste com 20 repetições), mas a cascata
também foi medida: houve 25 ativações em 60 execuções. Os quatro casos F1 passaram
de 25/40 em V1 para 40/40 em ambas as cascatas. Não são teste independente.
Em SMOKE-004, V2-L escolheu pós indevidamente sete vezes e retornou três saídas
inválidas. Sua frequência modal alta pode representar uma decisão errada.
[Todas as decisões e entropias](stability_001/stability.json).

## Eficiência e custo observado

Latências lógicas = soma das fases efetivamente medidas para cada política;
trabalho físico compartilhado é contado uma vez. A execução pareada sequencial
não mede throughput de três implantações independentes. p95 usa interpolação
linear; n=43/23 permite esse resumo, sem precisão populacional estabelecida.
Tokens incluem embedding quando ativado. `usage.cost` é reproduzido na unidade
do campo do provedor; o recibo não traz uma moeda separada, e não houve conversão
ou estimativa com tabela de preços. Cobertura de recibos/tokens/custo: 100%.

| Split | Política | Média / p50 / p95, s | Tokens/query | usage.cost/query |
|---|---|---:|---:|---:|
| DEV | V1 | 2,510 / 2,211 / 5,694 | 687,81 | 0,0000720879 |
| DEV | V2-D | 3,016 / 2,377 / 6,441 | 699,95 | 0,0000723307 |
| DEV | V2-L | 4,154 / 3,421 / 10,196 | 1519,23 | 0,0001538507 |
| TEST | V1 | 2,588 / 2,164 / 5,633 | 683,39 | 0,0000717074 |
| TEST | V2-D | 3,255 / 3,115 / 6,601 | 699,83 | 0,0000720361 |
| TEST | V2-L | 4,496 / 4,315 / 7,767 | 1864,61 | 0,0001915909 |

Trabalho físico, sem triplicar chamadas compartilhadas:

| Série | LLM | Embedding | Retrieval | Tokens | Soma usage.cost |
|---|---:|---:|---:|---:|---:|
| DEV | 64 | 21 | 21 | 65327 | 0,00661558 |
| TEST | 39 | 16 | 16 | 42886 | 0,00440659 |
| Estabilidade DEV | 85 | 25 | 25 | 85747 | 0,00869528 |
| Trabalho físico total | 188 | 62 | 62 | 193960 | 0,01971745 |

São 250 requisições externas, todas com recibos. Esse total é operacional;
não agrega métricas científicas DEV e TEST. As duas tentativas de preflight
acrescentaram zero chamadas. Demos reutilizam traces, sem custo externo adicional.

## Viés de domínio

O corpus contém 378 registros graduação e 129 pós. Entre **probes ativados**:

| Série / gold | Probes | Dominância do próprio domínio | Rotas cruzadas D / L |
|---|---:|---:|---:|
| DEV / graduação | 2 | 2/2 = 100% | 0 / 0 |
| DEV / pós | 7 | 6/7 = 85,71% | 0 / 0 |
| TEST / graduação | 2 | 2/2 = 100% | 0 / 0 |
| TEST / pós | 5 | 4/5 = 80% | 1 / 0 |

São estimativas condicionais ao gate V1, com denominadores pequenos. Entre gold
ambíguos, a graduação dominou 11/12 probes DEV e 9/9 TEST. Ambas as V2 rotearam
indevidamente os nove ambíguos TEST para graduação. Em POS2-011, gold pós, R1
roteou para graduação; R2 caiu em saída inválida, sem recuperar a rota correta.
Há tendência observada de exposição/decisão para graduação. A diferença de volume
é compatível com essa preocupação, mas os dados não isolam sua causalidade.
Rank mass não elimina viés de corpus nem revela o nível pessoal do usuário.
Não se aplicou correção de viés nesta entrega.

## Demos, melhoras e pioras preservadas

[DEMOS.md](DEMOS.md) e [traces completos](demo_traces.json): primeiros exemplos
que satisfazem a seleção pré-registrada, sem escolher pelo sucesso da V2.

1. CONTROL-POS: V1 direto pós; nenhum probe, embedding ou judge adicional.
2. SMOKE-004: V1 esclarece; counts 8 graduação/2 pós, dominância 0,544777.
   R1 esclarece. R2 termina em fallback inválido; não é sucesso semântico.
3. TEMP-GRAD-001, rodada 1: V1 esclarece apesar de graduação explícita; counts
   7/3, dominância 0,795150; R1 e R2 retornam graduação. Caso DEV conhecido.

No DEV, R1 melhorou oito itens e piorou nove em relação ao mesmo V1; R2 melhorou
nove e piorou onze, incluindo falhas. No TEST, R1 melhorou cinco e piorou nove;
R2 melhorou seis e piorou nove. Listas, perguntas e antes/depois em
[comparison.json](comparison.json).

Exemplos TEST de melhora: GRAD2-001 (IRA), GRAD2-011 e POS2-006/007/008 em ambas;
POS2-010, que menciona mestrado, foi recuperado somente por R2. Exemplo de piora:
GRAD2-006 pergunta motivos para segunda chamada sem identificar nível; V1 esclareceu,
ambas as cascatas escolheram graduação. POS2-017 pergunta sobre perder a vaga após
duas reprovações, também sem nível; ambas escolheram graduação. São erros de
roteamento contra rótulos candidatos congelados, não notas jurídicas das respostas.

## Testes, revisão e preservação

TDD: features e políticas começaram com testes RED de módulos ausentes; os
contraexemplos de `ambas`, congelamento de configuração e caminhos Git também
foram observados falhando antes das correções. Os **39 testes novos focados**
cobrem ranks/massas, desconhecidos, vazio, limiar inclusivo, determinismo, gate V1,
judge válido/inválido, ausência de gold, mesmo probe, métricas, calibração DEV-only,
split, reutilização de vetor e separação do contexto final. São versionados por
exceções seletivas; testes comuns usam mocks, sem API externa.

Verificação final: 39 focados aprovados; RAG **237
aprovados, 9 skips**, em 22,04 s; projeto **300 aprovados, 11 skips**, em 25,26 s.
Persistem os quatro avisos conhecidos de Pydantic, Starlette e AsyncMock. Nove
skips são capturas F1 opt-in; os outros dois já existiam. A evidência F3 congelada
foi selecionada explicitamente. Suíte verde não demonstra que F1 foi resolvida.
Ruff em `src/rag_baseline tests/rag_baseline` e formatação dos arquivos alterados
aprovados. `git diff --check` também foi conferido na entrega.

A verificação técnica encontrou e motivou correções antes dos experimentos:
guarda conservadora rejeitando pedidos legítimos de ambos os níveis, e lacuna
na comparação da configuração efetiva entre DEV/TEST. Também conferiu a errata
Windows e a integridade do threshold. Não houve ajuste de política após DEV.
A revisão final recomputou tabelas, pares, estabilidade, custos, demos e hashes,
sem encontrar pendências de código ou evidência. Isso não estabelece validação independente dos rótulos
nem certifica correção jurídica ou generalização.

registros** permanecem iguais por ID, texto, metadados canônicos e embedding
float32. Hash completo:
`ab253a24b756d9f3d3e05aeb49220798b08d947704112327fd894a577bb2b38a`.
Os **234 arquivos protegidos** permanecem iguais por SHA-256, incluindo corpora,
datasets anteriores, registry, resultados e fontes congeladas de V1/temporal/F3.

F2 não recebeu lookup, BM25, híbrido, reranking, reescrita, representação nova ou
reindexação. Seu diagnóstico anterior e condições continuam preservados; não foi
alegada uma nova avaliação ou correção F2. Version Filter e relações 658→956 e
177/§4º→1056 não mudaram. O prompt de geração conserva a mitigação F3, SHA-256
`ccf0374117c24920648661f4699e7291d59596450ead6b3f69bc59fcb10da3f3`.
Não há deduplicação F4, mudança de frontend, chunking, Chroma, GraphRAG ou RAGAS.
Na API, somente a construção opcional da cascata recebeu os parâmetros de modo;
escopo manual e o padrão V1 permanecem. O grafo usa V2 quando seu modo é passado
explicitamente; não se afirma que o grafo interativo padrão adota V2 sozinho.

## Interpretação e limites

H_ROUTER não recebeu suporte como melhoria geral nesta amostra: recuperar domínio
em F1 conhecido não compensou rotear perguntas que exigiam esclarecimento.
H_D recebeu suporte operacional/local: R1 custou menos que R2 e sua cascata foi
estável nos seis casos selecionados. Isso não torna corretas suas rotas TEST.
H_L não recebeu suporte geral: os ganhos pontuais de R2 coexistiram com perda
de ambiguidade legítima e seis saídas inválidas nas três séries.

A evidência favorece manter **V1 como padrão conservador** entre as políticas
atuais; nenhuma V2 é promovida como correção geral F1. No TEST, ambas reduziram
UCR para 7,14%, mas também perderam todos os nove esclarecimentos legítimos.
V2-H não foi implementado. As vantagens complementares pontuais não bastam para
priorizá-lo com esta evidência; não há zona de decisão segura estabelecida.

Limites: rótulos candidatos, amostra pequena, uma execução principal por item,
TEST derivado sem independência confirmatória, seis casos de estabilidade
selecionados por regressão, variação do provedor mesmo com temperatura zero,
gate V1 selecionando os probes, guarda lexical limitada para ambas, latências
medidas por fases e ausência de avaliação de respostas finais. A comparação
R2 não isola a contribuição causal dos metadados da contribuição de uma segunda
classificação por LLM. Não houve ablação para isso. Nenhuma escolha foi refeita
para melhorar métricas agregadas. Resultados negativos, erros e fallback foram
preservados e não foram transformados em sucesso por pós-processamento.

## Reprodução

A partir de `code/`, com ambiente e índice configurados e destinos novos:

```powershell
python -m rag_baseline.experiment_v2 --routing-v2-stage calibrate --output ../evaluation/results/novo_router_dev
python -m rag_baseline.experiment_v2 --routing-v2-stage test --calibration ../evaluation/results/novo_router_dev/frozen_threshold.json --output ../evaluation/results/novo_router_test
python -m rag_baseline.experiment_v2 --routing-v2-stage stability --repetitions 10 --calibration ../evaluation/results/novo_router_dev/frozen_threshold.json --output ../evaluation/results/novo_router_estabilidade
```

Commitar a nova calibração antes de TEST/estabilidade, como exige o runner.
Para reproduzir com o threshold desta entrega, usar o artefato
`dev_001/frozen_threshold_windows_v1.json` e destinos novos. Chamadas reais variam;
os comandos não prometem as mesmas respostas. `--routing-v2-stage prepare` deriva
o dataset para um caminho novo via `--dataset`, sem sobrescrever o existente.

Configuração opcional da API: `ROUTING_MODE=adaptive_distribution_v2`,
`ROUTER_PROBE_TOP_K=10`, `ROUTER_DISTRIBUTION_THRESHOLD=0.65`; para R2,
`ROUTING_MODE=adaptive_llm_v2`. O `.env` não foi editado para promover essas opções.
V1 permanece `intent_v1` por padrão. Não houve push, merge ou rebase. Nenhum
arquivo operacional de IA, cache ou segredo foi incluído; a chave configurada
foi procurada nos arquivos da entrega sem imprimir seu valor. A entrega termina
com commit local de evidências e árvore limpa, conferida após o commit.
