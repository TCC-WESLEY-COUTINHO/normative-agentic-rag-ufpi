# PRE-FREEZE UX & ANSWER RELIABILITY V2

Etapa de correção funcional anterior ao freeze; não é avaliação científica nem certificação de correção jurídica. Os alvos reproduzidos foram corrigidos e a operação local foi restabelecida. Não há confirmação visual do scroll e da animação registrada. O Router ainda apresentou falhas operacionais em consultas adicionais, registradas abaixo.

## 1. Estado inicial

Branch `fix/pre-freeze-ui-routing-defects-v1`; HEAD `91c51c97c52443ecdee8385fdb070854378d3b26`; árvore e index limpos.

## 2. Branch final

`fix/pre-freeze-ux-answer-reliability-v2`, criada a partir do HEAD real.

## 3. Article UI antes

Um expander `Trechos normativos recuperados` continha todos os artigos e textos em sequência. A identificação aparecia repetida em label, source e detalhes. A nova resposta somente era apresentada após rerun.

## 4. Article UI depois

Uma caption `Trechos normativos recuperados` seguida por um expander independente para cada referência estrutural distinta. Todos iniciam fechados. O label usa display_text e, quando fornecida pelo contrato, validated_subdivision. A identificação documental útil fica dentro do artigo; papel temporal aparece somente para histórico/posterior. Não são exibidos chunk_id, score, embeddings ou correlation_id.

## 5. Article collapse

Implementação em `code/src/streamlit_app.py::render_references`, com `st.expander(label, expanded=False)`. Removido o expander externo; nenhum nesting. Dedup usa o objeto tipado completo, conservando duas referências com o mesmo display_text e identidades diferentes. AppTest confirma três referências distintas → três expanders fechados, sem perda de texto.

## 6. Preview

Não implementado. O artigo fechado já limita a altura da conversa; ao abrir, apresenta evidence_text completo. Não há estado adicional de preview, recorte do contrato ou parser de caput/parágrafo/inciso/alínea.

## 7. Evidence text

Sem mutação no contrato, transporte, memória ou índice. Nos smokes finais, 17/17 hashes de evidence_text coincidem com os documentos do índice; todos foram renderizados. O componente `st.text` remove whitespace externo visualmente, como antes. A mensagem final e os fragmentos do progressive renderer conservam o texto original; Markdown aplica sua normalização nativa de espaços/indentação. Referência legada sem evidence_text conserva aviso seguro.

## 8. Reprodução exata da frequência

Pergunta: `Qual é a frequência mínima que eu preciso ter nas aulas para não ser reprovado por falta?`. Diagnóstico operacional real antes da correção usou `clarification=graduação`, pois a pergunta não declara nível. Registro completo em `regression_cases.json.frequency_before`: question, routing categórico, domínio, retrieval audit, referências, evidence_text, raw, violações, regeneração e resposta final.

## 9. Route/domain da frequência

Rota graduacao; Router V1; retrieval dense_vector. Em nova conversa HTTP/UI, a pergunta exata pede nível; depois de `graduação`, consulta a pergunta original. Esse esclarecimento contextual é legítimo e foi preservado. O diagnóstico antes/depois compara o mesmo contexto de graduação.

## 10. Retrieval da frequência

Ordem observada: arts. 112, 115, 113, 114 e 118 da Resolução 177/2012. Art. 112 contém literalmente frequência inferior a 75%; art. 115 contém mais de 25% de ausência. O retrieval estava correto. Nenhuma alteração em embedding, top_k, estratégia, filtro de versão ou índice.

## 11. Raw generation

Antes, o gerador explicou 75% e citou `Art. 112, inciso I`. O inciso consta do texto, mas não estava autorizado estruturalmente para a citação naquela consulta. O raw completo está no artefato de regressão, separado da resposta pública.

## 12. Guard result

`unvalidated_subdivision`, excerpt `inciso I`. Os locators autorizados tinham norma/artigo e subdivision_type=null. O guard estava correto: informação presente no texto não promove automaticamente sua granularidade de citação. Seu código e a ContentLocatorPolicy permaneceram idênticos; não foi tratado como false positive.

## 13. Regeneration

Antes, a única regeneração repetiu `inciso I`; segunda violação do mesmo tipo → fallback. Depois, o diagnóstico real produziu uma regeneração sem subdivisão e second_guard_violations vazio. O smoke final HTTP também terminou com core_status=regenerated. As auditorias finais persistidas estão em `final_persisted_audits`, incluindo raw, regeneração e permissões.

## 14. Root cause do fallback

Geração e regeneração não respeitavam a granularidade permitida. As instruções apresentavam locators estruturados, mas não davam uma orientação operacional suficientemente explícita para citar apenas o artigo e manter a regra substantiva. O fallback foi consequência da segunda rejeição correta. Não houve falha de retrieval, chronology guard ou transporte.

## 15. Correção

`body_instructions` apresenta formas de citação derivadas exclusivamente dos AllowedContentLocator existentes, explicando que texto da evidência não autoriza subdivisões. Quando todos os locators são article-level, adiciona instrução expressa para não escrever §/parágrafo/inciso/alínea/caput nas citações. A solicitação de regeneração explica como omitir a subdivisão indevida sem inventar outra. Permanece primeira geração → uma regeneração → fallback. Não há limpeza automática de respostas, extração heurística ou retries adicionais.

Uma pergunta longa intermediária ainda repetiu §6º nas duas tentativas. Esse resultado negativo motivou o RED específico da instrução article-only, em vez de relaxar o guard. Não se afirma que instruções tornem o provider infalível.

## 16. Por que não é hardcode de 75%

Nenhum valor percentual ou pergunta de frequência foi adicionado à lógica de produção. As formas autorizadas vêm dos contratos estruturados da consulta; o modelo continua produzindo o conteúdo com as mesmas evidências. Números aparecem somente em testes, corpus, respostas/auditorias e relatório.

## 17. Casos diretos adicionais

Testes controlados cobrem regra numérica do art. 114 (registro a cada 60 minutos), regra textual do art. 115 e regra de frequência do art. 112. Smokes reais adicionais: art. 114 via metadata_exact → accepted; art. 112, inciso I explicitamente pedido → accepted, com a subdivisão autorizada apenas naquele contexto. Permissões article-level continuam recusando a mesma subdivisão quando não autorizada.

## 18. Insuficiência real e extrapolação

Preservados os caminhos sem contexto elegível e os guards de artigo/norma/subdivisão/cronologia. O replay em que o provider ignora a permissão duas vezes continua fallback, com exatamente duas chamadas. O teste de abstenção confirma preservação de uma abstenção fornecida pelo provider, não capacidade semântica independente de detectá-la. A suíte existente cobre domínio/temporalidade incompatível.

O guard é delimitado a formas estruturais e temporais; não prova suporte de toda afirmação livre. A resposta operacional de IRA mudou corretamente de assunto, mas inclui afirmações de ausência/dispensa de IRA cuja suficiência não é estabelecida por esse guard. Ela não entra na métrica de conclusão com evidência direta nem certifica resposta juridicamente correta. Não foi introduzida regra que converte todo contexto em answer.

## 19. “Como trancar a pós”: antes/depois

RED exato demonstrou ausência de canonicalização e CLARIFICATION controlada. Depois, a pergunta é enviada ao routing como `como trancar a pós-graduação`, mantendo a original na memória/retrieval. Smoke real final: ANSWER, pos_graduacao, accepted; cinco referências.

## 20. Normalização de “a pós”

Regex restrita ao sintagma standalone `a pós` seguido apenas de pontuação/espaço e fim da pergunta. Preserva as formas na/da/pela/para a pós já existentes. Não transforma globalmente qualquer token pós nem fixa domínio fora do Router.

## 21. False positives

0/6 expansões indevidas nos negativos controlados: pós-alteração, pós-2025, efeito pós recurso, situação pós defesa e construções com `a pós` seguidas de hífen/texto temporal. Os quatro positivos obrigatórios passam. A suíte anterior de cues/ambiguidade também passou.

## 22. Sequência trancamento → IRA

Teste integrado controlado: duas novas operações normativas post, sem reutilizar resposta de trancamento e sem pending indevido. No primeiro smoke real, o turno de IRA pediu nível mesmo depois de um ANSWER; não era continuação de trancamento. Uma consulta isolada do mesmo texto canônico retornou post, demonstrando variabilidade.

O prompt V1 tratava IRA como pista de graduação sem estabelecer precedência sobre nível explícito. A atribuição da oscilação a essa ambiguidade é uma inferência de engenharia: a decisão bruta da tentativa HTTP não foi capturada, e o replay isolado acertou. Não se declara causa cognitiva do modelo. Após RED específico, mudou somente essa instrução: nível explícito prevalece sobre pista temática. No smoke final: `como trancar a pós` → ANSWER post; `precisa de ira pra passar na pós` → novo ANSWER post, regenerated, conteúdo sobre aprovação. Nenhum texto da pergunta foi hardcodado na produção.

## 23. Pending

ConversationFollowUpPolicy, resolver, memória e semântica de pending permanecem byte a byte idênticos. O teste integrado confirma pending=None depois de ambos os turnos; o checkpoint do smoke final de IRA confirma pergunta atual armazenada e pending=None. Não se migrou nem apagou memória antiga.

## 24. Arquitetura do streaming

Backend: pipeline completo → guard/regeneração → ChatMessage final tipado → SSE message + DONE. UI: consome o stream completo, revalida o payload e somente então armazena/apresenta. `receive_message` permanece idêntico. Nenhum token de raw/regen foi adicionado à API.

## 25. Raw draft exposure

0/8 streams operacionais finais apresentaram evento intermediário: todos message + DONE. Separadamente, 0/3 cenários de payload inválido/duplicado/string inesperada chegaram ao progressive renderer. Auditorias internas continuam fora do payload público.

## 26. Progressive rendering

**Validated progressive rendering / progressive reveal after validation**, usando `st.write_stream` sobre message.content final. No máximo 50 fragmentos, intervalo de 8 ms: até 0,4 s de pausa adicionada, além do custo de renderização. Não é LLM token streaming e não reduz a espera pelo backend. Erros e calculator são imediatos; normative answer, grounded follow-up, DIRECT e CLARIFICATION compatíveis usam reveal. Teste de texto longo confirma fragmentos completos e quantidade limitada.

## 27. Historical rerun

Histórico é apresentado imediatamente com markdown. Nova resposta é renderizada no mesmo ciclo do submit; não há rerun terminal que reanime tudo. Reruns operacionais finais e controlados não invocaram reveal novamente. A saudação inicial é removida após o primeiro submit.

## 28. Auto-scroll

Três emissões por resposta tipada final: submit, início da resposta e término dos textos/fontes. O usuário já vê sua mensagem durante a espera. Não há trigger em simples rerun ou abertura de referência.

## 29. Scroll implementation

Streamlit instalado 1.40.2: write_stream disponível; não foi encontrada API pública suficiente de scroll no código instalado. Helper isolado via components.v1.html chama scrollIntoView apenas no marcador próprio chat-bottom-anchor, abaixo do container de conversa. Não seleciona classes internas. Cada iframe recebe nonce UUID para evitar reuso do mesmo srcdoc nas interações seguintes. Não há dependência JS adicional nem loops de rerun.

## 30. Scroll limitations

AppTest verifica árvore, marcador, srcdoc distinto e 24/24 emissões; não executa o DOM real. Rolagem efetiva, timing e preferência visual precisam de verificação em navegador. Não se declara scroll visual validado por AppTest. Os artigos não têm evento que force retorno ao input ao abri-los.

## 31. Manual smoke 1

Operacional real via AppTest + AgentClient HTTP/SSE, nova conversa: trancar a pós → ANSWER post, accepted, cinco artigos fechados e progressive_renderer_invoked=1. Não houve verificação visual no navegador.

## 32. Manual smoke 2

Mesma conversa: IRA na pós → ANSWER post, regenerated; novo tema/operação, sem pending de trancamento. O acerto de rota não é avaliação da correção jurídica do texto gerado.

## 33. Manual smoke frequência

Nova conversa: pergunta exata → esclarecimento de nível; `graduação` → ANSWER graduacao, regenerated, artigos 112/115/113/114/118, explicação de frequência mínima. Sem fallback genérico na presença da evidência direta nessa execução final.

## 34. Manual article UX

17/17 referências finais apresentadas em expanders individuais inicialmente fechados, com texto exato. Os testes incluem labels iguais com identidade distinta, duplicata estrutural, legado sem texto e rerun. Abertura manual de apenas um artigo, legibilidade, animação e scroll real não foram verificados no navegador. Uma pergunta longa de graduação ainda retornou CLARIFICATION; outra longa post retornou ERROR router_error. Ambas estão preservadas, sem fabricar resposta.

## 35. Métricas técnicas

Escopo operacional final: oito requests com API pronta, incluindo três suplementares. Tentativas de versões intermediárias e quatro erros durante startup estão preservados separadamente. Não misturar essas taxas com avaliação científica ou acurácia jurídica.

| Métrica | Numerador/denominador | Escopo |
|---|---:|---|
| Article Collapse Rendering Rate | 17/17 | referências finais com expander fechado |
| Evidence Preservation Rate | 17/17 | hashes texto tipado/documento original iguais |
| Direct Evidence Answer Completion Rate | 4/4 | trancamento, frequência grad, art.114 e art.112 autorizado; conclusão substantiva, não correctness |
| Explicit Post Route Rate | 2/3 | inclui erro de Router da pergunta longa suplementar |
| Post Cue False Positive Count | 0/6 | negativos controlados |
| Validated Progressive Rendering Rate | 7/7 | mensagens finais não ERROR; calculator excluído por desenho |
| Raw Draft Exposure Count | 0/8 | streams reais finais; adicionalmente 0/3 inválidos controlados |
| Auto-scroll Trigger Rate | 24/24 | emissões Python; não valida DOM |
| Typed Reference Rendering Rate | 17/17 | referências reais finais |
| Content-to-Reference Parsing Count | 0/17 | auditoria e regressão art.999 |
| Legacy Fallback Count | 0/8 | nenhum desvio ao agente legado |

Separadamente: canonicalização terminal controlada 4/4; conclusão direta com provider fixo 3/3. A pergunta IRA é excluída da conclusão por evidência direta porque os trechos não estabelecem explicitamente a dispensa de IRA. Clarifications/ERROR sem retrieval também não têm evidência final elegível. Aviso para referência antiga sem evidence_text é compatibilidade visual, distinto de fallback para backend legado.

## 36. Resultados negativos

Preservados: frequência inicial fallback por inciso I; IRA intermediário CLARIFICATION; pergunta longa intermediária fallback por §6º; pergunta longa final grad CLARIFICATION; longa post ERROR router_error; quatro requests durante startup sem readiness. Também registrados erros de fixture CorpusChunk/RetrievedChunk, path de teste inexistente, captura Unicode, descoberta do Ruff, expectativas antigas de expander e normalização Markdown nativa. Só falhas de asserção válidas contam como RED de produto. Não se fez nova chamada indefinidamente até obter sucesso nem se descartaram falhas operacionais dos contadores aplicáveis.

## 37. Limitações e revisão

O provider pode ignorar instruções e o Router ainda pode pedir esclarecimento indevido ou falhar; preservar fallback/erro seguro é necessário. A correção remove a causa observada por instrução explícita, sem garantir aceitação universal. Não houve tuning amplo ou alteração de modelo/temperatura/top_k.

Revisão de código identificou dois problemas Important: erro antigo visível depois de retry bem-sucedido e iframe idêntico nas interações seguintes. Ambos têm RED→GREEN e foram corrigidos. O placeholder de erro é limpo no submit; srcdoc recebe nonce. A mudança posterior de instrução V1/article-only foi verificada pela suíte, sem segunda revisão de código.

Minor adiado: a forma interna autorizada de caput pode aparecer como `caput caput` no prompt. Não amplia autorização nem altera referências públicas. Não há validação jurídica de toda prosa livre, de UX em navegador/mobile, carga ou produção.

## 38. Testes focused

69 passed na seleção AppTest + regressões de domínio/answer após correções de revisão. Seleção ampliada com pre-freeze anterior e normative output: 164 passed. Seleção final do arquivo UX, incluindo texto longo: 15 passed. Teste adicional de texto longo integrado na suíte final; execuções e REDs em `execution_summary.json`. Os testes com provider fixo exercitam fronteiras, formato e guards; os smokes reais são a evidência separada de comportamento observado do modelo.

## 39. Full suite

Resultado final consolidado em `execution_summary.json`; inclui UI/AppTest, router, structured output/locator, transport, conversation, agent, retrieval, calculator, runtime, service/client e rag_baseline. Baseline: 1044 passed/12 skipped. Antes da verificação extra de texto longo: 1079 passed/12 skipped/6 warnings. **Entrega final: 1080 passed, 12 skipped, 6 warnings em 85,50 s**, exit 0 (`full_delivery_valid`). A tentativa anterior com expectativa errada sobre indentação Markdown permanece registrada como 1 failed/1079 passed; a expectativa foi corrigida, sem mudança de produção, antes deste GREEN final. Warnings incluem fixtures Pydantic deliberadamente inválidas, AsyncMock legado e depreciações de dependência/TestClient; skips existentes não foram apresentados como testes executados.

## 40. Ruff

Ruff check e Ruff format --check nos dez arquivos de produção/testes alterados. Não se formatou o repositório inteiro.

## 41. Diff check

Git diff --check e diff --cached --check executados. Sem alteração em .gitattributes ou normalização global. Capturas finais no log de execução.

## 42. Preservação

Manifesto SHA256 antes/depois, resumido em `execution_summary.json`: 1364 arquivos iniciais, 1357 idênticos e sete arquivos originais alterados: UI, routing_normalization, normative_output, service, Router V1 prompt e dois testes UI de expectativas. Três novos arquivos de regressão; sete artefatos de entrega.

Router V2, dense/metadata_exact/vector_filtered, Version Filter, Temporal Intent, grounding, contratos Structured Output V2/NormativeToolResult, facade, memória, calculator, runtime, transport/client, registry/default e normative registry permanecem byte a byte idênticos. Exceções explícitas: instruções de geração/regeneração, normalização estreita e prompt V1; schema/algoritmo V1 e guard V2 preservados por AST. `body_instructions` é o único nó alterado em normative_output; o guard não mudou.

**507/507 IDs/documentos/metadados/embeddings float32 idênticos**, SHA256 lógico `ab253a24b756d9f3d3e05aeb49220798b08d947704112327fd894a577bb2b38a`. Sem reindexação. Snapshot após smokes/rebuild. Igualdade lógica não exige igualdade física de housekeeping Chroma.

## 43. Commits locais e operação

- e69e745 — test: reproduce pre-freeze ux and answer reliability defects.
- b8dcffb — fix: guide generation toward structurally authorized citations.
- 4767a21 — fix: recognize terminal postgraduate noun phrases.
- c4012aa — feat: compact evidence and progressively render validated chat.
- 4e12298 — fix: refresh scroll events and clear transient chat errors.
- 01de677 — fix: clarify explicit domain and article citation precedence.
- Commit final de verificações/artefatos informado na entrega, evitando autorreferência.

API http://127.0.0.1:8080 e UI http://127.0.0.1:8501, containers healthy, readiness=true/507; default chatbot_ufpi_v2 preservado. Rebuild/restart somente API/UI alteradas; mesmos env/volumes, SQLite retido e portas loopback. Use **Nova conversa** em teste manual para não reutilizar checkpoints antigos. Não há migração automática de respostas antigas.

## 44. Confirmações

Nenhum deploy externo, publicação de imagem, freeze, avaliação científica, reindexação, re-embedding, alteração de modelo/temperatura/top_k, raw model streaming, parsing textual de references ou novo parser jurídico na UI.
