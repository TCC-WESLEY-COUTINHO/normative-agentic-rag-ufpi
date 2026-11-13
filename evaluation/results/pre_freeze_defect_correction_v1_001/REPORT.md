# Pre-freeze Defect Correction V1

Data: 01/11/2026, America/Sao_Paulo. Comandos em UTC. Regressões pré-freeze usadas para correção; não são TEST científico independente.

**1044 passed / 12 skipped / 5 warnings** na suíte final. **4/4 casos HTTP/UI controlados** e **4/4 smokes operacionais com provider real**, separados. Em cada conjunto final: **20/20 ocorrências de referências com texto de evidência**, uma seção por resposta e **zero seções bibliográficas duplicadas**. **507/507 registros logicamente idênticos**. Default `chatbot_ufpi_v2` preservado. Sistema local deixado em execução.

## 1. Estado inicial

Branch `feat/tcc-ui-integration-v1`, HEAD `729975154f1098447b984219c8abf2fd16bf18c5`, árvore limpa. Status, branch, HEAD, log -15, diff e cached executados antes de alterações, conforme [initial_audit.json](initial_audit.json). Branch `fix/pre-freeze-ui-routing-defects-v1` criada desse HEAD. [preservation_before.json](preservation_before.json) registra 1291 hashes de arquivos iniciais.

## 2. Reprodução da duplicação

[reproduction_before.json](reproduction_before.json) separa raw body, Structured Output, NormativeToolResult.answer, ChatMessage.content, references e AppTest. Raw body: `Conteúdo controlado.`, sem bibliografia. O Structured Output já acrescentava `Fontes:` e duas referências; facade e transporte mantinham esse answer. A UI mostrava esse content e seu expander tipado. São observações controladas do caminho integrado anterior à correção, não uma inferência a partir da tela.

## 3. Causa das fontes duplicadas

`normative_output.compose_answer` acrescentava deterministicamente a lista textual de referências ao status/body. A geração já recebia instrução para não listar fontes. O mesmo composer também era utilizado no fallback. Facade e transporte não introduziam a primeira lista; a UI apresentava a segunda conforme seu contrato anterior.

## 4. Correção na fronteira de output

O composer agora compõe apenas status e body. References permanecem no contrato. A instrução de geração proíbe bibliografia final; o guard V2 existente recusa seção terminal estrutural inequívoca. Uma regeneração e o fallback existentes permanecem. Dez variantes positivas e seis casos de prosa/menção legítima/não terminal são cobertos. Nenhum corte, parsing de fontes ou regex de artigos foi introduzido na UI. Menções necessárias a norma/artigo no corpo continuam válidas.

## 5. Semântica real das referências

`normative_references` projeta os chunks finais elegíveis associados ao grounding **antes** da geração, com ordenação/dedup existentes. Portanto são evidências disponibilizadas ao gerador, não atribuição por afirmação nem prova de que cada trecho foi utilizado. O teste com body sem citações e references não vazias confirma essa independência.

## 6. Label final

**Trechos normativos recuperados** descreve essa semântica sem declarar suporte direto para cada afirmação. Não se usam rótulos que certifiquem validade jurídica ou vigência.

## 7. Detalhes apresentados

Uma seção contém os registros estruturalmente distintos. Cada registro exibe display_text, validated_subdivision quando existente, source, artigo estruturado, papel temporal traduzido e texto normativo. `eligible` vira `Selecionado para esta consulta`; `historical` e `posterior` viram contextos histórico e posterior. Não se exibe chunk_id, score, embedding, prompt, audit ou candidato bruto. A identificação normativa já está em display_text/source; não se acrescentou outra chave técnica visual.

## 8. Evidence text

Adicionado `NormativeReference.evidence_text: StrictStr | None = None`. O texto já existia como `chunk.content` final elegível e é copiado deterministicamente, sem resumo do LLM. O transporte/memória existentes carregam a extensão tipada, inclusive repeat/checkpoint/SSE, sem mudança nesses componentes. Referência antiga sem o campo continua válida e informa `Texto integral indisponível nesta resposta.`. A UI não consulta Chroma. OCR e redação do corpus são preservados. `st.text` recebe o texto original; a representação Streamlit remove whitespace externo. Nos casos controlados, o hash do texto tipado coincide com o documento de origem (20/20).

## 9. Reprodução do domínio pós

Texto exato: `como entrar na pós?`. O replay controlado anterior passa por ConversationFollowUpPolicy → NORMATIVE_RAG → facade → Router V1/core, sem memória/resolver, e registra scope=null, insufficient_scope_signal, CLARIFICATION e pending criado. O primeiro diagnóstico operacional real anterior retornou ANSWER post nesta execução; não se afirma que o modelo anterior sempre falhava. Depois da canonicalização, um smoke real ainda reproduziu a clarification e motivou um trace adicional.

## 10. Entrada do Router

Antes, o Router recebia `como entrar na pós?`. A correção envia somente para routing `como entrar na pós-graduação?`. A pergunta original permanece no request, retrieval/generation e last_normative_question. As quatro entradas finais controladas estão em [provider_observations.json](provider_observations.json); não contêm system prompts. Pergunta e clarification, quando presentes, passam pela mesma normalização estreita.

## 11. Saída anterior observada

O replay preserva a decisão válida null/insufficient_scope_signal. Mais decisivo: [manual_router_diagnostic.json](manual_router_diagnostic.json) registra a entrada **já canônica**, saída válida null/ambiguous_academic_level e pedido do modelo para distinguir pós lato sensu de stricto sensu. O Router substituía essa pergunta pelo texto fixo graduação/pós/ambas. Esse trace guarda apenas pergunta e decisão categórica, sem prompt completo ou credenciais.

## 12. Causa do domínio

Dois pontos estreitos: abreviação explícita sem canonicalização e falta de instrução inequívoca de que pós já resolve o nível, independentemente de subtipo. A distinção lato/stricto não é um quarto nível do schema. Não era falha do parser, retrieval ou contextual resolver. A canonicalização sozinha foi insuficiente na execução real e essa limitação foi preservada, em vez de atribuir sucesso apenas ao replay.

## 13. Correção dos cues

Novo `routing_normalization.routing_question` expande apenas construções standalone `na pós`, `da pós`, `pela pós`, `para a pós`, com término/delimitador controlado. Não transforma qualquer token pós nem fixa domain diretamente. Casos hifenizados temporais não sofrem expansão. Router V1 conserva a decisão final.

## 14. Router V1

Algoritmo, schema, validação e política de falha permanecem idênticos por AST. **O prompt mudou**, somente com duas linhas sobre pós explícita versus lato/stricto e um exemplo JSON. A preferência inicial de preservá-lo integralmente foi revista diante do trace real e do RED específico `router_subtype_red_contract` (1 failed). A seção 51 do pedido autoriza essa exceção. O novo teste é uma regressão do contrato do prompt, não simulação de garantia sobre o LLM. O smoke final real verifica o comportamento observado.

## 15. Router V2

adaptive_router, router_probe e componentes experimentais V2 permanecem byte a byte idênticos. Nenhuma promoção, rank-mass, LLM judge ou tuning V2.

## 16. Casos explícitos post

7/7 formas controladas chegam a ANSWER pos_graduacao sem pending de domínio, incluindo os quatro textos obrigatórios e da/pela/para a pós. ScopeProvider representa decisões controladas para testar integração/canonicalização; essa taxa não estima acurácia de um modelo real.

## 17. Graduação

2/2 textos explícitos obrigatórios preservam ANSWER graduacao e pergunta original enviada ao Router.

## 18. Ambiguidade

3/3 consultas de ingresso sem nível continuam CLARIFICATION controlada; nenhuma expansão ou embedding é realizado nesses casos. Não se força pós pela temática.

## 19. False positives

0/5 falsas expansões nos contraexemplos temporais, incluindo pós-alteração, após a alteração, pós-2025 e prefixos na/da seguidos de forma hifenizada. O teste de ambos conserva `ambas` (1/1).

## 20. Pós após graduação

Regressão de memória: ANSWER grad → pergunta explícita pós produz nova operação, ANSWER post e nova correlation, sem reutilizar a resposta de graduação. Passou no teste integrado controlado e nos smokes finais controlado/real. Tentativas operacionais anteriores com erro/clarification estão preservadas separadamente.

## 21. Pending clarification

`pending_clarification is None` é conferido após os explícitos post e após o caso grad→post. Não foi introduzido patch especulativo para a resposta contraditória `graduação`; a causa da pendência indevida foi tratada. Pendências antigas não foram migradas nem apagadas.

## 22. End-to-end com corpus atual

[local_regression_rows.json](local_regression_rows.json) registra 4/4 requests reais HTTP/SSE pela UI/AgentClient com registry/lifespan/runtime/graph/facade/core/índice reais e provider controlado. A consulta pós limpa e após graduação tem domain=pos_graduacao, strategy=dense_vector, norm IDs finais somente `ufpi-956-2025`, status=ANSWER. IDs elegíveis e referências estão no artefato. Vetor fixo copiado do índice serve apenas ao encadeamento; não mede relevância ou qualidade normativa. Nenhum top_k/model/embedding/temperatura foi alterado.

## 23. Duplicação final

Duplicate Source Section Count = 0/4 respostas controladas finais; separadamente 0/4 smokes operacionais reais finais. Não se usa esse contador para garantir ausência universal de qualquer formato livre de bibliografia.

## 24. UI final

Uma região `Trechos normativos recuperados` por resposta normativa final observada. Um expander externo com os detalhes de cada referência evita expanders aninhados, não suportados pela versão instalada. AppTest cobre rerun e dedup estrutural; referências distintas não são unidas apenas por label.

## 25. Source detail

20/20 ocorrências de referências finais controladas têm texto apresentado e hash de origem conferido; outras 20/20 no smoke real têm texto apresentado igual ao contrato recebido, considerando o whitespace externo do componente. No teste semântico art.999 no content não cria fonte: apenas o artigo tipado aparece nas fontes. Referências legadas sem texto têm aviso explícito.

## 26. Content parsing e fallback legado

Content-to-Reference Parsing Count = 0/20 ocorrências controladas, por auditoria de fonte e regressão art.999. Legacy Fallback Count = 0/4 requests controlados. Todo request ao backend nomeia chatbot_ufpi_integrated_v1. Esses contadores não representam varredura universal de tráfego.

## 27. Focused checks

Focused GREEN anterior: 320 passed/5 warnings, cobrindo UI/client/service/output/transporte/memória/runtime. Após variantes adicionais: 128 passed/1 warning. Após o RED real de subtipo: 41 regressões RAG passaram. As seleções se sobrepõem. O full final contém 34 testes app, 9 client, 24 service, 951 rag_baseline, 23 core, 2 memory e 1 integration; 12 skips existentes. As categorias router, agent, retrieval, temporal, structured, calculator, transport, conversation e runtime estão incluídas. [test_results.json](test_results.json) mantém comandos/cwd/timestamps/exit; [test_counts.json](test_counts.json) deriva contagens do XML final.

## 28. Suíte completa

`full_final_router_contract`: **1044 passed, 12 skipped, 5 warnings in 96.47s (0:01:36)**, exit 0, Windows/Python3.11.15. A suíte final foi repetida porque o prompt mudou depois do full anterior (1043). Warnings preservados: fixture Pydantic deliberadamente inválida, AsyncMock legado, depreciação de dependência e timeout TestClient. Sem API real necessária nos testes; provider real usado somente nos smokes operacionais separados. Docker opt-in legado continua skipped, sem alegar nova full Linux nesta etapa.

## 29. Ruff

Ruff check e format --check de todos os arquivos produtivos/testes alterados e sete scripts técnicos de evidência aprovados, 18 arquivos. A captura final é registrada em verification.json. Não houve formatação global.

## 30. Diff check

O primeiro diff --check staged sinalizou padding em quatro linhas de falha do JUnit; captura preservada em diff_staged_initial.json. Atributo XML limitado à pasta nova reconhece esse whitespace de captura, sem editar o XML. Diff --check unstaged e staged finais conferidos. Atributos preservam bytes CRLF das capturas, sem normalizar arquivos anteriores. Staged manifest e auditoria de blobs são entregues junto às evidências.

## 31. Preservação

[preservation.json](preservation.json): 1291 arquivos iniciais; **1283 idênticos e oito alterações existentes autorizadas**: agentic.py, normative_output.py, output_contracts.py, router.py, streamlit_app.py e três testes de expectativas/fixtures. Novos arquivos: normalizador, dois testes e evidências. Mudanças de produto ficam no output/guard, referência opcional, renderer e fronteira de routing/prompt. Retrieval dense/metadata_exact/vector_filtered, Temporal Intent, VersionFilter, grounding, serviço de geração/retry, NormativeToolResult/facade, memória/resolver/transformer, calculator, runtime, registry/default, transporte/client/schema, assets, pyproject/lock, Docker/Compose e resultados anteriores permanecem idênticos. AST confere as partes preservadas dentro dos arquivos alterados.

**507/507 IDs/documentos/metadados/embeddings float32 idênticos**, SHA256 `ab253a24b756d9f3d3e05aeb49220798b08d947704112327fd894a577bb2b38a`. Snapshot final realizado após smokes. Nenhuma indexação, metadata update ou re-embedding. Igualdade lógica não promete igualdade física de housekeeping/ownership Chroma.

## 32. Resultados negativos

[negative_results.json](negative_results.json) mantém todos os REDs e falhas de preparação, expectativas antigas, provider real, acentuação e cleanup. O replay inicial não substitui evidência real; a primeira chamada real antiga foi bem sucedida. Depois, canonicalização isolada ainda falhou; o trace de subtipo comprovou necessidade do prompt. `manual_after.json`, `manual_followup.json` e `manual_final.json` são tentativas anteriores, não o denominador final. Followup com literais corrompidos por pipe não conta como teste da pergunta exata. `router_subtype_red.log` e `router_subtype_green.log` registram erro de comando/path, não RED/GREEN válido. A execução autoritativa está em [manual_after_router_prompt.json](manual_after_router_prompt.json).

## 33. Limitações e operação local

Não há avaliação jurídica/científica, freeze, tuning amplo, autenticação, carga, verificação em navegador/mobile ou prontidão de produção. AppTest inspeciona a árvore real de componentes; não substitui revisão visual. O guard é limitado a seções terminais reconhecidas; o modelo/provedor ainda pode falhar. O prompt não garante comportamento determinístico futuro. Texto antigo persistido pode conter Fontes e não ter evidence_text; use **Nova conversa** para retestar. Não se alterou autoridade histórica. Um futuro provider no grounded transformer exigirá revisar sua própria política bibliográfica; o runtime atual usa fallback baseado na resposta original, sem esse provider.

API `http://127.0.0.1:8080`, documentação `http://127.0.0.1:8080/docs`, interface `http://127.0.0.1:8501`. Ambos containers locais healthy, /health ok, readiness ready=true/507 e UI health ok, conforme [local_operational_status.json](local_operational_status.json). Default v2 e integrado experimental/non-default preservados. Serviços foram deixados em execução. Rebuild local de backend/UI não publica imagem nem inicia produção. Erros de upstream foram preservados, não mascarados por fallback legado.

## 34. Commits

- `136f2b0` — test: reproduce pre-freeze routing and source defects.
- `f4bd36c` — fix: make normative sources singular and inspectable.
- `6b790c4` — fix: normalize explicit postgraduate domain cues.
- `c24020bb618a2fde5d493b107e0b31899dfb8014` — fix: keep postgraduate subtype out of domain clarification.
- Evidências: commit final de artefatos, sem autorreferência.

## 35. Confirmações

Nenhum deploy, publicação de imagem, freeze científico/dataset/protocolo, final evaluation, reindexação, atualização de metadata, re-embedding, promoção/tuning V2, regex/parsing de fontes na UI ou API real necessária aos testes. Os requests reais desta etapa são diagnóstico/smoke operacional separado, autorizado, sem ajuste de qualidade das respostas. [decision_log.jsonl](decision_log.jsonl) contém decisões técnicas públicas.
