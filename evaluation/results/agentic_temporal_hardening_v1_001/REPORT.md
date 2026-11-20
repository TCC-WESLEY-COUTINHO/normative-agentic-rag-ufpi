# Endurecimento temporal do pipeline normativo — v1

> **Registro histórico.** Configuração, resultados, contagens de testes e estados descritos referem-se à execução documentada, anterior à v3.4. Para a versão atual, consulte o [guia de evidências e reprodução](../../README.md).

Data de referência da auditoria: 29/10/2026. Dataset técnico de regressão, sem
revisão jurídica especializada. As conclusões são restritas às relações documentais
explicitamente modeladas no registry e aos casos avaliados.

## 1. Objetivo e resultado

Auditar Router, retrieval, intenção temporal, Version Filter, contexto entregue ao
gerador e referências. Foram corrigidos bugs reproduzidos, sem alteração de
modelos, temperatura, top-k, embeddings, chunking, corpus ou relações normativas.

No conjunto controlado, OCER foi **0/12**, preservação histórica **6/6** e referências
elegíveis **21/21**. Isso demonstra as invariantes técnicas nesses casos; não
estabelece correção jurídica geral ou qualidade das respostas do modelo.

O smoke real preserva resultados negativos: quatro esclarecimentos indevidos do
Router V1, perda do art. 69 pelo retrieval e falhas de geração mesmo com contexto
temporalmente correto. A branch não promove Router V2 nem corrige F1/F2/F4.

## 2. Estado inicial e isolamento local

- Branch inicial: `feat/adaptive-router-v2-experiment`.
- HEAD inicial: `303bf3e6ecd6472c7137726993fc166c38ce31e0`.
- Árvore inicial limpa; nenhum checkpoint vazio foi criado.
- Branch de trabalho criada exatamente desse HEAD: `fix/agentic-temporal-hardening-v1`.
- Executados antes de alterações: `git status --short`, `git branch --show-current`,
  `git rev-parse HEAD`, `git log -10 --oneline --decorate`, `git diff`,
  `git diff --cached` e `git diff --stat`.
  merge, rebase, reset ou clean foi executado.

O launcher original do `.venv` aponta para um Python 3.11 ausente. Foi utilizado
Python 3.11.15 compatível em `<repo>`, com os pacotes cp311
já existentes. Dependências e arquivos de configuração do projeto não mudaram.
Nenhum cache, runtime ou arquivo temporário faz parte dos commits.

## 3. Arquitetura real observada

| Etapa | Implementação real |
|---|---|
| Entrada HTTP/manual | `code/src/rag_baseline/api.py`, `QueryRequest` e `create_app` |
| Entrada de biblioteca | `agentic.py`, `AgenticRagService.query` |
| Estado LangGraph | `agentic.py`, `AgenticState` |
| Router | `router.py`, `NormativeRouter.route`; V2 em `adaptive_router.py` |
| Escopo | `route_query`/`decide`; manual resolve o escopo sem chamada ao Router |
| Esclarecimento | `clarify`/`reroute`, uma rodada; término sem retrieval se não resolvido |
| Retrieval | `RagService.retrieve` → `ChromaVectorStore.query`, dense/top-k 5 |
| Candidatos brutos | retorno de `retrieve`, armazenado em `state.chunks` |
| Intenção temporal | `classify_temporal_intent`; recalculada após esclarecimento |
| Fonte estrutural | `data/normative_registry.json`, validado por `NormativeRegistry.load` |
| Pré-filtro | exclusão de fontes derivada do mesmo registry |
| Safety filter | `VersionFilter.apply`, incluindo revogação e alteração parcial |
| Histórico | exclusões de sucessores conhecidos e preservação da redação original |
| Contexto final | retorno de `filter_context` e `audit.final_references` |
| Montagem do prompt | `service.py`, `_context` e `RagService.generate` |
| Geração | `OpenRouterClient.chat`, após o filtro; sem chamada se insuficiente |
| Referências | `service.py`, `_reference`, a partir dos chunks finais |

A classificação ocorre antes do retrieval para permitir o pré-filtro. A aplicação
das relações, a substituição e a decisão de insuficiência ocorrem novamente após
os candidatos e antes da geração. A auditoria guarda candidatos e decisões; esses
campos não são concatenados ao prompt do gerador.

Antes desta branch, a API manual contornava o filtro. Agora os escopos manuais da
implementação real usam o mesmo grafo, conservando ausência de `route` no contrato
manual e sem chamar o classificador de domínio. A injeção de serviços substitutos
legados na fábrica de testes permanece compatível. A primitiva `RagService.query`
continua disponível sem filtro para a biblioteca/experimentos legados; ela não é
mais o caminho manual padrão da API real. `version_filter=false` continua sendo
uma desativação explícita para comparações experimentais, fora das garantias desta
auditoria.

## 4. Router congelado

`BaselineSettings.ROUTING_MODE` e os construtores continuam com `intent_v1`.
`adaptive_distribution_v2` e `adaptive_llm_v2` exigem configuração explícita.
Não houve mudança no prompt V1, nas regras V2, no probe ou na configuração padrão.
Os testes exercitam V1 sem probe e os modos experimentais explicitamente ativados.
Não foi repetida a avaliação científica completa V2 com API real.

## 5. Máquina de estados temporal

| Estado | Política operacional |
|---|---|
| `current` | excluir atos explicitamente obsoletos; aplicar somente alteração registrada |
| `historical` | preservar redação antiga; excluir sucessor incompatível conhecido |
| `comparison` | manter ambos os estados pedidos; exigir presença das normas identificadas |
| `validity` | usar base documental do registry para a relação expressa perguntada |
| `indeterminate` | política conservadora de snapshot atual, sem certificar vigência |

`is_historical_question` permanece como interface de compatibilidade; histórico e
comparação requerem evidência histórica. Há tratamento de pedido anterior à
alteração, redação antiga e pedido atual negado. Não há novo LLM de temporalidade.

Uma pergunta por ano não é resolvida a partir do ano do número da resolução.
Ela produz `chronology_unresolved` e abstenção: este snapshot não permite
certificar aplicabilidade numa data de calendário. A classificação lexical é
limitada, e a cobertura bilateral da comparação se refere às normas explicitamente
identificadas; não há interpretação jurídica geral de períodos livres.

## 6. Invariantes e revogação integral

T1 mantém evidência elegível; T2 bloqueia norma explicitamente revogada; T3 preserva
texto histórico; T4 isola a alteração parcial; T5 não aplica redação posterior ao
histórico; T6 fecha o caminho de alteração não resolvida; T7 distingue unknown de
vigente; T8 abstém com insuficiência; T9 deriva referências do contexto final; T10
mantém a mitigação de granularidade F3.

Na relação **658/2024 → 956/2025, art. 62, VI**, o pré-filtro atual deriva a exclusão
do registry, e o safety filter remove a 658 se ela chegar por caminho alternativo.
O teste de prompt capturado mantém 956 art. 53 e impede a presença do texto da
658 art. 43. A relação documental não foi alterada.

Pergunta de vigência pode receber o trecho documental do art. 62 já registrado,
com referência determinística à 956. Isso não é um resolvedor geral de artigos e
não corrige F2. Não se infere data de publicação ou entrada em vigor.

## 7. Alteração parcial e idempotência

Na relação **177/2012, art. 68, §4º → 1056/2026, art. 1**, somente `previous_text`
é substituído por `effective_text` comprovado na base documental. Demais parágrafos
e alíneas permanecem, assim como ID e norma-base. A 177 inteira não é revogada.
O art. 69 não recebe a alteração.

Foi reproduzido e corrigido um bug: reaplicar o filtro sobre um trecho já
transformado antes removia a evidência como unresolved. A aplicação agora é
idempotente, sem duplicação da redação e sem deduplicador textual.

Perguntas sobre qual norma alterou o dispositivo podem usar sua base documental
no registry. A inserção respeita o domínio resolvido e só corresponde ao artigo e
parágrafo registrados; não resolve referência arbitrária por metadados.

## 8. Histórico, unknown e unresolved

O histórico da 658 preserva o texto recuperado e exclui a 956 quando ela é seu
sucessor incompatível na pergunta. O histórico do dispositivo alterado da 177
preserva a redação-base e exclui a 1056 posterior, inclusive quando o usuário
identifica artigo/parágrafo sem repetir o número da norma.

`desconhecida` permanece elegível quando nenhuma relação conhecida a exclui, mas
é comunicado ao gerador com instrução de que o snapshot não certifica vigência.
Isso é distinto de `vigente`. Os registros da 177, 956 e 1056 continuam unknown.

Se o trecho esperado para substituição não puder ser encontrado de modo seguro,
o registro é `amendment_unresolved`. O grafo abstém antes de gerar, mesmo quando
outros artigos sobreviveram. Texto inexistente não é sintetizado.

## 9. Contexto insuficiente, prompt e proveniência

Contexto vazio, alteração não resolvida, calendário não documentado e comparação
sem um dos lados identificados não são enviados ao gerador para inferência.
A resposta conservadora nesses caminhos tem zero tentativas de geração.

`VersionAudit.provenance` registra `chunk_id`, `source_norm`, `source_article`,
`temporal_action` e `relation_source`. Ações incluem `kept_current`,
`excluded_revoked`, `historical_preserved`, `excluded_later_wording`,
`amendment_applied`, `amendment_unresolved` e `relation_evidence`. As exclusões
do pré-filtro também são auditadas, inclusive as históricas.

O prompt capturado nos testes recebe exclusivamente os chunks pós-filtro.
Prompts completos de execução não foram salvos como artefatos. Os traces guardam
candidatos, classificação, decisões, contexto final, referências e resposta.

## 10. Referências e F3

`_reference` usa fonte/artigo e metadados estruturais dos chunks finais, sem
referências geradas livremente pela LLM. Chunk removido não integra `references`.
Norma revogada pode ser referenciada quando legitimamente usada no histórico.
A alteração parcial conserva a referência da norma-base transformada; o ato
alterador aparece como referência quando seu texto também está no contexto.

O prompt F3 e a estrutura `Reference` permanecem inalterados. Isso preserva a
mitigação, mas não garante obediência do modelo: P1 real acrescentou localizações
mais finas, e P1 automático produziu uma localização malformada. Essas saídas
constam em `generation_review.json`, sem reescrita das respostas.

## 11. Pares atual × histórico

No par pós, a mesma temática usa 956 art. 53 no atual e 658 art. 43 no histórico.
No par graduação, o mesmo ID da 177 art. 68 tem redação alterada no atual e redação
original no histórico. A diferença de conteúdo é verificada, não somente IDs.
Os dois pares controlados apresentam contexto distinto (**2/2**).

No smoke automático, a graduação foi interrompida pelo Router nos dois membros;
portanto não se considera o par vazio como preservação histórica bem-sucedida.
Na condição manual, ambos os pares têm contextos distintos, com a limitação
de geração histórica da graduação descrita abaixo.

## 12. Integração Router + temporal e índice local

O dataset contém graduação/pós atual e histórica, ambas, ambígua e os três
escopos manuais. `both/ambas` mantém evidência elegível dos dois domínios;
Version Filter não funciona como Router. A restrição do domínio para evidência
documental inserida apenas obedece à rota já escolhida.

Quatro probes somente leitura no Chroma real passaram (**4/4**), preservando os
507 registros. Usaram vetores de documentos já existentes, repetidos entre
condições temporais. São testes de integração de pré-filtro/safety filter e
overlay, não uma medida de retrieval semântico da pergunta. Detalhes e contextos
estão em `local_index_probe.json`.

## 13. Dataset e condições experimentais

`evaluation/datasets/temporal_invariants_v1.json` contém **22 casos** derivados dos
casos reais, rotulados como regressão técnica. Inclui os campos id, domínio,
pergunta, intenção temporal, normas permitidas/bloqueadas, ação de alteração,
ação esperada da resposta, caso de origem e notas. Datasets anteriores não mudaram.

As condições são:

1. Controlada: corpus real, candidatos fixos, Router/cliente simulados, 22 casos.
2. Smoke automático: 9 perguntas fixas com API real e V1.
3. Smoke manual: mesmas 9 perguntas, domínio conhecido explícito quando disponível;
   a ambígua continua automática. Essa condição isola o filtro sem corrigir o V1.

Modelos preservados: `openai/text-embedding-3-small` e
`qwen/qwen3-30b-a3b-instruct-2507`; temperatura 0 e top-k 5. Receipts de provedor
registram modelo/uso, sem chave, headers ou corpos arbitrários de erro.

## 14. Métricas com denominadores

| Métrica | Controlado | Real automático | Real manual |
|---|---:|---:|---:|
| Classificação temporal | 22/22 | 9/9 | 9/9 |
| OCER | 0/12 | 0/10 | 0/20 |
| Current-Norm Hit Rate | 11/11 | 3/5 | 5/5 |
| Compliance Violation Rate | 0/11 | 0/4 | 0/4 |
| Preservação histórica | 6/6 | 1/2 | 2/2 |
| Aplicação/preservação de alteração | 6/6 | 0/0 (não observada) | 2/2 |
| Isolamento da alteração | 2/2 | 0/0 (não observado) | 1/1 |
| Contexto final elegível | 21/21 | 20/20 | 35/35 |
| Referências elegíveis | 21/21 | 20/20 | 35/35 |
| Abstenção de insuficiência esperada | 4/4 | 0/1 | 1/1 |
| Ação técnica esperada do pipeline | 22/22 | 5/9 | 9/9 |

OCER = chunks de normas explicitamente obsoletas no contexto final / todos os
chunks finais das consultas atuais às quais relações conhecidas se aplicam.
Redação parcial desatualizada também é contada separadamente na verificação de
compliance. Unknown não é automaticamente uma violação. Denominador zero produz
`null`, e não uma nota perfeita.

Current-Norm Hit é presença da norma requerida, não do artigo exato. O caso G2
mostra essa distinção: há chunks da 177, mas falta o art. 69. Referências elegíveis
exigem pertencimento ao contexto final e elegibilidade temporal, sem medir
cobertura semântica das afirmações. Duas regressões asseguram que uma referência
revogada atual ou posterior incompatível não conte como elegível mesmo se um
caminho com filtro explicitamente desligado a conservar no contexto.

Histórico mede preservação de evidência no fluxo completo; o denominador real
automático inclui o caso parado pelo Router. Métricas de aplicação/isolamento da
alteração só se aplicam quando o candidato alvo chegou ao filtro. Ação técnica
mede chamada de geração/esclarecimento/abstenção antes da chamada, não qualidade
semântica. G2 chamou o modelo, que se absteve no texto. Não há escore automático
de qualidade jurídica ou de resposta final.

## 15. Falhas encontradas e correções mínimas

| Camada | Falha reproduzida | Correção |
|---|---|---|
| TEMPORAL_INTENT | atual apagava o lado antigo da comparação | estados explícitos e precedência de comparação |
| TEMPORAL_INTENT | redação antiga/pedido atual negado mal interpretados | composição lexical limitada e negação estreita |
| VERSION_FILTER | ato posterior permanecia em histórico de alteração | exclusões derivadas da relação registrada |
| AMENDMENT_APPLICATION | reaplicação descartava trecho já alterado | idempotência da substituição comprovada |
| CONTEXT_ASSEMBLY | modo manual contornava o filtro | mesmo pipeline com escopo manual, sem Router |
| CONTEXT_ASSEMBLY | vigência/alteração sem evidência documental no prompt | inclusão restrita da base da relação no registry |
| CONTEXT_ASSEMBLY | evidência documental inserida de outro domínio | respeito ao escopo resolvido |
| CONTEXT_ASSEMBLY | algum contexto bastava para alteração unresolved/comparação incompleta | abstenção antes da geração |
| CONTEXT_ASSEMBLY | unknown ausente do aviso atual | status e limites explícitos no contexto do gerador |
| Avaliador | Router interrompido atribuído também ao retrieval; artigo ausente não detectado | atribuição por etapa e checagem do artigo pedido |
| Avaliador | referência contava só pertencimento, sem elegibilidade temporal | interseção com contexto final temporalmente elegível |

Cada correção foi precedida de RED e seguida de GREEN. As reproduções da revisão
independente foram verificadas novamente. Nada foi alterado apenas por preferência
arquitetural. Não houve nova estratégia de routing ou recuperação.

## 16. Resultados negativos reais, preservados

- **ROUTER, automático: 4/9 casos.** P3, G1, G3 e E2 pediram esclarecimento apesar
  de nível explícito. É a limitação F1 preservada; o filtro nem chegou a executar
  nesses casos. As métricas reanalisadas não atribuem a interrupção ao retrieval.
- **RETRIEVAL, G2 nas duas condições: 1/9 por condição.** O art. 69 não apareceu
  no top-k, embora outros artigos da 177 tenham aparecido. O modelo se absteve.
  Não foi implementado lookup, reescrita, híbrido ou mudança de embedding.
- **GENERATION, G3 manual.** Contexto contém 177 art. 68 original e exclui a 1056,
  mas a resposta nega evidência da redação anterior e chama a redação de vigente.
  Essa falha não é atribuída ao filtro e não foi mascarada.
- **GENERATION, P1 automático/manual.** O texto acrescenta parágrafos/incisos nas
  citações apesar da restrição F3. P1 automático inclui localização malformada.
  O manual ainda mistura condições do exame de qualificação com o tema da defesa;
  não se certifica a correção dessas afirmações.
- O histórico da pós automático usa passado; o manual preserva o texto mas usa
  enquadramento histórico menos explícito. Nenhuma dessas saídas foi reescrita.

Foram inspecionadas **11 respostas geradas**; **3 casos** têm achados técnicos de
geração explícitos. Esse registro é inspeção técnica, não avaliação jurídica
especializada nem estimativa de acurácia geral. Não houve falha de provedor observada.

## 17. Limitações e F1–F4

O controle se limita ao registry de quatro normas e às duas relações documentadas.
Não prova ausência de outros atos, vigência global, retroatividade ou efeitos por
turma. Classificação lexical e suficiência de duas normas não garantem relevância
semântica de todos os chunks. Datas históricas de calendário não são resolvidas.

F1 permanece; F2 permanece backlog; F3 mantém a mitigação estrutural/prompt, mas
há descumprimento residual do modelo no smoke; F4 não recebeu deduplicador.
Resultados anteriores de F1/F2/F3/F4 e V2 permanecem intactos. Não há GraphRAG,
BM25, reranker, novo frontend, deploy ou experimento com estudantes nesta branch.

## 18. Testes e verificação final

Resultados em `verification_after_review.json`:

- Temporais: **68 passed**.
- `rag_baseline`: **276 passed, 10 skipped**.
- Suíte completa: **339 passed, 12 skipped**.
- Novo arquivo de invariantes: **40 passed**, incluídos nas contagens acima.
- Ruff nos seis arquivos Python da entrega: **All checks passed**.
- `git diff --check`: exit code **0**.
- Os testes normais usam clientes simulados e não acionam API externa.

Warnings: duas depreciações LangChain/Pydantic em rag_baseline; a suíte completa
também avisa sobre AsyncMock e timeout no TestClient. Não foram ocultados nem
tratados como bugs temporais. As contagens de etapas anteriores são preservadas
`verification_after_review.json` é a referência definitiva.

## 19. Preservação


- **507 registros** com mesmos IDs, textos, metadados canônicos e vetores float32.
- SHA-256 do snapshot: `ab253a24b756d9f3d3e05aeb49220798b08d947704112327fd894a577bb2b38a`.
- **238 arquivos protegidos**, nenhuma alteração: corpora, registry, datasets e
  resultados anteriores, incluindo F1–F4 e Router V2.
- Nove módulos congelados sem diff: Router V1, V2/probe, config, prompt F3,
  retrieval, vector store, service e corpus.
- Nenhum valor da chave configurada encontrado nos arquivos da entrega.

## 20. Artefatos e reprodução

Os diretórios são preservados em vez de sobrescritos:

- Raiz e `controlled_001`: execuções controladas anteriores à consolidação do avaliador.
- `controlled_analysis_002`: métricas controladas finais, reanálise offline.
- `smoke_001`: traces automáticos originais, incluindo atribuições antigas do avaliador.
- `smoke_analysis_002`: atribuição/métricas finais corrigidas offline, mesmas respostas/contextos.
- `smoke_manual_001`: condição real manual, com traces originais.
- `smoke_manual_analysis_001`: métricas finais da condição manual.
- As reanálises anteriores também permanecem preservadas; a correção da métrica
  de referência não mudou os valores observados, pois os contextos finais
  efetivamente entregues nestas execuções eram temporalmente elegíveis.
- `generation_review.json`: achados técnicos de saída separados das métricas de contexto.
- `comparison.json` e comparações por condição: pares atual/histórico.
- `local_index_probe.json`: integração somente leitura no índice real.
- Manifests registram hashes de fontes/dataset e receipts de chamadas reais.

Execução a partir de `code/`, com Python/dependências/índice já configurados:

```powershell
python -m pytest tests/rag_baseline/test_temporal_invariants.py tests/rag_baseline/test_temporal_versions.py tests/rag_baseline/test_versioning.py -q -p no:cacheprovider
python -m pytest tests/rag_baseline -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
.venv\Scripts\ruff.exe check --no-cache src/rag_baseline/agentic.py src/rag_baseline/versioning.py src/rag_baseline/api.py src/rag_baseline/models.py src/rag_baseline/temporal_evaluation.py tests/rag_baseline/test_temporal_invariants.py
git diff --check
python -m rag_baseline.temporal_evaluation --output ../evaluation/results/nova_execucao_controlada
python -m rag_baseline.temporal_evaluation --live --output ../evaluation/results/novo_smoke_automatico
python -m rag_baseline.temporal_evaluation --live --manual-smoke --output ../evaluation/results/novo_smoke_manual
python -m rag_baseline.temporal_evaluation --reanalyze ../evaluation/results/agentic_temporal_hardening_v1_001/smoke_001 --output ../evaluation/results/nova_reanalise_offline
```

Para executar com Python 3.11.15, acrescentar `src` ao `PYTHONPATH` e usar
o ambiente com as dependências do projeto. Novas chamadas reais podem produzir outras saídas.
