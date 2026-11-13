# Evolução normativa real — relatório de entrega

28/10/2026. Dois casos documentais implementados, com dataset candidato e execução
exploratória. Nenhuma inferência confirmatória ou validação jurídica humana.

O índice conjunto passou de **438 para 507 registros**, adicionando somente os
67 chunks da 658/2024 e os 2 da 1.056/2026. Os 438 registros anteriores, incluindo
seus embeddings, e os 81 arquivos protegidos permanecem iguais por SHA-256.
O filtro distingue revogação integral e alteração de dispositivo; a 177 não foi
marcada como revogada. Os experimentos também revelaram esclarecimentos indevidos
e falhas de recuperação, mantidos nesta entrega.

## Estado inicial e proteção dos repositórios

Antes de qualquer alteração em cada repo foram executados `git status --short`,
`git branch --show-current`, `git rev-parse HEAD`, `git log -5 --oneline --decorate`,
`git diff` e `git diff --cached`.

| Repo | Branch inicial | HEAD inicial | Status/diffs |
|---|---|---|---|
| RAG | `feat/agentic-router-versioning-v1` | `3d371586475326274e2b212ed0c8b91f45ad6dbf` | vazios |
| ingest_documents | `feat/ingest-resolucao-956-v1` | `9a997210f60b0ffa6b1d33b934c315b240a58724` | vazios |

Últimos cinco commits iniciais do RAG: `3d37158`, `5213881`, `eebdb2d`,
`a39c354`, `754e20f`. Da ingestão: `9a99721`, `6d893ad`, `6ed09c2`,
`cfeb8cf`, `f83f1f9`. Não havia trabalho não commitado; **nenhum checkpoint
foi necessário**. As novas branches são `feat/temporal-revocation-amendment-v1`
e `feat/ingest-temporal-norms-v1`. Nenhuma alteração local foi descartada.

O Git da ingestão exigiu exceção de propriedade restrita a cada comando
(`git -c safe.directory=...`); nenhuma configuração global foi alterada.
O `.venv` padrão do RAG apontava para Python ausente. Foi reutilizado o ambiente
já existente `code/.local/venv-agentic` com Python 3.12.13, preservando `.venv`
e `uv.lock`. O sandbox normal falhou na inicialização; os comandos necessários
foram executados com aprovação automática, sem rejeição pendente.

## Fontes oficiais, hashes e relações comprovadas

Todas as fontes são institucionais UFPI. Os PDFs foram baixados e conferidos;
o catálogo não foi a única evidência. Dados completos em
[temporal_sources_v1.json](../../provenance/temporal_sources_v1.json) e nas
proveniências individuais.

| Ato/documento | Data do ato | Fonte oficial | SHA-256 do PDF |
|---|---|---|---|
| 177/2012, regulamento consolidado em 2023 | 05/11/2012 | [PDF UFPI](https://ufpi.br/arquivos_download/arquivos/Parfor/REGULAMENTO_GERAL_DA_GRADUAÇÃO_-_177.2012_atualizada_2023_para_site_1_.pdf) | `b5cf8085c758b4e5f07e37db404900926737235e2d315ccd88761353d1484fe0` |
| 658/2024, regulamentação da pós stricto sensu | 22/04/2024 | [PDF SIGAA/UFPI](https://www.sigaa.ufpi.br/sigaa/verProducao?idProducao=6869447&key=18c6011be067380f348deb69741d19c1) | `2dc41b821dbe62cc40e5e57f2c48fbf1b4e7d5f7b34a89f1ad78619187fb3050` |
| 956/2025, regulamentação da pós stricto sensu, no pacote CEPEX 953–956 | 18/12/2025 | [PDF UFPI](https://ufpi.br/images/Portarias/Portarias%202025/CEPEX%20953%20A%20956.pdf) | `ae2af3e6909baf1c1ff7cef3690e3e2adf12d7bd53cadf7bb5db925fb9255ace` |
| 1.056/2026, alteração do art. 68, §4º | 17/08/2026 | [PDF UFPI](https://ufpi.br/images/Resoluo%20CEPEXUFPI%20N%201.056_%20de%2017%20de%20Agosto%20de%202026%201.pdf) | `0f9690d60110f71f622814ea914d5de644de5946acaf5cd6ba04395f24922c5b` |

O PDF oficial da 177 é byte a byte idêntico ao já existente no RAG. O pacote
oficial da 956 contém outros atos e tem hash diferente do PDF local isolado da
956: `d4b0861f5c3211fcf59c702577cfadc4633b16301dfa23748bfce410ef37ab9a`.
Essa diferença de contêiner foi registrada; não houve substituição do PDF ou corpus antigo.

**Pós — revogação integral.** A página 22 do pacote oficial, página impressa 17
da 956, contém: “Art. 62. Ficam revogadas: [...] VI - a Resolução CEPEX/UFPI
Nº 658, de 22 de abril de 2024”. A relação é
`ufpi-658-2024 → revogada por → ufpi-956-2025`, com base em art. 62, VI.

**Graduação — alteração parcial.** A página única da 1.056, art. 1º, determina
nova redação para o art. 68, §4º do Anexo da 177. A página 23 da consolidação
da 177 comprova a redação anterior. A mudança introduz ressalva para cursos
de políticas públicas/programas institucionais com corpo docente selecionado
por edital, permitindo designação nas condições indicadas independentemente
do vínculo com a UFPI. A regra geral permanece; as alíneas a–g não são reimpressas
no ato e foram preservadas. O ano **2026 foi lido no PDF**, sem inferência.

Os arts. 63 da 956 e 2º da 1.056 condicionam eficácia à publicação. Não foi
atribuída data de publicação a partir da assinatura. “Atual” nesta avaliação
significa precedência expressa entre os atos do snapshot fechado, sem resolver
transição de turmas, retroatividade ou direitos adquiridos.

## Pipeline da ingestão e corpora entregues

Origem exclusiva: `ingest_documents`. Cadeia reutilizada da 956:

`PDF oficial → docling_smoke.build_converter() → Docling/Tesseract português
→ export_to_markdown() → legal_article_chunker.build_compatible_chunks()
→ metadados/IDs → validate_corpus()`.

A CLI existente `resolution_956` recebeu parâmetros para outras normas;
não foi criado parser especial para a 1.056. Foram corrigidos no parser
compartilhado: referência interna introduzida por “segundo o Art. 2º”, artigo
citado entre aspas em ato alterador e hierarquia dividida pelo Docling.
Regressão compara a releitura do Markdown antigo da 956 com seu JSON original,
com igualdade exata. Nenhum corpus antigo foi reconstruído.

| Validação | 658/2024 | 1.056/2026 |
|---|---:|---:|
| Páginas do PDF | 19 | 1 |
| Artigos/chunks | 67 | 2 |
| IDs únicos | 67 | 2 |
| Vazios / duplicados / multiartigo / lacunas | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| norm_id/setor incorretos | 0 / 0 | 0 / 0 |
| Sem capítulo | 0 | 2, ato sem capítulos |
| Preservação textual estrutural | 0,985 | 0,991 |
| Status dos novos chunks | revogada | desconhecida |

O primeiro OCR da 658 foi rejeitado pela validação; os artefatos finais só
foram produzidos após corrigir a causa estrutural. Não houve edição manual
da redação OCR para fabricar uma diferença normativa.

Somente quatro arquivos finais foram copiados da ingestão para o RAG:

- [658_2024_temporal_v1.json](../../corpora/658_2024_temporal_v1.json), SHA-256
  `ca0274876732d97ec577a540b849f870f9be15d5e0d4628985408d6c4ccf4c02`.
- [1056_2026_temporal_v1.json](../../corpora/1056_2026_temporal_v1.json), SHA-256
  `6c3cf25e3b49769f622b31d301621b3fdc5c88c3400a9931f7e2324efb080958`.
- [Proveniência 658](../../provenance/658_2024_temporal_v1.json).
- [Proveniência 1.056](../../provenance/1056_2026_temporal_v1.json).

Cada novo chunk contém norma, setor, status, fonte/documento e artigo. Prefixos:
`ufpi-658-2024` e `ufpi-1056-2026`; IDs seguem o padrão existente por artigo e
índice. Os blobs commitados dos novos corpora mantêm exatamente os bytes
referenciados na proveniência. PDFs novos e pipeline permanecem na ingestão;
não foram copiados `.venv`, caches, intermediários, logs ou arquivos de agentes.

## Indexação incremental e preservação

Foi usada a coleção existente `ufpi_duas_regulacoes_setor`, com o mesmo embedding,
sem reset, synchronize, exclusão ou atualização dos registros anteriores.
O novo utilitário de indexação exige fontes explícitas, verifica colisões antes
de chamadas, calcula apenas embeddings ausentes e usa `collection.add`.

| Norma | Antes | Depois | Alteração de registros antigos |
|---|---:|---:|---|
| 177/2012 | 376 | 376 | nenhuma |
| 956/2025 | 62 | 62 | nenhuma |
| 658/2024 | 0 | 67 | adição |
| 1.056/2026 | 0 | 2 | adição |
| Total | 438 | 507 | 69 novos IDs |

Provas: [snapshot anterior](preservation_before.json),
[resumo da indexação e snapshots por ID](../temporal_incremental_index_v1/summary.json),
[recibos de embedding](../temporal_incremental_index_v1/receipts.json) e
[verificação após experimentos](preservation_after.json).
Cada registro anterior foi comparado por ID, SHA-256 do texto, metadados
canônicos e embedding float32 little endian. Os **438 permaneceram iguais**.
Os **81 arquivos protegidos**, incluindo corpora e resultados congelados,
também permaneceram iguais. Os dados antigos da ingestão têm diff vazio.

Reprodução da etapa incremental, a partir de `code/`, com destino novo:

```powershell
python -m rag_baseline.incremental_index --source ../evaluation/corpora/658_2024_temporal_v1.json ufpi-658-2024 "Resolução CEPEX/UFPI nº 658/2024" --source ../evaluation/corpora/1056_2026_temporal_v1.json ufpi-1056-2026 "Resolução CEPEX/UFPI nº 1.056/2026" --output ../evaluation/results/temporal_incremental_nova_execucao
```

## Registry e comportamento do Version Filter

[Registry](../../../data/normative_registry.json), schema 1.1: revogação mantém
`superseded_by` e base textual no art. 62, VI; alteração usa `amendments` com
artigo, parágrafo, ato alterador, fonte da redação aplicável, redação anterior,
redação aplicável e base do art. 1º. Os textos são conferidos contra os corpora.

A 177 permanece norma-base, com status global desconhecido; não é revogada
nem excluída por fonte. Se o art. 68 é recuperado numa consulta atual, somente
o corpo introdutório comprovado do §4º é substituído em memória. ID, distância,
alíneas e outros dispositivos permanecem. A auditoria registra original,
resultado, ato e precedência em `amended_references`. Uma divergência de texto
exclui somente o chunk-alvo como `amendment_unresolved`, sem declarar revogação
do documento. O registro não constitui grafo jurídico geral.

Consultas históricas preservam o texto original e recebem aviso de status.
“Segundo a 658/2024” e a forma completa com CEPEX/UFPI são reconhecidas para a
norma expressamente revogada. Marcadores atuais têm precedência. Com filtro
desligado, B/C preservam o comportamento de recuperação sem intervenção temporal.
O Router continua independente; seu código e prompt não foram alterados.

## Dataset candidato e condições congeladas

Dez itens, cinco por domínio, com evidência literal e páginas dos PDFs:
[conjunto completo](../../datasets/temporal_candidates_v2.json),
[pós](../../datasets/temporal_pos_v1.json) e
[graduação](../../datasets/temporal_graduacao_v1.json).
Há perguntas atuais, históricas, de vigência, comparação/ato alterador e
recuperação concorrente. Todos os rótulos e qrels foram preparados antes das
chamadas. Não foram ajustados após resultados e não são gold validado.

O código experimental foi congelado em `82b83ae1d713548c94c3898de7af608c97e2d2db`.
Condições preservadas: A oracle/manual; B ambas sem filtro; C Router sem filtro;
D Router com filtro. Modelo principal/Router `qwen/qwen3-30b-a3b-instruct-2507`,
embedding `openai/text-embedding-3-small`, temperatura 0, `top_k=5`, prompt V2
inalterado. Os oito manifestos finais registram `inputs_dirty=false`; hashes
dos insumos e JSONL foram conferidos. Cada execução tem diretório novo.

## Resultados temporais B × D por domínio e relação

20 saídas brutas: [pós B](../temporal_pos_B_001/rows.jsonl),
[pós D](../temporal_pos_D_001/rows.jsonl),
[graduação B](../temporal_grad_B_001/rows.jsonl) e
[graduação D](../temporal_grad_D_001/rows.jsonl).
São cinco itens por condição e domínio, sem erros de API. Comparação e
denominadores em [comparison.json](comparison.json). Resumos completos também
agrupam por `domain` e `temporal_relation`.

| Domínio/relação | Condição | Recall@5 | Wrong-norm@5 | Obsolete Context Rate | Compliance Violation Rate | Current-Norm Hit@5 | OPER |
|---|---|---:|---:|---:|---:|---:|---:|
| Pós / revocation | B | 1,00 | 0,40 | 6/25 = 24% | 3/5 = 60% | 3/3 = 100% | n/a |
| Pós / revocation | D | 0,60 | 0,20 | 0/15 = 0% | 0/3 = 0% | 2/3 = 66,7% | n/a |
| Graduação / amendment | B | 0,80 | 0,40 | 6/25 = 24% | 4/5 = 80% | 4/4 = 100% | 3/4 = 75% |
| Graduação / amendment | D | 0,60 | 0,00 | 0/20 = 0% | 0/4 = 0% | 3/4 = 75% | 0/3 = 0% |

Recall inclui os cinco itens respondíveis, atribuindo zero a esclarecimentos
indevidos. Wrong-norm é média nas perguntas com contextos, mede origem documental
e não erro jurídico. B pode recuperar 658 até em consultas da graduação;
isso explica parte de sua exposição e origem indevida. Current-Norm Hit
considera qrels atuais inclusive nas consultas sem geração, que recebem zero;
suporte de redação aplicado pelo registry é explicitamente contado e não vira
um hit de retrieval artificial para o ato não recuperado.

**OPER**: consultas atuais previamente anotadas para dispositivo alterado em
que a redação anterior foi entregue como aplicável / consultas desse tipo
com geração. Históricas ficam fora. Definições completas de todas as métricas
e denominadores estão no [protocolo temporal](../../protocol_temporal_v1.md).
CVR inclui norma obsoleta ou dispositivo desatualizado entregue como atual;
é métrica de exposição do contexto, sem nota jurídica da resposta.

D pediu esclarecimento indevido em `TEMP-POS-003`, `TEMP-POS-004` e
`TEMP-GRAD-005`, apesar do domínio explícito. Gerou 3/5 respostas na pós e 4/5
na graduação. Isso reduz os denominadores; **taxa zero não demonstra melhor
qualidade**. Nas três consultas atuais da graduação geradas em ambas as
condições, a exposição anterior foi 2/3 em B e 0/3 em D. B × D combina
roteamento e filtro, não isola causalmente o Version Filter.

## Principais exemplos reais e demos

**Pós, TEMP-POS-001.** B recuperou 956 art. 52, 658 art. 43, 956 art. 53,
956 art. 54 e 658 art. 40. Há competição real: o art. 43 da 658 prevê pelo
menos sete dias, e o art. 53 da 956 prevê dez dias para divulgação da defesa.
D excluiu previamente a 658 e usou cinco chunks da 956, incluindo art. 53.
O [replay dos mesmos candidatos B](pos_same_candidates_replay.json) registra
pré-filtro, duas remoções fundamentadas e três referências finais. Ele não
se confunde com a recuperação D, que já trouxe cinco após a pré-exclusão.
**B e D responderam dez dias no exemplo**; o resultado demonstra redução de
exposição, sem demonstrar melhora de correção da resposta.

**Graduação, TEMP-GRAD-001.** B entregou o ato 1.056 art. 1 junto com o chunk
original `ufpi-177-2012-art-68-idx-000067`, mais artigos 65/87 da 177 e um
da 658. D preservou a 177 e atualizou somente o corpo introdutório do §4º em
memória, mantendo alíneas e outros artigos. O
[replay da graduação](grad_same_candidates_replay.json) registra chunk
original, ato alterador, regra de precedência e contexto final. A auditoria
D também contém essa aplicação. A resposta gerada, entretanto, repetiu uma
frase; não recebeu avaliação automática.

As duas demos do terminal existente, comandos e saídas reais estão em
[DEMOS.md](DEMOS.md). Pós mostra rota, exclusão da 658, base no art. 62, VI,
e contexto final 956. Graduação mostra norma-base 177, art. 68, §4º, ato
1.056, precedência e texto aplicável. Uma tentativa adicional não interativa
da graduação pediu esclarecimento indevido e foi preservada; a execução
interativa seguinte respondeu em uma consulta. Não houve ajuste de pergunta,
Router ou configuração para os resultados B/D.

## Testes, smoke e verificações finais

Suíte inicial do RAG: 215 aprovados, 2 ignorados, 4 avisos. Suíte final:
**254 aprovados, 2 ignorados, os mesmos 4 avisos**, em 25,30 s. Os avisos
envolvem deprecações Pydantic/Starlette e AsyncMock já presentes no baseline.
Ingestão: **5 testes aprovados**, em 8,164 s. Detalhes em
[verification.json](verification.json).

Os 19 casos locais de versionamento e 20 da indexação incremental cobrem:
revogação 658/956, filtro atual/histórico, elegibilidade da 956, 177 não
revogada, alvo art. 68/§4º, redação nova e ato 1.056, preservação histórica,
consulta com título oficial completo, falha restrita ao dispositivo,
metadados, métricas, colisões/no-op, vetores inválidos e preservação de registros.
Um teste aplica o filtro ao **corpus real inteiro da graduação**: mantém os
376 artigos, altera somente o texto-alvo de 68, preserva a–g e mantém todos
os conteúdos originais em modo histórico. Testes existentes de orquestração
e condições verificam independência do Router e baseline com filtro desligado.
Os novos testes do RAG permanecem locais por política já existente no
`.gitignore`; não foi forçada sua inclusão. Os cinco testes da ingestão
estão versionados em seu repositório.

Smokes novos A/B/C/D, quatro itens cada, sem erros de API:

| Condição | Rotas corretas | Recall@5 (3 respondíveis) | Wrong-norm@5 | Gerações |
|---|---:|---:|---:|---:|
| A | manual | 0,1667 | 0,40 | 3 |
| B | manual | 0,1667 | 0,5333 | 4 |
| C | 4/4 | 0,1667 | 0,40 | 3 |
| D | 4/4 | 0,50 | 0,00 | 3 |

Precisão/recall de esclarecimento em C/D: 1/1 no item ambíguo. A não inventou
setor oracle para ele. Não substituir os experimentos antigos por estes:
o índice agora contém fontes adicionais. Dados em
[smoke_comparison.json](smoke_comparison.json) e nos diretórios
`temporal_smoke_A_001` a `temporal_smoke_D_001`.

Ruff aprovado no RAG em `src/rag_baseline tests/rag_baseline`, com checagem
de formatação das fontes alteradas; na ingestão, `ruff check .` aprovado.
`git diff --check` contra os HEADs iniciais passou nos dois repos. A primeira
checagem detectou padding de alinhamento do Rich nas transcrições; o commit
de resultados foi criado antes de corrigir esse check. A regra final de
whitespace foi limitada às transcrições para preservar exatamente seus bytes;
nenhum JSONL ou resultado bruto foi editado. A checagem foi repetida com sucesso.

Revisão independente do código precedeu o congelamento experimental.
Foram corrigidos o reconhecimento do título oficial completo nas consultas
históricas, com testes observados falhando e passando, e o registro dos
hashes de proveniência nos manifestos. Nenhuma pendência crítica ou menor
restou na revisão. Conferência visual dos PDFs, suíte e índice foram
verificadas separadamente; a revisão não certificou validade fora do snapshot.

## Commits, estado de entrega e limitações

Commits locais do RAG:

- `82b83ae` — código, corpus, registry, protocolo, proveniência e dataset congelados.
- `aab2ff5` — resultados B/D, smokes, demos, métricas e provas de integridade.
- O commit de relatório que contém este arquivo registra a entrega e o ajuste
  restrito de whitespace das transcrições. O hash final é informado na resposta
  de entrega e pode ser obtido com `git rev-parse HEAD`.

Commits locais da ingestão: `c828e27`, `58b032f`, `09926d7`, `a3e4894`,
`f7bf5d1`; HEAD `f7bf5d1671ae83c23eed16c72512b5789f8557e2`.
Estado da ingestão: limpo. Após o commit dos insumos, nenhum insumo experimental
ficou sujo; os resultados foram commitados separadamente. A entrega termina
com conferência de `git status --short` vazio em ambos os repos após o commit
do relatório, sem push ou merge.

Limitações que permanecem:

- Amostra candidata pequena, uma execução por condição, sem revisores,
  notas jurídicas ou participantes. Os campos de avaliação continuam nulos.
- O Router errou três rotas por esclarecimento indevido no temporal e também
  variou entre duas execuções adicionais da mesma pergunta da graduação.
- A pergunta histórica da graduação não recuperou o art. 68 em B nem D.
  O mecanismo permite o texto anterior, mas esse retrieval real falhou.
  A resposta D chegou a negar alteração de 2026 a partir da ausência de contexto;
  isso não é prova de inexistência da alteração documentada.
- Na resposta D principal da pós, a indicação de §1º não localiza o prazo de
  dez dias, que consta no caput do art. 53. Métricas de contexto não medem esse erro.
- A melhoria de exposição não é melhoria automática da resposta: o exemplo
  principal da pós já foi respondido corretamente em B, e a resposta principal
  da graduação em D contém repetição. Não houve ajuste do prompt principal.
- OCR conserva símbolos `$`/`8` por `§`, ruído em linhas pontilhadas/cabeçalho
  citado e assinatura da 1.056. A redação substantiva foi conferida no PDF;
  o nome do capítulo V da 658 conserva a ordem reconstruída pelo Docling.
- Não se demonstra aumento de créditos de 24 para 30: na 658 há 24 em
  disciplinas e seis da dissertação. Esse contraste não foi usado como caso.
- Datas de publicação e aplicação a turmas anteriores não foram inferidas.
  Vigência global desconhecida não equivale à inexistência da relação expressa.
- A origem dos embeddings antigos não tinha recibo; sua preservação foi
  comprovada por hash, sem alegar certificação retrospectiva de modelo.
- A indexação incremental requer escrita exclusiva; detecta alterações
  concorrentes, mas não oferece transação/rollback entre API e Chroma.

Confirmações de escopo: **nenhuma arquitetura paralela de ingestão no RAG;
nenhum corpus, ID, embedding antigo ou resultado congelado alterado; nenhum
arquivo operacional de IA, cache ou segredo novo versionado; nenhum push;
nenhum merge**. A chave configurada foi procurada nos arquivos adicionados
ou modificados sem imprimir seu valor e não foi encontrada. Router, modelo,
embedding, top_k, prompt principal, API, implementação Chroma, GraphRAG,
RAGAS e frontend não foram alterados. A tarefa se encerra neste relatório.
