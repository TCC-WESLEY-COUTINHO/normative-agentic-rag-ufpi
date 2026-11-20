# Diagnóstico das falhas agentic — versão 1

> **Registro histórico.** Configuração, resultados, contagens de testes e estados descritos referem-se à execução documentada, anterior à v3.4. Para a versão atual, consulte o [guia de evidências e reprodução](../../README.md).

28/10/2026. Depuração dos casos conhecidos, sem avaliação confirmatória, ajuste de
dataset ou avaliação jurídica especializada. A única intervenção de produção aceita foi
a mitigação de citação em F3. F1 e F2 permanecem abertas; F4 foi localizada na
geração e continua sem correção específica. Resultados negativos foram preservados.

## Estado inicial e entrega

Estado inicial observado: branch `feat/temporal-revocation-amendment-v1`, HEAD
`34b02b46e72a514c5618732cea966f769a440bef`, árvore limpa. Foram conferidos HEAD,
status, branch, dez commits, diff, diff cached e diff stat antes das alterações.
Não houve checkpoint vazio. A branch local foi criada exatamente desse HEAD:
`fix/agentic-failure-analysis-v1`. Registro em [initial_state.json](initial_state.json).

Commit de produção: `71bff32853e125ba2aed6b25e9117760a84b2eb5`,
`fix: constrain generated citations to supported article metadata`. O segundo
commit reúne somente os testes restantes, o roteiro de reprodução e esta evidência.
Seu hash é informado na entrega; não houve push, merge, rebase ou alteração de main.

## Método e condições

Foram localizados os JSONL originais de pós/graduação B/D e os manifestos.
[original_cases.json](baseline_001/original_cases.json) preserva perguntas,
decisões, contextos e respostas dos seis casos relevantes. As capturas originais
não guardavam o corpo bruto do Router nem o tráfego histórico de todas as camadas.
Essas ausências não foram preenchidas como se fossem observações históricas.

As novas reproduções guardam as requisições efetivas, conteúdo bruto retornado,
decisão parseada, normalização, recibos, configuração e hashes. Não guardam
cabeçalhos de autenticação nem campos de raciocínio do provedor. São registros
experimentais das chamadas, não instruções ou logs operacionais de agentes.

Configuração: modelos principal e Router `qwen/qwen3-30b-a3b-instruct-2507`,
embedding `openai/text-embedding-3-small`, temperatura 0, máximo de 800 tokens,
`top_k=5`, coleção `ufpi_duas_regulacoes_setor`, 507 registros. Os únicos top-k
maiores foram consultas diagnósticas F2. Perguntas de ablação não foram usadas
como perguntas de produção nem incorporadas aos datasets.

Os três manifestos finais de F1 (`../failure_regression_v1_001/f1_retained/manifest.json`, não incluído neste snapshot),
F4 (`../failure_regression_v1_001/f4_retained/manifest.json`, não incluído neste snapshot) e
pipeline (`../failure_regression_v1_001/pipeline_001/manifest.json`, não incluído neste snapshot) identificam
`71bff32`, fontes por SHA-256 e `production_inputs_dirty=false`. O roteiro e
resultados ainda não estavam commitados nessas chamadas; isso aparece no status
Git, sem alegação de árvore inteira limpa durante a coleta.

## F1 — esclarecimento indevido

Casos: `TEMP-POS-003`, `TEMP-POS-004`, `TEMP-GRAD-005` e a pergunta de
`TEMP-GRAD-001`, cuja rota já variara nas demos. As perguntas exatas estão nas
capturas e não foram reformuladas. Foram feitas dez chamadas por caso no estado
inicial e dez na versão entregue; cinco controles receberam uma chamada por série.

Na primeira série, todas as 45 respostas passaram na validação. Nos erros, o
modelo já retornava `scope=null`, `needs_clarification=true` e
`reason_code=ambiguous_academic_level`. Na pós, a pergunta bruta distinguia lato
de stricto sensu; na graduação, pedia confirmação do nível já escrito. O parser
não converteu uma rota correta em esclarecimento. A aplicação substituiu apenas
a frase por sua pergunta fixa. Não havia histórico anterior na requisição.

| Caso | Rota esperada/10 inicial | Estabilidade modal inicial | Rota esperada/10 final | Estabilidade modal final |
|---|---:|---:|---:|---:|
| TEMP-POS-003 | 8/10 | 0,80 | 6/10 | 0,60 |
| TEMP-POS-004 | 5/10 | 0,50 | 4/10 | 0,60 |
| TEMP-GRAD-005 | 5/10 | 0,50 | 4/10 | 0,60 |
| TEMP-GRAD-001 | 7/10 | 0,70 | 7/10 | 0,70 |

`route_stability_rate` é a frequência da decisão modal; `expected_route_rate`
é a frequência da rota esperada. Uma decisão modal pode estar errada.
Fontes: [antes](f1_before/summary.json) e
versão entregue (`../failure_regression_v1_001/f1_retained/summary.json`, não incluído neste snapshot).
Há variação mesmo com temperatura zero.

Uma alteração localizada de instrução continuou falhando em 5/40 chamadas dos
casos problemáticos (tentativa (`../failure_regression_v1_001/f1_after/rows.jsonl`, não incluído neste snapshot)).
Restringir o schema com o detector lexical existente chegou a 40/40 nesses
casos, mas quebrou esclarecimentos legítimos como “Não sei se meu curso é
graduação ou pós-graduação” e a menção incidental ao curso anterior. O
contraexemplo foi reproduzido: dois testes falharam com a restrição e passaram
após sua retirada. A revisão também identificou essa regressão. A variante que
restringia a rota exata quebrava ainda a comparação abreviada “graduação e pós”.

**Nenhuma dessas intervenções foi entregue.** `router.py`, seu prompt, schema
e o detector permanecem idênticos ao HEAD inicial. O teste contra esclarecimento
indevido ficou RED nas capturas finais: 5 falhas e 7 aprovações, contando os três
testes de preservação da ambiguidade. Falham os quatro casos e o controle 956.

No controle “Segundo a Resolução 956/2025, posso cancelar uma disciplina?”, a
última série também revelou saída semanticamente inválida: o modelo pediu
esclarecimento com `clarification_question=null`. A validação rejeitou e o fallback
registrou `invalid_model_decision`. Essa falha adicional não explica os quatro
casos originais de decisão válida. A pergunta sem nível continua esclarecendo.

A causa localizada é a classificação indevida feita pelo modelo; não foi
estabelecida uma correção mínima que mantenha a extração semântica conservadora.
Sem commit de bugfix F1. Dados completos em [f1_analysis.json](f1_analysis.json).

## F2 — retrieval histórico da graduação

Pergunta exata:

> Como era a redação do art. 68, §4º da Resolução 177/2012 no regulamento da graduação atualizado em 2023, antes da alteração de 2026?

Alvo: `ufpi-177-2012-art-68-idx-000067`. A pergunta chega intacta ao embedding,
já contém graduação, 177/2012 e art. 68. O alvo tem setor correto e permanece
elegível. Sua representação contém norma, setor, título, capítulo, seção,
subseção e artigo; são 3.267 caracteres de conteúdo, 3.582 no texto reconstruído
para embedding. O recibo do embedding antigo não existia; não se alega recuperá-lo.

| Rank | Índice conjunto: norma/artigo | Distância | Graduação: artigo da 177/2012 | Distância |
|---|---|---:|---|---:|
| 1 | 956/2025 art. 62 | 0,349782 | 388 | 0,373272 |
| 2 | 658/2024 art. 66 | 0,350247 | 307 | 0,376499 |
| 3 | 177/2012 art. 388 | 0,373272 | 226 | 0,379074 |
| 4 | 177/2012 art. 307 | 0,376499 | 385 | 0,382756 |
| 5 | 177/2012 art. 226 | 0,379074 | 305 | 0,383721 |
| 6 | 177/2012 art. 385 | 0,382756 | 302 | 0,389158 |
| 7 | 177/2012 art. 305 | 0,383721 | 306 | 0,389451 |
| 8 | 658/2024 art. 67 | 0,385050 | 303 | 0,389993 |
| 9 | 177/2012 art. 302 | 0,389158 | 386 | 0,392084 |
| 10 | 177/2012 art. 306 | 0,389451 | 301 | 0,396395 |
| 11 | 177/2012 art. 303 | 0,389993 | 308 | 0,397818 |
| 12 | 177/2012 art. 386 | 0,392084 | 1.056/2026 art. 1 | 0,398478 |
| 13 | 956/2025 art. 63 | 0,392376 | 304 | 0,401225 |
| 14 | 177/2012 art. 301 | 0,396395 | 387 | 0,407966 |
| 15 | 177/2012 art. 308 | 0,397818 | 300 | 0,408674 |
| 16 | 1.056/2026 art. 1 | 0,398478 | 224 | 0,409376 |
| 17 | 177/2012 art. 304 | 0,401225 | 225 | 0,412649 |
| 18 | 658/2024 art. 65 | 0,401778 | 231 | 0,413785 |
| 19 | 658/2024 art. 62 | 0,406695 | 234 | 0,414868 |
| 20 | 658/2024 art. 63 | 0,406833 | 222 | 0,415050 |

O alvo está em **363º no conjunto e 300º na graduação**, distância 0,490787.
Não é near-miss de ranking. Top 5, 10, 20 e o ranking completo diagnóstico, com
IDs exatos, estão em [rankings.json](f2_retrieval/rankings.json).

| Query diagnóstica | Rank conjunto do art. 68 | Rank graduação |
|---|---:|---:|
| Original | 363 | 300 |
| Original + graduação | 397 | 329 |
| Original + Resolução 177/2012 | 372 | 309 |
| Original + artigo 68 | 343 | 281 |
| Redação sobre o coordenador de estágio | 5 | 2 |
| Sem expressão temporal | 350 | 292 |

Classificação: **embedding miss**, com competição de ranking e pouca informação
semântica sobre o conteúdo do dispositivo na pergunta. A busca densa não opera
como lookup exato de número de artigo. Os dados não isolam uma dimensão do
embedding nem provam causalidade do tamanho do chunk. Retirar a expressão
temporal não resolve. Não foi encontrado erro de filtro, perda de referência ou
reescrita. Três embeddings independentes da pergunta original reproduziram os
mesmos top 5 B/D antigos; a reexecução final também não trouxe o alvo.

Sem alteração de produção ou commit F2: mudar representação e reindexar está
fora das variáveis permitidas; adicionar lookup, reescrita ou reranking seria
outra estratégia experimental. [Análise](f2_analysis.json),
[representação](f2_retrieval/target.json), [repetições](f2_retrieval/repeats.json).

## F3 — caput atribuído ao §1º

Caso `TEMP-POS-001`, chunk `ufpi-956-2025-art-53-idx-000051`. Os metadados
identificam `Art. 53`, sem parágrafo. O texto inicial contém o prazo de dez dias;
o §1º trata dos formatos presencial, híbrido ou remoto. O formatter conserva a
separação e não acrescenta metadado de §1º. O OCR usa `$` para os marcadores e
o §1º menciona o caput; essa contribuição possível não foi isolada por ablação.

Com a pergunta e os cinco chunks finais originais, **10/10 respostas brutas**
do provedor citaram incorretamente “Art. 53, § 1º”. As respostas armazenadas pelo
serviço eram iguais às brutas. Trata-se de grounding/localização na geração,
não de falta de retrieval. Requisição completa e contexto em
[f3_before/rows.jsonl](f3_before/rows.jsonl).

RED: o teste com o corpus real passou na localização do prazo, mas falhou na
atribuição ao parágrafo nas dez respostas: 1 aprovado, 1 falhou. Uma instrução
genérica para só citar subdivisões com suporte continuou errando 10/10 e ficou
preservada em f3_after (`../failure_regression_v1_001/f3_after/rows.jsonl`, não incluído neste snapshot).

A intervenção aceita acrescenta somente duas linhas: as citações de localização
devem usar fonte e artigo, granularidade dos metadados, sem acrescentar parágrafo,
inciso ou alínea. Não contém “dez dias”, “53” ou regra jurídica manual. Não há
reescrita ou pós-processamento da resposta.

GREEN: **10/10 respostas citaram somente art. 53**, mantendo dez dias; teste
de captura 2/2 aprovado e 19 testes focados aprovados. O teste exige manifesto
concluído e prompt capturado igual ao atual. A reexecução do pipeline após o
commit também citou apenas art. 53. O prompt histórico do piloto mantém SHA-256
`dbe2b931d08dfa564bab82e8528b3dbaf5e15c1a737b09087fc61a40496fde4d`;
o prompt de execução revisto tem
`ccf0374117c24920648661f4699e7291d59596450ead6b3f69bc59fcb10da3f3`.

Commit local `71bff32`. A revisão aceitou a mudança como **mitigação medida**.
Ela sacrifica localização mais fina e não garante adesão universal do modelo:
as novas respostas da graduação ainda citam §4º, que tem suporte textual, apesar
da instrução conservadora. Não se conclui melhora geral da qualidade jurídica.
[Análise](f3_analysis.json), capturas finais (`../failure_regression_v1_001/f3_article_only/rows.jsonl`, não incluído neste snapshot).

## F4 — repetição textual

Caso `TEMP-GRAD-001`. O prompt original foi usado explicitamente para reproduzir
o estado histórico, com os cinco chunks finais originais. **8/10 respostas brutas**
repetiram a cláusula rastreada: execuções 1, 2, 3, 5, 7, 8, 9 e 10. Houve nove
respostas distintas. A repetição já existia em `message.content`, antes do serviço.

As dez respostas foram comparadas no serviço e reapresentadas pela API real
local e pelo terminal existente, sem nova chamada ao LLM nesses replays.
As respostas bruta/serviço/API/JSONL do terminal eram iguais, e as contagens da
cláusula no texto renderizado eram iguais às do serviço. Isso é replay local
das respostas recém-observadas; não recuperação do tráfego histórico ausente.
O caminho do cliente é não streaming, sem concatenação de eventos parciais.

Os IDs dos chunks são únicos, a alteração foi aplicada uma vez, e a redação
aplicável aparece uma vez no chunk-base. Há sobreposição substantiva legítima
entre o ato 1.056 e a norma-base alterada; não se isolou sua contribuição causal
à geração. Não houve prova de duplicação de bloco, aplicação duplicada de
amendment, concatenação pelo serviço ou duplicação pelo terminal.

Dois testes determinísticos passam: preservação da aplicação única e preservação
da resposta bruta através de cliente, serviço, API e terminal. Eles usam a
resposta repetida real e não comparam uma futura resposta livre com string fixa.

Após apenas a mitigação F3, houve **0/10 repetições da cláusula rastreada** na nova
série, com nove respostas distintas. Esse resultado não prova ausência de toda
repetição semântica nem um efeito causal confirmado sobre F4. **Não há fix ou
commit específico F4, nem deduplicador de respostas.**
[Antes](f4_original/rows.jsonl), depois (`../failure_regression_v1_001/f4_retained/rows.jsonl`, não incluído neste snapshot),
[análise e limites](f4_analysis.json).

## Reexecução controlada final

Somente seis perguntas conhecidas, uma chamada completa por caso em D, e o
par B da pergunta histórica. Não foi rodado o dataset inteiro para escolher uma
versão. comparison.json (`../failure_regression_v1_001/comparison.json`, não incluído neste snapshot) contém
pergunta, contexto, decisão e resposta antes/depois para cada linha.

| Caso/condição | Antes congelado | Depois observado | Estado |
|---|---|---|---|
| TEMP-POS-003 D | esclarecer | esclarecer | F1 aberta |
| TEMP-POS-004 D | esclarecer | pós; comparação respondida | uma execução favorável, F1 ainda variável |
| TEMP-GRAD-005 D | esclarecer | esclarecer | F1 aberta |
| TEMP-GRAD-001 D | repetição | cláusula sem repetição | F4 sem fix específico |
| TEMP-GRAD-002 B/D | art. 68 ausente | art. 68 ausente | F2 mantida |
| TEMP-POS-001 D | dez dias, §1º incorreto | dez dias, art. 53 | F3 mitigada no caso |

A resposta histórica D continua fazendo afirmações auxiliares indevidas sobre
ausência de alteração a partir de contexto insuficiente. Essa limitação não foi
corrigida nem ocultada. Não há notas de avaliação ou novo resultado final do TCC.

## Testes, lint e integridade

Estado inicial disponível: 191 testes RAG aprovados; a primeira verificação completa
registrou 254 aprovados. A contagem 254 do relatório anterior refere-se ao conjunto
mais amplo disponível, não deve ser confundida com o comando limitado ao RAG.

Verificação final com a captura GREEN F3 selecionada:

- Focados: 7 aprovados, 9 verificações de captura F1 não selecionadas, 1,03 s.
- RAG: 198 aprovados, 9 não selecionados, 2 avisos, 27,60 s.
- Projeto completo: 261 aprovados, 11 ignorados/não selecionados, 4 avisos, 28,48 s.
- Checagem explícita das capturas finais F1: **5 falhas, 7 aprovações**, 0,40 s.
  Casos: POS-003, POS-004, GRAD-005, GRAD-001 e controle 956.

Os avisos existentes são deprecações Pydantic/Starlette e AsyncMock. As nove
verificações de captura F1 são opt-in, não chamadas escondidas ao provedor; os
dois outros skips já existiam. Não se apresenta a suíte determinística verde
como resolução de F1. Novos testes são versionados por exceções seletivas de
`.gitignore`; caches e testes locais não relacionados continuam excluídos.
As duas novas pastas de resultados têm regras seletivas `-text` em
`.gitattributes`, preservando os bytes coletados e seus hashes durante o commit.

Os **507 registros**, com texto, metadados e embeddings float32, permanecem
iguais ao snapshot inicial. Os **176 arquivos protegidos** permanecem idênticos
por SHA-256, incluindo corpora, datasets, registry e todos os resultados anteriores
protegidos. Hash do índice antes/depois:
`ab253a24b756d9f3d3e05aeb49220798b08d947704112327fd894a577bb2b38a`.
Uma captura local inicial abortou por citação de nomes Unicode pelo Git, sem
chamadas externas; `baseline_001` é a captura válida.

## Reprodução

Na raiz do repositório, com o ambiente configurado e destino novo:

```powershell
python evaluation/failure_analysis.py router --repetitions 10 --output evaluation/results/nova_serie_router
python evaluation/failure_analysis.py retrieval --output evaluation/results/novo_diagnostico_retrieval
python evaluation/failure_analysis.py generation --case-id TEMP-POS-001 --repetitions 10 --output evaluation/results/nova_serie_citacao
python evaluation/failure_analysis.py generation --case-id TEMP-GRAD-001 --original-generator --repetitions 10 --output evaluation/results/nova_serie_repeticao_original
python evaluation/failure_analysis.py pipeline --output evaluation/results/nova_reexecucao_casos
```

O [roteiro](../../failure_analysis.py) recusa reutilização do diretório de saída,
registra fontes/configuração e confere preservação do índice. `--original-generator`
seleciona somente o prompt congelado para reprodução, sem modificar produção.
As execuções acima usam API real; os testes comuns não fazem essas chamadas.

Para a checagem da evidência F3, a partir de `code/`:

```powershell
$env:CITATION_REGRESSION_RUN=(Resolve-Path ../evaluation/results/failure_regression_v1_001/f3_article_only).Path
python -m pytest tests/rag_baseline -q
python -m pytest -q
```

## Conclusões científicas

- F3 tem uma mitigação medida, com teste RED/GREEN e uma única mudança geral de instrução.
- F1 é uma falha variável de classificação; a restrição lexical de schema foi rejeitada por quebrar ambiguidade legítima.
- O controle 956 também revelou saída inválida rejeitada pelo fallback; isso não foi confundido com os quatro erros originais de decisão válida.
- F2 é um miss distante na busca semântica, sem erro identificado de metadados, filtro ou perda da pergunta.
- F4 aparece na geração; não houve defeito demonstrado de montagem, aplicação duplicada ou renderização.
- Zero repetições da cláusula na série final não demonstra uma correção geral de F4.
- Os resultados são exploratórios, sem tuning por métricas agregadas, participantes, validação ou nova avaliação confirmatória.
- Corpus, índice, embeddings existentes, datasets/qrels, relações temporais, modelos, temperatura, top-k principal e resultados antigos foram preservados; somente o prompt de citação mudou em produção.

Nenhum arquivo operacional de IA, segredo ou cache foi versionado. Não houve
alteração da API, frontend, Chroma, chunking, GraphRAG ou RAGAS. Os commits
permanecem locais. A revisão final não encontrou bloqueadores na mitigação F3
nem nas evidências e testes de fronteira F4; isso não certifica validade jurídica.
