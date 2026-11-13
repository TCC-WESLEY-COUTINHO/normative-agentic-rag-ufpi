# Grounding temporal da geração — v1

Consolidação: 30/10/2026. Experimento técnico exploratório, com anotações
provisórias do assistente; não é gold jurídico nem validação independente.

## 1. Objetivo e conclusão

Propagar decisões temporais determinísticas ao gerador, sem modificar Router,
retrieval, estratégia temporal ou relações do Version Filter. O contrato passou
nos testes estruturais e chegou ao prompt efetivo.

No caso histórico original da graduação, a negação do texto histórico disponível
caiu de **10/10 BEFORE para 0/10 AFTER**. No conjunto de 44 respostas por fase,
TCR caiu de **14/44 para 6/44** e HFA subiu de **4/20 para 20/20** segundo os
critérios técnicos declarados. Permaneceram invenções de cronologia e overclaim.

O resultado não foi uniformemente positivo: CSC caiu de **12/12 para 11/12** e
CGVR aumentou de **18/44 para 21/44**. O caso F3 repetido isoladamente melhorou
de **5/10 para 0/10** violações, mas a citação de inciso na pergunta de revogação
aumentou. Não houve tuning após observar AFTER, substituição de respostas ou
remoção textual de falhas.

## 2. Estado inicial e branch

Branch inicial `fix/agentic-temporal-hardening-v1`, HEAD verificado
`365d28a1d5b21ae27bd7220316aa5aa612ca608e`, árvore limpa. Executados status,
branch, HEAD, log de dez commits, diff, diff cached e diff stat antes de alterações.

Branch local `fix/temporal-generation-grounding-v1` criada exatamente desse HEAD.
Nenhum checkpoint vazio, pull, push, merge, rebase, reset ou clean foi executado.

## 3. Falha original e reprodução

Pergunta preservada:

> Como era o §4º do art. 68 na graduação sobre a escolha do coordenador de estágio antes da alteração de 2026?

O contexto congelado é o da condição manual anterior: art. 68 original da 177,
seguido dos arts. 69, 66, 80 e 79. O filtro registrou `historical_preserved`, não
aplicou o texto da 1056 e excluiu o ato posterior. O status da norma-base permaneceu
`desconhecida`.

Todas as dez gerações BEFORE negaram disponibilidade da redação histórica,
apesar de ela estar presente; oito também chamaram a redação de vigente. Modelo,
temperatura, contexto e prompt anterior foram preservados antes de editar produção.
`before.jsonl` contém respostas brutas, prompt efetivo, contexto, estado e referências.

## 4. Arquitetura anterior e dados perdidos

O fluxo real continua API → AgenticState → Router/escopo → classificação temporal
e pré-filtro → dense retrieval → Version Filter → contexto final → geração →
referências determinísticas.

Os nomes reais são `TemporalIntent`, `TemporalProvenance` e `VersionAudit` em
`versioning.py`; não existem `TemporalQueryIntent` ou `FilterResult` neste código.
O audit já possuía intenção, status, proveniência por chunk, alterações aplicadas,
relações documentais e decisões de insuficiência.

Antes, `agentic.generate` transmitia somente os chunks finais e um aviso em prosa
com status e orientação histórica/comparativa. `RagService.generate` montava
`_context(chunks)` e chamava `OpenRouterClient.chat`. A proveniência estruturada,
o motivo da preservação e a relação de alteração não chegavam como contrato ao
gerador. O modelo tentava inferir a temporalidade a partir do próprio texto.

## 5. TemporalGroundingContext

O novo módulo interno `code/src/rag_baseline/grounding.py` projeta dados já decididos
em uma estrutura pequena:

| Campo | Fonte |
|---|---|
| `temporal_intent` | `VersionAudit.temporal_intent.mode`, mesma taxonomia existente |
| `requested_time_context` | demais campos do mesmo TemporalIntent |
| `evidence_states` | proveniência dos IDs finais e status do audit |
| `known_relations` | relações documentadas do registry, pertinentes às evidências/pergunta |
| `generation_constraints` | intenção, estados, relações e metadados finais |

Cada evidência inclui ID, norma, artigo, ação temporal, status, papel temporal e,
quando disponível, referência resumida da base da relação. Não inclui conteúdo
integral, `previous_text`, `effective_text` ou trechos removidos. Nomes de atos
podem aparecer na relação documental sem expor o corpo de um chunk excluído.

O builder rejeita evidências diferentes de `audit.final_references`, ausência de
proveniência, filtro desligado e insuficiência. A projeção é idempotente e não
consulta LLM, embedding, índice, API ou resposta anterior.

## 6. Intervenção e prompt

`filter_context` guarda o contrato em `AgenticState.temporal_grounding` somente
quando há contexto elegível. `generate` o passa a `RagService.generate`, que aceita
o argumento opcional reutilizável `temporal_grounding`.

O prompt recebe instruções gerais e JSON delimitado por `[TEMPORAL GROUNDING]`.
O aviso anterior, os chunks e o system prompt F3 permanecem preservados. A única
diferença experimental é a seção de grounding acrescentada ao user prompt.
Não há números de resoluções hardcoded na instrução de produção.

Na comparação, `temporal_action` registra a ação legada do filtro, enquanto
`temporal_role` governa a apresentação como histórico ou posterior. A revisão
encontrou uma instrução ambígua, corrigida e testada antes de AFTER: ambos os
textos podem ter ação `historical_preserved`, mas o sucessor não vira predecessor.

## 7. Histórico

O contrato identifica a preservação como histórica e exige enquadramento temporal,
proíbe certificação de vigência atual e proíbe negar o texto efetivamente presente.
Também informa a relação de alteração pertinente sem exigir o corpo do ato posterior
para reconhecer o texto antigo.

As dez respostas AFTER do caso A apresentam a redação antiga como anterior à
alteração e respondem com o texto preservado. Isso resolve o sintoma reproduzido
nesse conjunto, sem garantir adesão geral a todas as restrições.

## 8. Current e indeterminate

Current mantém a política temporal já existente e explicita que a elegibilidade
foi decidida pelo pipeline. O gerador não deve reintroduzir conteúdo excluído ou
usar conhecimento externo para certificar status desconhecido.

Indeterminate permanece explícito. Sua política de seleção de snapshot não mudou,
e a instrução não autoriza converter ausência de intenção em certeza de vigência.

No único caso atual de alteração parcial AFTER, o modelo disse “A redação vigente”
apesar do status desconhecido. Esse resultado negativo reduz CSC e integra UOR/TCR.

## 9. Comparison

O contrato diferencia os papéis histórico e posterior usando a relação conhecida,
sem tratar `desconhecida` como vigente. A comparação congelada mantém 658 art. 43
e 956 art. 53, com os mesmos textos antes/depois.

A resposta AFTER separa os dois estados e explicita que o status da 956 é
desconhecido. Há somente uma repetição desse caso; não se faz claim de estabilidade
geral para comparações.

## 10. Validity

A pergunta de vigência da 658 recebe a relação comprovada `REVOKED_BY` e a base
956, art. 62, VI. Todas as dez respostas de ambas as fases mantêm a direção da
revogação. Entretanto, algumas acrescentam cronologia não documentada.

BEFORE contém inferências de temporalidade/alcance nas repetições 2, 5, 7 e 9;
AFTER inventa publicação ou entrada em vigor em 18/12/2025 nas repetições 2, 4, 8
e 10. A data não foi certificada pelo registry. A relação correta não torna essa
cronologia correta.

## 11. Unknown

O contrato mantém `normative_status=desconhecida` separado de ação/papel temporal
e deriva `must_not_claim_unknown_as_current`. Status sem comprovação não certifica
vigência.

O caso direto G (“A Resolução 956/2025 ainda está vigente na pós-graduação?”)
permaneceu conservador, **1/1 antes e depois**. A redução agregada de UOR decorre
principalmente da eliminação do overclaim no histórico da graduação; não representa
dez novas perguntas independentes sobre unknown.

## 12. Amendment e amendment_unresolved

`amendment_applied` identifica somente a substituição parcial registrada, conserva
a norma-base e não representa revogação integral. A relação informa art. 68, §4º
como alvo e 1056 art. 1 como base, sem duplicar redação velha e nova no contrato.

O histórico usa a redação antiga preservada. `amendment_unresolved` continua
abstendo antes de gerar; não é transferido ao modelo para resolução. O teste
assegura zero chamadas ao gerador nesse caminho. VersionFilter e registry não mudaram.

## 13. F3 e teto de citação

Os metadados finais atuais suportam localização por fonte e artigo, sem campos
validados de parágrafo/inciso/alínea. O contrato deriva teto `article`. O prompt
F3 existente e `_reference` permanecem inalterados. Mencionar o §4º perguntado ou
transcrever o texto não equivale automaticamente a uma citação bibliográfica fina.

O caso H repetido deixou de acrescentar §1º indevido: **5/10 → 0/10** violações.
Contudo, na pergunta de revogação AFTER, as dez respostas copiaram art. 62, VI,
embora o teto de citação fosse artigo. O inciso é documentado na relação, mas não
foi autorizado pelo teto bibliográfico desta interface. Isso é descumprimento do
contrato, não prova de que o inciso inexista na norma.

No conjunto completo, CGVR aumentou. Esse resultado foi preservado; não foram
apagadas citações por regex nem ajustado o prompt após AFTER.

## 14. Desenho before × after

O dataset novo contém oito casos. A, C, E e H têm dez repetições por fase;
B, D, F e G têm uma. Total: **44 BEFORE + 44 AFTER**, sem erros de provedor.

São contextos finais congelados, derivados dos traces da etapa anterior. O caso A
usa exatamente a pergunta e os cinco chunks do histórico manual que falhou. H usa
a pergunta F3 conhecida com contexto final atual preservado. Não foi executado
retrieval real novamente; isso isola a fronteira de geração e não avalia F1/F2.

Modelo `qwen/qwen3-30b-a3b-instruct-2507`, temperatura 0, limite de 800 tokens e
top-k 5 preservados; endpoint configurado `https://openrouter.ai/api/v1`.
Não houve chamadas adicionais a embedding, Router ou LLM-as-judge no experimento.
As gerações usam o mesmo system prompt nas duas fases.

`comparison.json` verifica **44/44 pares** com mesma pergunta, contexto, estado,
referências e system prompt. Somente o user prompt recebe a seção estruturada.
Não houve mudança do dataset para melhorar resultados nem tuning posterior.

## 15. Métricas e método de anotação

`annotation_protocol.json` foi salvo antes de observar AFTER. `annotations.jsonl`
contém julgamento técnico explícito por saída, hash da resposta, códigos de falha
e evidências. São anotações provisórias do assistente, sem validação
independente; não são gold jurídico. O agregador apenas calcula as razões.

| Métrica | BEFORE | AFTER |
|---|---:|---:|
| Temporal Contradiction Rate — TCR | 14/44 (31,82%) | 6/44 (13,64%) |
| Historical Framing Accuracy — HFA | 4/20 (20%) | 20/20 (100%) |
| Current-State Consistency — CSC | 12/12 (100%) | 11/12 (91,67%) |
| Unknown Overclaim Rate — UOR | 8/34 (23,53%) | 1/34 (2,94%) |
| Temporal Relation Consistency — TRC | 22/32 (68,75%) | 32/32 (100%) |
| Citation Granularity Violation Rate — CGVR | 18/44 (40,91%) | 21/44 (47,73%) |

TCR inclui negar o histórico fornecido, chamá-lo de atual ou inventar cronologia/
alcance temporal. HFA exige contextualização histórica e não negar o texto; mera
atribuição à resolução com verbos futuros não basta. CSC é temporal, sem incorporar
erro de citação como se fosse erro temporal. UOR conta certificação positiva de
vigência para evidência unknown; seu denominador inclui qualquer fonte final unknown.

TRC mede compatibilidade da relação conhecida, não prova de datas. Uma saída pode
passar TRC e falhar TCR por inventar eficácia. A referência de avaliação é a decisão
do pipeline congelada: BEFORE ainda não recebia todas essas decisões em contrato.
CGVR conta localização bibliográfica fina além do teto, não toda menção ao dispositivo
perguntado ou sua transcrição. Todas as 44 respostas por fase têm referências
normativas estruturadas. Denominador zero resulta em `null`.

## 16. Estabilidade

- A histórico da graduação: negação **10/10 → 0/10**; framing **0/10 → 10/10**.
- C histórico da pós: framing **4/10 → 10/10**; AFTER ainda inventou eficácia na repetição 6.
- E vigência: direção de revogação **10/10 → 10/10**; cronologia indevida **4/10 → 4/10**.
- H F3: citação fina indevida **5/10 → 0/10**.

Temperatura zero não produziu texto idêntico em todas as repetições. As fases são
sequenciais, não randomizadas, e as repetições pertencem aos mesmos quatro casos.
Não representam quarenta perguntas independentes, validação confirmatória ou
estimativa da população de usuários.

## 17. Casos que continuaram falhando

AFTER B chama a redação unknown de vigente. AFTER C6 inventa que os artigos
estavam em vigor na data de publicação. AFTER E2/E4/E8/E10 inventam publicação ou
eficácia em data não comprovada. Citações além do teto permanecem em A, C, D e E.

As falhas observadas nesta comparação são `GENERATION`; o contexto foi mantido
idêntico. Não foram atribuídas a Router, retrieval ou Version Filter, nem
mascaradas. Relação documental correta e contexto elegível não garantem resposta
inteiramente correta.

## 18. Limites

A evidência favorece melhora do histórico nos casos testados, com adesão parcial
às demais constraints e regressão agregada de granularidade. A anotação semântica
é provisória e pode exigir revisão independente. Oito casos, repetições desiguais,
um provedor/modelo e execução sequencial limitam a inferência causal e a generalização.

Não se certifica vigência global, publicação, eficácia, retroatividade, alcance
por turma ou correção jurídica de todas as afirmações. Contextos congelados não
medem recuperação, roteamento, memória ou uso conversacional real.

O argumento opcional mantém chamadas legadas sem grounding compatíveis. Sua
garantia estrutural se aplica quando o fluxo filtrado constrói e passa o contrato;
não torna chamadas diretas sem contrato equivalentes ao pipeline normativo.

## 19. Alterações de produção e compatibilidade

Mudanças restritas a `grounding.py`, ao campo de estado e passagem em `agentic.py`,
e ao argumento/renderização em `RagService.generate`. Não foi alterado o texto
bruto retornado pelo provedor ou o algoritmo de referências.

Router V1 continua padrão, com prompt/schema/parser/fallback intactos; V2-D/V2-L
continuam explícitos e experimentais. Retrieval e F2 não mudaram. VersionFilter,
classificação temporal, registry e relações normativas foram preservados. Nenhuma
integração com agents, memory, client, metadata search ou tool calling foi feita.

## 20. Testes e verificação

- Novo arquivo de grounding/métricas: **10 passed**.
- Temporais com grounding: **78 passed**.
- `tests/rag_baseline`: **286 passed, 10 skipped**.
- Suíte completa: **349 passed, 12 skipped**.
- Ruff nos cinco arquivos Python da entrega: **All checks passed**.
- `git diff --check`: exit code **0**.
- Nenhuma API real no pytest normal.

O primeiro baseline teve 275 passed, uma falha e dez skips: um teste legado de
Chroma temporário falhou com `Nothing found on disk` no leitor HNSW. A repetição
isolada passou e as regressões completas posteriores passaram sem mudança de
retrieval ou do teste legado. O evento foi registrado, não omitido.

Warnings de LangChain/Pydantic, AsyncMock e timeout de TestClient foram preservados.
Comandos, contagens e ciclos RED/GREEN constam em `verification.json`.

## 21. Preservação e artefatos

`preservation_before.json` e `preservation.json` verificam **507 registros** com
mesmos IDs, textos, metadados e embeddings float32 e **290 arquivos protegidos**
sem alteração, incluindo corpora, registry, datasets/resultados anteriores e
componentes congelados. Nenhuma reindexação foi realizada.

`frozen_contexts.json`, `before.jsonl` e `after.jsonl` conservam contexto bruto,
estado, prompt efetivo, resposta bruta, referências e receipts sem segredo. O
prompt do próprio gerador está salvo como evidência técnica autorizada.

Uma solicitação de execução externa foi inicialmente rejeitada pela revisão
automática por dúvida de autorização de payload/destino. Conferidos o endpoint,
as fontes públicas UFPI e a autorização explícita do pedido, a reapresentação foi
aprovada. A execução rejeitada não fez chamadas, e não houve contorno do bloqueio.

## 22. Reprodução e commits locais

A partir de `code/`, com ambiente já configurado:

```powershell
python -m pytest tests/rag_baseline/test_temporal_grounding.py -q -p no:cacheprovider
python -m pytest tests/rag_baseline -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
.venv\Scripts\ruff.exe check --no-cache src/rag_baseline/grounding.py src/rag_baseline/agentic.py src/rag_baseline/service.py src/rag_baseline/generation_evaluation.py tests/rag_baseline/test_temporal_grounding.py
git diff --check
```

`generation_evaluation --stage before/after --output <pasta>` executa somente a fase
explicitamente solicitada sobre seus `frozen_contexts.json` e manifest, recusando
sobrescrever o arquivo da fase. `prepare` exige destino e dataset novos; não deve
ser reaplicado sobre os artefatos congelados desta entrega. O BEFORE desta comparação
foi capturado no código anterior; gerar um novo BEFORE no código corrigido não
reconstitui automaticamente o prompt antigo. Para repetir estas entradas, use
as capturas preservadas e nova pasta. As chamadas reais podem produzir outras saídas.

O Python compatível usado está em
`D:/faculdade/TCC/RAG/.uv-python/cpython-3.11.15-windows-x86_64-none/python.exe`, com
`PYTHONPATH=src;.venv/Lib/site-packages`. Não houve alteração de dependências.

Commits locais: `a1062a1` (`test: capture temporal generation grounding failures`),
`fd3caa6` (`fix: propagate temporal provenance to generation`) e o commit de
evidências `experiment: evaluate temporal generation consistency` que contém este
relatório.

Nenhum segredo ou artefato de processo de IA foi incluído. Nenhum push, merge,
rebase, frontend, metadata search, calculator, tool calling, deploy ou experimento
com estudantes foi iniciado. A árvore é conferida novamente após o commit final.
