# Correção pré-freeze de domínio explícito e fallback temporal

Correções técnicas dos casos A e B concluídas, com revisão independente e regressões verdes. O probe normal final respondeu A/accepted e B/regenerated, sem clarification de setor nem fallback. Focused: **733 passed**. Full suite: **1227 passed, 12 skipped, 6 warnings, exit 0**. Índice: **507/507 idêntico**.

Esta entrega é uma regressão técnica pré-freeze. Não constitui validação jurídica ou avaliação científica final. A revisão técnica registrada em `review_findings.json` não constitui validação jurídica ou científica das respostas e deste relatório.

## Git

Estado inicial observado: branch `fix/pre-freeze-conversation-policy-compact-references`, HEAD **`0e5107cd60973d929032f173986a51513487889c`**, árvore limpa. Status, branch, HEAD, log de 15 commits, diff e diff staged foram conferidos antes das mudanças produtivas. `preservation.json.initial_git_commands` registra esses comandos; sua entrada não rastreada é o runner de auditoria recém-criado, posterior à observação inicial limpa.

Branch final: **`fix/pre-freeze-explicit-sector-temporal-fallback`**. Trabalho anterior preservado.

| Commit local | Conteúdo |
|---|---|
| `2f5c89ba91fb4c071d874fb8b9ae814cf4bdd883` | `fix: resolve explicit normative sectors before Router V1` |
| Commit que contém este relatório | `fix: constrain temporal validity regeneration without weakening guards` |

O HEAD final inclui a correção B e os artefatos.

Somente três arquivos produtivos mudaram: `agentic.py`, `routing.py` e `service.py`, em `code/src/rag_baseline/`. Há 15 arquivos de testes/fixtures alterados ou adicionados, incluindo os dois novos módulos de regressão. Arquivos novos de testes foram adicionados explicitamente porque a regra existente de ignore os ignora; o ignore permaneceu igual.

## Case A Root Cause

Pergunta: “A Resolução 658/2024 ainda pode reger hoje a pós-graduação da UFPI ou foi revogada? Qual ato e dispositivo estabelecem isso?”

Em `before_traces.json`, action=NORMATIVE_RAG, Scope=IN_SCOPE_NORMATIVE, uma chamada Scope e helper de setor=pos_graduacao. O Router recebeu a pergunta original completa, clarification=null. A normalização e o reconhecimento de setor funcionavam.

O retorno bruto do Router continha scope=pos_graduacao, needs_clarification=false e reason_code=explicit_pos, mas também uma clarification_question não nula explicando que a pergunta era sobre pós. Essa combinação viola o schema. A validação produziu invalid_model_decision e a facade terminou ERROR/router_error, sem retrieval. Isso reproduz a falha de decisão sobre setor explícito; o terminal observado nesta reprodução foi ERROR, enquanto o navegador relatou CLARIFICATION. Não se afirma que foram terminais idênticos.

A causa localizada foi submeter um setor já inequívoco a uma decisão LLM que podia contradizer o contrato. Não foi perda da expressão “pós-graduação” nem interferência do Scope Gate.

## Case A Fix

O modo `intent_v1` reutiliza `question_sector(..., explicit_only=True)` antes do Router, após o Scope Gate. Somente um setor declarado e inequívoco resolve diretamente. Registra explicit_sector_fast_path_used, resolved_sector e router_calls=0. A inferência temática anterior continua disponível aos consumidores que usam o helper sem o novo parâmetro.

IRA, Exame Final e Láurea isolados não ativam o caminho estrito. Comparações de níveis, abreviações mistas e ocorrências ambíguas de “pós” seguem ao Router. Foram preservados os negativos pós-recurso, pós-defesa, pós-2025 e pós-pandemia, incluindo pontuação Unicode. Não foi criado classificador novo, outro LLM ou lista temática de bypass.

As quatro perguntas positivas exigidas, graduação explícita e “a pós” estão cobertas. Continuação de clarification mantém seu fluxo anterior. Router V1 continua para consultas sem setor inequívoco; Router V2 e Scope Gate permanecem iguais.

No probe final A: Scope IN_SCOPE_NORMATIVE, setor pos_graduacao, fast path=true, Router=0, intent=validity, strategy=vector_filtered, referência final 956/2025 art. 62, uma geração, guard sem violações, accepted. O dispositivo revogador foi obtido do sistema temporal; não foi hardcodado no routing. Os candidatos vetoriais iniciais estavam vazios nesse probe; o fluxo temporal normal incluiu a evidência estruturada de revogação no output do VersionFilter.

## Case B Root Cause

Pergunta confirmada pelo usuário: “Em um curso de graduação da UFPI ofertado por programa institucional, um professor selecionado por edital, sem vínculo efetivo com a universidade, pode ser coordenador de estágio?”

O fallback manual foi localizado em checkpoint. A primeira extração consultou a projeção pública e concluiu, incorretamente, que não havia auditoria interna persistida. A revisão independente encontrou o envelope privado em memória: `to_persistence()` salva internal_audit, recuperável por `restore_result()`. A busca foi corrigida e recuperou a auditoria da mesma correlation_id, **`3d174b4a-570d-4e40-9176-9720bd4b13b0`**. `manual_case_b.json` preserva a extração incompleta; `manual_case_b_private_audit.json` contém o resultado completo recuperado. A hipótese inicial de causa irrecuperável foi superada antes do fix.

As evidências e a relação temporal estavam presentes. A primeira geração explicava a ressalva, mas acrescentava “permanece em vigor”. O guard rejeitou **unsupported_current_validity**, offsets 933–951. A regeneração repetiu a certificação em “redação vigente”, offsets 673–688, e recebeu o mesmo código. Após duas tentativas, ocorreu fallback. regeneration_error=null.

A causa concreta foi geração de certificação de vigência atual sem suporte, seguida de orientação de retry insuficiente para evitar sua repetição. O guard rejeitou corretamente. A geração não ignorou a exceção substantiva; o problema foi a afirmação temporal adicional. Retrieval, VersionFilter e target provision não perderam a alteração.

## Case B Trace

O checkpoint manual preserva resultado, referências, proveniência temporal, auditoria de retrieval e gerações/guards no envelope privado. Os objetos brutos completos do retrieval não estavam persistidos nesse checkpoint; os probes novos capturam candidatos e entradas/saídas completas das camadas.

Nos probes B com geração, a estratégia dense_vector recuperou, em ordem: **1056/2026 art. 1; 177/2012 arts. 87, 68, 65 e 66**. As cinco evidências permaneceram elegíveis. TemporalGroundingContext contém AMENDED_BY, norma-base 177, ato 1056, target_article=68 e target_paragraph=4. As permissões incluem o art. 1 do ato e o §4 do art. 68 da base como amendment_target. As referências e a proveniência temporal do fallback manual coincidem com uma reprodução accepted.

| Etapa | Manual recuperado | Probe normal final |
|---|---|---|
| Scope | Resultado normativo persistido; sem contador histórico de Scope disponível | IN_SCOPE_NORMATIVE, 1 chamada |
| Setor / Router | Não se reconstrói decisão bruta ausente do checkpoint | graduacao, fast path=true, Router=0 |
| Temporal / retrieval | Relação AMENDED_BY e auditoria preservadas | indeterminate / dense_vector |
| Evidências finais | 1056/1 e 177/87,68,65,66 | As mesmas cinco |
| Geração 1 / guard | “permanece em vigor” / unsupported_current_validity | “é vigente” / unsupported_current_validity |
| Geração 2 / guard | “redação vigente” / unsupported_current_validity | Exceção e condições preservadas / nenhuma violação |
| Resultado | ANSWER/fallback | ANSWER/regenerated |

Os probes em threads novas registram thread_id, pending_before/after, correlation_id, action, Scope, routing, intent, candidatos ordenados, VersionFilter, grounding, chunks elegíveis, referências, gerações e guards. Pending ausente no início; o final B também termina sem pending. Os textos integrais e offsets estão nos JSON.

## Case B Fix

Em `service.py`, somente quando o primeiro guard retorna unsupported_current_validity, a única regeneração existente recebe restrições estruturadas adicionais: remover os excertos rejeitados, não certificar vigência atual a partir da relação documental e preservar o conteúdo substantivo suportado, com suas condições e exceções.

Uma primeira versão do reparo removeu o problema temporal, mas um replay com retry real introduziu atribuição inválida de citação: unallowed_article e unvalidated_subdivision. Esse resultado permanece em `live_retry_trace.json`. Um segundo RED reproduziu essa falha; a orientação passou também a pedir explicação substantiva sem citações redundantes no corpo, deixando referências tipadas e framing temporal à aplicação.

A omissão de citações é uma instrução ao modelo, não uma garantia. No probe normal final, a regeneração manteve citações autorizadas e passou pelo guard. Não há sanitização posterior, regex nova ou alteração das permissões. A geração inicial, guard, locators, grounding e máximo de uma regeneração permanecem iguais. Não há pergunta, norma, artigo ou resposta específicos hardcodados nessa correção.

`live_retry_final_trace.json` usa a primeira geração manual gravada e uma regeneração real do provider: regenerated, segundo guard vazio. `final_complete_traces.json` usa todo o provider normal, sem injetar geração: B produziu espontaneamente “é vigente”, o guard bloqueou e o retry corrigiu. A resposta final preserva as condições de programa/política e seleção por edital, sem tornar a exceção regra geral, com 177 como base e 1056 como ato alterador.

## RED

Comandos completos, cwd, exit, duração e falhas constam em `test_results.json` e na ordem de `execution_log.jsonl`. Python 3.11.15 com dependências locais existentes; testes executados de `code/`.

| Etapa | Comando resumido (`python -m`) | Resultado anterior ao respectivo fix |
|---|---|---|
| A inicial | `pytest -q tests/rag_baseline/test_explicit_sector_fast_path.py` | 7 failed, 11 passed |
| Comparação abreviada | Mesmo módulo, seleção registrada no JSON | 3 failed |
| Comparação com Unicode | Mesmo módulo, seleção registrada no JSON | 5 failed |
| B manual | Módulo temporal, seleção manual/retry registrada | 1 failed, 1 passed, 7 deselected |
| B retry com locator inválido | Módulo temporal, seleção retry/locator registrada | 1 failed, 9 deselected |

As sete caracterizações de B anteriores à recuperação da auditoria ficaram verdes após corrigir expectativas de fixtures; as falhas iniciais dessas caracterizações não reproduziam o fallback manual e não foram apresentadas como RED do defeito. O RED B foi criado após recuperar a geração e os guards manuais. Os testes usam provider controlado na fronteira e executam o pipeline real de evidências/grounding/guard, verificando condições, referências, permissões e resultado. A classificação/geração do modelo real é observada separadamente nos probes.

## GREEN

| Verificação final | Resultado |
|---|---|
| Fast path e negativos | 23 passed |
| Regressões B e candidatos temporais | 10 passed |
| Focused final completo | **733 passed, 2 warnings, 57.91 s, exit 0** |
| Ruff check | All checks passed, exit 0 |
| Ruff format --check | 21 files already formatted, exit 0 |
| git diff --check | exit 0 |

O focused inclui Scope, policy/pending, Router V1, normalization/fast path, intent temporal, retrieval, VersionFilter, grounding, geração/guard/locators, retry/fallback, integração, memória e transport.

A primeira full suite apontou expectativas antigas de chamadas ao Router. Foram migradas para o setor explícito mantendo as verificações de retrieval, grounding, correlação e memória; cenários que precisam exercitar o Router usam pergunta sem nível declarado. Todas as falhas intermediárias permanecem registradas. Os antigos resultados 730/1224 foram superados pelas execuções completas após o fix B, não reutilizados como verificação do código final.

Revisão técnica independente: dois problemas de comparação abreviada/Unicode resolvidos com RED/GREEN; busca do envelope privado corrigida; revisão do reparo B e dos probes finais sem finding de implementação restante. O revisor registrou recortes de 329, 171 e 157 testes; não são somados à full suite como casos independentes.

## Probe Metrics

Foram preservados **14 requests: 12 normais e 2 replays da primeira geração manual com regeneração real**. As repetições iniciais investigaram a intermitência antes de a causa privada ser recuperada. Não foram descartados o ERROR inicial A, a clarification B nem o replay intermediário com fallback.

| Artefato | Requests / natureza | Resultados |
|---|---|---|
| before_traces | 2 normais | A ERROR; B accepted |
| before_b2 | 1 normal | B CLARIFICATION |
| routing_fixed_traces | 2 normais | A e B accepted |
| exact_block_trace | 1 normal, quebras do anexo | B accepted |
| b_repeated_traces | 3 normais | B accepted nas três |
| final_a_trace | 1 normal | A accepted |
| live_retry_trace | 1 replay | B fallback por locators no retry |
| live_retry_final_trace | 1 replay | B regenerated |
| final_complete_traces | 2 normais | A accepted; B regenerated |

`probe_metrics.json` contém por request todos os campos pedidos: Scope, setor, fast path, Router, intent, estratégia, presença de normas nos candidatos e no VersionFilter, contagem de referências, tentativas, guards, fallback e terminal. Para A registra também 658/956 e as relações temporais. Presença nos candidatos brutos e evidência incluída posteriormente pelo fluxo temporal são campos distintos.

Runtime normal `build_integrated_agent_runtime`, grafo `chatbot_ufpi_integrated_v1`, InMemorySaver e projeção oficial. Provider/config normais: OpenRouter HTTPS, qwen/qwen3-30b-a3b-instruct-2507, temperature 0, max_tokens 800, embedding openai/text-embedding-3-small, top_k 5, collection ufpi_duas_regulacoes_setor. Os probes usam os três módulos corrigidos por overlay em processo isolado, com hashes iguais ao checkout. Não houve reconstrução/deploy da API/UI; **o navegador continua com a imagem anterior**. Só os dois replays rotulados substituem a primeira geração pelo texto manual.

## Preservation

Índice antes/depois: **507/507**, SHA256 **`ab253a24b756d9f3d3e05aeb49220798b08d947704112327fd894a577bb2b38a`**. Snapshot lógico idêntico.

Registry canônico: **`fbd017d0f080481bb0f89e6809b48a87317d8fc97909e7ec2d40f8240bff25ef`**.

Router V2 `adaptive_router.py`: **`41b3e56fcc83b33998b614ab13fe37f2e71c42e90a5010d3827aea9a62aff186`**, antes=depois.

`preservation.json` contém hashes individuais: **108 arquivos protegidos idênticos**, incluindo Scope Gate/prompt, Router V1/V2, VersionFilter, guard/locators, grounding, retrieval/config, registry, corpus/data e UI. Sete funções protegidas de `agentic.py` têm AST idêntica: classificação temporal, detecção histórica, route_query, reroute, retrieve, filter_context e generate.

Modelos, temperature, embedding, top_k, collection, chunks, metadata e estratégias permanecem iguais. O único ajuste de instrução normativa é o reparo condicional do retry em `service.py`. O mapa de hashes de fontes/testes ao final da suite permite conferir preservação até o commit.

Não houve UI nova, reindexação, re-embedding, promoção de Router V2, deploy, freeze, avaliação final, push/pull/merge/rebase/reset/clean ou descarte de trabalho.

## Full Suite

Comando final: `python -m pytest -q -rs --tb=short`, cwd `code/`.

**1227 passed, 12 skipped, 6 warnings em 103.75 s, exit 0**, registro `full_final_complete`. Nenhum arquivo produtivo/teste mudou depois dessa execução.

Skips: dois testes Docker exigem --run-docker; um exige CITATION_REGRESSION_RUN; nove exigem ROUTER_REGRESSION_RUN. Não contam como pass.

Warnings: dois serializers Pydantic em fixtures deliberadamente inválidas; um AsyncMock/coroutine não awaited no teste client/test_astream; duas deprecações LangChain/Pydantic __fields__; uma deprecação de timeout Starlette TestClient. Foram preservados, sem correções fora do escopo.

## Limitations

TEMP-GRAD-001–005 permanecem candidatos, sem validação independente registrada, usados como DEVELOPMENT/REGRESSION CANDIDATES. Nenhum dataset ou referência candidata foi modificado ou promovido a gold científico. As 40 perguntas históricas continuam expostas ao desenvolvimento, inelegíveis como futuro TEST independente não visto.

TEMP-GRAD-002 tem uma limitação anterior: o ano em “atualizado em 2023” é interpretado como requested_year e termina chronology_unresolved no cenário de teste. Esse comportamento foi caracterizado e preservado; não foi corrigido sem diagnóstico próprio. Os outros candidatos verificam a relação e os contratos, não correção jurídica universal.

Uma instrução de retry reduz o erro observado sem garantir toda geração futura. Saídas que continuem inválidas ainda devem terminar fallback; há teste desse comportamento. Guard de locators/vigência não é um juiz factual/jurídico completo. A atribuição de citações tem limites de janela/contexto; a falha intermediária foi preservada e não motivou relaxamento.

O checkpoint manual não contém todos os contadores históricos ou objetos brutos de cada camada; os novos probes fornecem o trace completo observado em threads novas. As amostras são pequenas e conhecidas; não estimam precisão geral ou garantem reprodutibilidade bit a bit do provider.

## Findings Remaining

Nenhum finding técnico de implementação aberto para os fixes A/B após revisão de código. Permanecem **TEMP-GRAD-002/chronology_unresolved, preexistente e fora deste fix**, limites de geração/guard e a ausência de validação jurídica ou científica registrada do relatório e do conteúdo. O ambiente do navegador ainda usa a imagem anterior, pois deploy foi expressamente excluído desta etapa.

Não inicia redesign ou freeze.
