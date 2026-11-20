# Protocolo pré-experimental de roteamento V2

> **Protocolo histórico.** As condições e comandos abaixo registram o experimento anterior à v3.4. Não descrevem a configuração atual; novas execuções exigem diretório de saída novo e os insumos da condição histórica. Veja [reprodução e limites](../docs/REPRODUCAO.md).

28/10/2026. Registro anterior às chamadas deste experimento. Estudo exploratório,
sem validação dos rótulos, inferência confirmatória ou avaliação jurídica.
O objeto é F1; F2, Version Filter, geração F3 e repetição F4 permanecem congelados.

## Hipóteses e políticas

H_ROUTER: evidência de recuperação exploratória pode melhorar decisões cujo domínio
não é resolvido confiavelmente apenas pela intenção textual.
H_D: uma regra determinística sobre a distribuição pode ter maior estabilidade e
menor custo operacional que um julgamento adicional por LLM.
H_L: um judge com evidência estruturada pode distinguir melhor ambiguidades
semânticas que uma regra fixa. Nenhuma política é declarada vencedora a priori.

R0=`intent_v1`, sem mudança de prompt/schema/parser/fallback. R1 e R2 reutilizam
a MESMA decisão V1 em cada par. V1 direto válido (inclusive ambas) encerra as três
políticas. Caso contrário, um único embedding e um único probe global top-10
produzem o MESMO ProbeResult, identificado por SHA-256, para R1 e R2. A comparação
pareada isola o decisor condicional ao V1/probe compartilhados; não é execução
independente de três sistemas, nem garante estabilidade de chamadas futuras.

R1=`adaptive_distribution_v2`: massa por domínio = soma de 1/rank; share = massa /
soma das massas dos setores conhecidos. Um só domínio conhecido resolve para ele.
Com dois, resolve se o maior share >= threshold; empate ou share insuficiente
esclarece. Probe vazio/só desconhecidos esclarece. Nunca infere ambas do probe.
R2=`adaptive_llm_v2`: mesmo ROUTER_MODEL, temperatura atual zero, somente query
original e metadados estruturados do probe. Schema próprio de quatro campos e cinco
reason_codes. Saída inválida/erro esclarece e conta como falha, mesmo se gold for
esclarecer. Ambas exige pedido textual explícito de comparação ou regras conjuntas;
a validação posterior é conservadora e tem cobertura lexical limitada.

Os 507 registros são somente lidos: 378 graduação e 129 pós. Configuração Chroma
observada: cosine; menor distância é melhor. Não se calcula 1-distance nem se
interpreta distância/share como probabilidade calibrada. Ranks são obrigatórios;
distâncias, gaps e estatísticas são diagnósticos. Hits desconhecidos são retidos
para auditoria e excluídos apenas dos agregados por domínio.

Probe não recebe Version Filter, não reescreve query e não fornece textos ao
generator. Na integração normal, apenas o vetor da query pode seguir ao retrieval
temporal final top-5. Os experimentos pareados abaixo medem somente roteamento,
sem retrieval final nem geração. Testes de integração verificam essa fronteira.

## Dataset e separação

Derivação reproduzível em `routing_dataset.py`: perguntas originais V2 e rótulos
de `router_labels_v1`; dez temporais; quatro smoke; cinco controles de F1; dois
contraexemplos de regressão; seis paráfrases candidatas multidomínio preparadas
antes das chamadas. Não há respostas, trechos gold ou qrels no derivado.
Cada item preserva pergunta, origem, ID, rótulo e categoria. Duplicatas por NFKD,
casefold e tokens alfanuméricos são agrupadas antes do split, com aliases e
prioridade DEV. Divergência de rótulo aborta a derivação.

Todos os temporais, smokes, controles e contraexemplos conhecidos ficam em DEV.
Assim TEMP-POS-003/004 e TEMP-GRAD-005/001 jamais são teste independente.
Demais itens: ordenar por SHA-256(seed + ID), alternar DEV/TEST, começando DEV,
estratificando por categoria e flag de paráfrase. Seed:
`router-v2-split-2026-10-28`. Não se ajusta split após resultados.
TEST não participa da calibração, mas perguntas dos conjuntos antigos já foram
exploradas, e as paráfrases compartilham família entre splits. Essa dependência,
rótulos candidatos e amostra pequena impedem alegação confirmatória.

## Calibração e congelamento

Somente DEV, uma chamada V1 por item; se ativado, um probe e um judge.
Thresholds R1: 0.55, 0.60, 0.65, 0.70, 0.75, 0.80. Todas as seis decisões usam
o mesmo probe observado, sem repetir API para selecionar threshold.
Seleção: maior macro-F1 nas quatro classes fixas; menor Wrong Route Rate;
menor Unnecessary Clarification Rate; maior Clarification Recall; persistindo
empate, menor threshold (ordem crescente dos candidatos). Sem denominador,
métrica é null; no desempate esse valor é tratado como zero. Registrar tabela,
hash DEV, dataset, código, configuração e threshold em artefato congelado.
Commitar calibração antes de chamar TEST. Nenhum ajuste de prompt, split,
threshold, probe top-k, modelo ou regra após observar DEV/TEST.

TEST: uma execução pareada por item com threshold congelado. O runner recusa
hashes diferentes dos insumos de calibração. Cada fase usa diretório novo,
manifesto iniciado/concluído, recibos e saídas por pergunta. Não sobrescrever
resultados, omitir erros nem selecionar somente chamadas favoráveis.

## Métricas e denominadores

Classes fixas: graduação, pós, ambas, esclarecer. Matriz com quatro linhas gold
e cinco colunas preditas (as quatro classes e error). Falhas inválidas/API contam
como erro, nunca como esclarecimento correto. Macro-F1 é média das quatro F1;
classe sem suporte recebe zero. Accuracy = decisões corretas / todos os itens.
WRR = rota não nula incorreta / todos os itens; não inclui abstensão indevida,
que aparece em UCR = esclarecimentos sobre itens respondíveis / respondíveis.
Clarification Precision = esclarecimentos válidos corretos / todos os outputs
de esclarecimento (inclui fallback); Recall = válidos corretos / gold esclarecer.
Falhas em outputs com rota também são incorretas.

Probe Activation = ativações / todos; Resolution = decisões não nulas válidas /
ativações; Assisted Accuracy = decisões corretas, inclusive esclarecer / ativações.
Distribution Decision Accuracy e Judge Accuracy usam esse mesmo denominador
condicional nas respectivas políticas. R0 não tem probe (N/A na apresentação).
Publicar contagens, matriz e estratos, sem misturar DEV/TEST em uma claim.

Estabilidade: selecionar previamente os quatro F1, CONTROL-POS e SMOKE-004
(alias de CONTROL-AMBIGUOUS). Dez pares completos por pergunta, com novo V1 e,
quando ativado, novo embedding/probe/judge; sem cache. Intercalar por rodada na
ordem de IDs. Expected Route Rate = corretas / repetições; Stability = frequência
modal / repetições (pode estar errada); entropy em bits com math.log2. Publicar
também estabilidade da cascata R1, além do determinismo sobre probe fixo.
Não usar repetição para recalibrar nem promover a melhor tentativa.

Eficiência: chamadas físicas compartilhadas contadas uma vez; chamadas lógicas
por política incluem V1 e suas fases necessárias. Latência por política é soma
das fases medidas que ela usaria isoladamente; execução pareada sequencial não
é benchmark de throughput. Média e p50; p95 apenas com n>=20, interpolação linear.
Tokens/custo apenas de usage real do provedor; publicar cobertura, subtotais
reportados e null para total incompleto. Sem estimativa por tabela de preços.
Não triplicar custo físico somando custos lógicos compartilhados.

Viés: condicionar a probes ativados com gold graduação/pós e reportar n,
P(dominante=grad|gold grad), P(dominante=pós|gold pós), rotas erradas cruzadas,
e direções da dominância. O gate V1 seleciona a amostra; não generalizar esses
percentuais a todo o corpus nem corrigir distribuição sem outra investigação.

## Demos e integridade

Três traces reais, sem reescrever pergunta: primeiro CONTROL-POS com V1 direto;
primeiro SMOKE-004 que ativa probe; primeiro F1 que ativa probe. Selecionar por
ordem de coleta, independentemente de acerto V2; manter todas as chamadas.
Mostrar ranks, contagens, massas, threshold e decisões. Se o resultado esperado
não ocorrer, publicar a ausência. Melhoras e pioras vêm de pares individuais,
sem alegar correção jurídica. V2-H não será implementado nesta etapa.

Antes/depois: SHA-256 dos arquivos protegidos e snapshot completo de IDs,
documentos, metadados canônicos e embeddings float32 dos 507 registros.
Nenhuma reindexação. Verificar V1, registry, temporal, prompt F3 e resultados
anteriores. Testes comuns usam mocks; API real só nas etapas explícitas do runner.
