# Normative Tool Result e Facade V1 — fronteira de integração

Data: 31/10/2026. Verificação de engenharia local, sem chamadas reais a modelos ou nova avaliação de qualidade de resposta.

Foram implementados **NormativeToolResult V1** e **NormativeRagFacade V1**, em dois módulos novos. A facade usa o serviço agentic não interativo, fixa Router V1 e chama o núcleo com Version Filter habilitado e escopo automático. O contrato transporta a resposta final sem reescrita, referências oficiais e proveniência estruturada; separa serialização pública de persistência privada.

Resultado de verificação: **79 testes novos aprovados**, **550 passed / 12 skipped** na suíte completa e quatro probes offline sobre o índice real local. Os **555 arquivos anteriores e 507 registros permaneceram idênticos**. Isso verifica contratos e wiring nos cenários testados; não demonstra melhora de precisão, confiabilidade ou qualidade jurídica. Nenhuma tool foi criada/registrada no agente.

## 1. Objetivo

Estabilizar a fronteira núcleo normativo → resultado estruturado → futura tool, conforme opção B da auditoria anterior. Esta etapa não conecta conversa, memória, service, client ou UI e não acrescenta metadata search.

## 2. Estado inicial

Branch verificada: `audit/agentic-conversational-integration-v1`. HEAD: `61d2bc0e3db4b967aafb0f8127da9c109f0c2f06`. Árvore limpa; a auditoria anterior estava commitada. Status, branch, HEAD, log de 15 commits, diff, cached diff e stat estão em [initial_audit.json](initial_audit.json).

Branch de trabalho criada exatamente desse HEAD: `feat/normative-tool-facade-v1`. Não houve pull, push, merge, rebase, reset ou limpeza destrutiva.

## 3. Baseline congelado

Permanece selecionado Structured Normative Output V2: Router V1 → Temporal Intent → dense retrieval → Version Filter → grounding → geração/guard/composição V2. Temporal Intent antecede retrieval no fluxo real, para determinar exclusões.

Os resultados anteriores permanecem os mesmos: 0/213 violações nas referências oficiais, conclusão 42/44, fallback 2/44 e exposição cronológica ampla final 7/44. São números preservados do experimento anterior, não resultados novos. As limitações, falsos positivos e ambiguidades V2 não foram corrigidos nesta etapa. Não há V3 nem tuning/reexecução dos 44 casos.

## 4. Findings relevantes da auditoria

A infraestrutura legada perde dados estruturados ao projetar o núcleo para ChatMessage; artifact não é preservado pelo transporte, e reescrita livre pode substituir a saída validada. O núcleo expõe modos manuais e filtro opcional fora desta facade.

Esta implementação resolve somente o contrato e o caminho estreito de chamada. Os bloqueadores de ownership, transporte, streaming, memória, empacotamento e emissão final da auditoria continuam fora do escopo.

## 5. Contratos existentes

`AgenticRagService.query(self, question, *, clarification=None, use_version_filter=True, scope=None)` retorna `QueryResult`. Seu construtor compila o grafo com `interactive=False` por padrão. `QueryRequest` da API existente também contém sector e version_filter; ele não é reutilizado como entrada da facade.

`QueryResult` contém answer, references de evidência, modelos, route, needs_clarification, clarification_question, selected_scope, version_filter, routing, error e normative_output. response_kind, generation_attempts e output_audit são campos internos excluídos do dump padrão.

[existing_contracts.json](existing_contracts.json) registra assinaturas reais, campos, exclusões, schemas de referências e o mapeamento. Nenhum schema anterior foi alterado.

## 6. NormativeToolResult V1

Implementação: [tool_contracts.py](../../../code/src/rag_baseline/tool_contracts.py). Segue Pydantic com modelos frozen e extra=forbid. A configuração frozen é superficial; listas/dicionários não representam imutabilidade profunda. A facade copia os dados para evitar aliasing com o resultado do núcleo.

| Campo | Origem/responsabilidade |
|---|---|
| contract_version, core_version | identificadores obrigatórios e independentes |
| status | ANSWER, CLARIFICATION ou ERROR |
| answer | resposta final exata, somente em ANSWER |
| references | NormativeReference oficial, sem conteúdo integral do chunk |
| temporal_provenance | TemporalGroundingContext estruturado |
| temporal_status_text, allowed_temporal_facts | framing/fatos já produzidos pelo núcleo |
| core_status | accepted, regenerated ou fallback do V2 |
| domain | graduacao, pos_graduacao, ambas ou null |
| retrieval_strategy | discriminante da estratégia; facade atual emite dense_vector |
| needs_clarification, clarification_question | continuação a cargo da futura camada pai |
| correlation_id | UUID da operação normativa |
| error_code, safe_message | erro categórico e mensagem fixa segura |
| internal_audit | privado, excluído do dump público |

ANSWER exige resposta não vazia, referências, proveniência com estados de evidência, framing, fatos, domínio e status V2. CLARIFICATION e ERROR não podem carregar answer/referências/proveniência normativas. Versões, domínios, estados e combinações inválidas falham explicitamente na validação.

## 7. Serialização pública e persistência

`model_dump()` / `model_dump_json()` são públicos e excluem internal_audit, inclusive quando solicitado via include. Para schema público, usar `model_json_schema(mode="serialization")`. O schema de validação também descreve entradas internas e não deve virar prompt do agente.

`to_persistence()` devolve envelope privado com persistence_version, result e internal_audit; `from_persistence()` valida e reconstrói o resultado. O envelope não deve ser enviado ao LLM ou usado como resposta HTTP pública. Não se deve depender do checkpoint direto do modelo público para guardar auditoria: a camada futura deve persistir explicitamente o envelope.

Roundtrips JSON e JsonPlusSerializer do envelope cobrem ANSWER, CLARIFICATION e ERROR, preservando referências, proveniência, correlação e auditoria. Formatos inválidos/versões incompatíveis falham. Nenhum backend de memória foi integrado.

## 8. Referências oficiais

Fonte exclusiva: `QueryResult.normative_output.references`. O tipo reutilizado é NormativeReference, com identidade, artigo, display e papel temporal. `QueryResult.references` usa Reference e inclui content/distance, representando evidência legada; foi deliberadamente omitido do novo contrato público e de persistência.

O teste compara os dois schemas e verifica que conteúdo de chunk não migra para as referências oficiais. A facade não reconstrói referências, aumenta granularidade ou cria fontes a partir de relações.

## 9. Proveniência temporal

Vem exclusivamente de `normative_output.temporal_provenance`, validada como TemporalGroundingContext. Preserva intenção, contexto solicitado, estados, papéis, relações conhecidas e restrições do grounding. Texto de mensagem/answer não fabrica proveniência.

Os dicionários legados de requested_time_context e relation_source recebem validação de chaves correspondente à projeção real: campos de TemporalIntent sem mode; source/article para a prova da relação. Chaves adicionais de prompt são rejeitadas, sem remoção silenciosa. Não há inferência normativa nova.

## 10. Status

| Transporte | Significado |
|---|---|
| ANSWER | saída final estruturada do núcleo, preservada exatamente |
| CLARIFICATION | domínio não resolvido, pergunta ao pai, sem resposta normativa |
| ERROR | consulta não concluída pela fronteira, com código e mensagem segura |

O status V2 é separado. Um fallback conservador produzido e composto pelo V2 continua ANSWER com core_status=fallback; isso não afirma conclusão substantiva. Falha de provider ou falta de contexto elegível não vira resposta normativa.

## 11. Correlação

Sem correlation_id, a facade cria um UUID por invocação. UUID fornecido é preservado. Identificador inválido produz invalid_request com nova identidade válida; não é tratado como thread_id. Se outro campo da consulta for inválido e a correlação for válida, ela permanece.

A futura camada pai conserva a pergunta original e reutiliza a correlação na chamada com clarification. Não há histórico de conversa dentro do resultado e não há armazenamento de pendência nesta etapa.

## 12. Versões

contract_version obrigatório: `1`. core_version obrigatório: `structured_output_v2`. O envelope de persistência tem persistence_version `1`. SHA Git e hashes de arquivos ficam nos artefatos técnicos, não substituem os identificadores públicos estáveis.

## 13. Facade

Implementação: [tool_facade.py](../../../code/src/rag_baseline/tool_facade.py).

```python
NormativeRagFacade(service, router, version_filter)
await facade.query(
    question: str,
    clarification: str | None = None,
    correlation_id: str | UUID | None = None,
) -> NormativeToolResult
```

O construtor recebe dependências de aplicação confiáveis e cria um AgenticRagService próprio com routing_mode="intent_v1". Não aceita grafo arbitrário nem configuração de execução por consulta. O corpo da query delega uma vez ao serviço agentic; não duplica router, retrieval, filtro, grounding, prompt ou guard.

## 14. Domain Router automático

A chamada é sempre `core.query(question, clarification=..., use_version_filter=True, scope=None)`. O teste unitário verifica os argumentos; a equivalência e os probes executam o NormativeRouter real com JSON de provider controlado. Router V1 decide domínio; model/tool calling externo não o substitui.

## 15. Version Filter obrigatório

O filtro é habilitado internamente sem parâmetro público para desligá-lo. Para ANSWER, a facade também exige version_filter.enabled=True no retorno. A passagem pelo filtro e grounding é exercitada pelo grafo existente nos testes/probes. Não foi alterada a política de seleção temporal.

## 16. Manual scope não exposto

A assinatura não aceita sector, scope ou manual_scope. Também rejeita version_filter/use_version_filter, top_k, model, temperature, retrieval_backend, skip_grounding, skip_guard, raw_retrieval e raw_search. São rejeições TypeError verificadas na assinatura real, antes de chamada ao núcleo. Modos manuais continuam intactos fora desta facade.

## 17. Dense retrieval preservado

O caminho continua sendo `RagService.retrieve` e `ChromaVectorStore.query`. Top_k, modelo, filtros, exclusões, embeddings, chunking e coleção não foram modificados. Não foi necessária extensão no núcleo congelado.

retrieval_strategy admite dense_vector, metadata_exact e vector_filtered como valores de contrato, mas esta facade só emite dense_vector e não possui seleção/engine de estratégias. A interface externa não oferece backend ou estratégia ao caller.

## 18. Mapeamento de erros

OpenRouterError e subclasses → provider_error; CorpusNotIndexedError e subclasses → index_unavailable; ValueError de chamada → invalid_request. Códigos conhecidos retornados pelo núcleo também são mapeados, incluindo generation_error e erros do router. Erros desconhecidos → internal_error; nunca se devolve str(exception), traceback, corpo de provider ou path.

Retorno gerado sem normativa estruturada, filtro/rota válidos ou audit V2 coerente → invalid_core_result. Falta de contexto com zero tentativas → no_eligible_context. Audit malformado é rejeitado com diagnóstico de tipo, sem propagar ValidationError. CancelledError permanece cancelamento e não vira ERROR.

## 19. Esclarecimento

CLARIFICATION exige resultado coerente de esclarecimento, zero tentativas e ausência de geração/saída normativa. Preserva a pergunta de esclarecimento, domínio null e correlação; answer é null. Não há interrupt, suspensão ou subgrafo interno.

Quando o núcleo encerra esclarecimento não resolvido sem nova pergunta, a facade retorna clarification_unresolved ERROR. Quando o erro é de router/provider, retorna ERROR antes de tratar o pedido como pergunta normal ao usuário.

## 20. Testes de bypass e passagem pelo V2

Os testes rejeitam os 13 parâmetros indevidos e verificam que o núcleo não foi chamado nesses casos. Para ANSWER, exigem saída estruturada, rota coerente com selected_scope, filtro habilitado, audit guard_version=2, final_answer idêntico ao answer e ação do guard correspondente ao core_status.

Testes negativos cobrem ausência de saída/audit, versão antiga do audit, filtro desabilitado, rota manual, domínio divergente, raw no lugar da resposta final e proveniência inválida. Não existe caminho público de raw search ou chamada direta a generate nesta facade.

## 21. Equivalência

Com provider fake e evidência controlada, a mesma pergunta passa diretamente por AgenticRagService.query e pela facade: answer final, referências oficiais e proveniência são equivalentes após mapeamento. O teste também observa router, embedding e seção de grounding no prompt controlado, sem chamada remota.

Outro cenário força reincidência de locator inválido: o guard V2 faz duas tentativas, produz fallback e a facade preserva essa resposta final. O raw continua apenas no audit privado. Não há reescrita ou segunda síntese no adapter.

## 22. Probes locais

[local_probes.py](local_probes.py) é reproduzível e foi repetido após as mudanças finais. [local_probes.json](local_probes.json) contém os quatro resultados e recibos de wiring.

| Escopo controlado | Resultado | Acesso ao índice/geração |
|---|---|---|
| graduacao | ANSWER | dense real local + geração fake |
| pos_graduacao | ANSWER | dense real local + geração fake |
| ambas | ANSWER | dense real local sem filtro único de setor + geração fake |
| ambíguo | CLARIFICATION | sem retrieval, embedding ou geração |

O embedding foi replay de vetor 1536 já armazenado; não é embedding semântico da pergunta. As decisões de escopo vieram de JSON controlado consumido pelo router real. Geração e embedding não usaram provider real; HTTP de provider foi bloqueado no harness. Esses probes não avaliam relevância, cobertura de ambos os domínios ou correção jurídica. Snapshot antes/depois idêntico.

## 23. Futura metadata strategy

A mesma estrutura externa admite outro valor de retrieval_strategy sem alterar NormativeToolResult. Localização estrutural deve continuar retornando evidências ao pipeline temporal obrigatório. Nenhum lookup, filtro norma/artigo, adaptação Supabase, metadata nova ou reindexação foi implementado.

## 24. Futura tool do agente

A etapa posterior poderá envolver query em uma tool com entrada estreita e usar somente o dump público como resultado. A camada pai deverá preservar o envelope privado no local apropriado e entregar answer autoritativo sem síntese normativa livre posterior. Este contrato descreve essa obrigação; não impõe sozinho a emissão do agente superior.

Não há @tool, StructuredTool, BaseTool, ToolNode registration ou bind_tools novos. Agents, registry/default, service, ChatMessage, client, Streamlit, SSE, history e feedback permanecem idênticos.

## 25. Decisões e execução

[decision_log.jsonl](decision_log.jsonl) contém **12 decisões públicas**, com problema, evidência, alternativas, decisão, razão, status, testes e arquivos relacionados.

[execution_log.jsonl](execution_log.jsonl) contém **22 eventos observáveis** de auditoria, RED/GREEN, verificações, probes e commits. [tdd_cycles.json](tdd_cycles.json) distingue testes RED de verificações de comportamento já implementado.

O primeiro RED marcou 70 erros de setup pela ausência dos módulos; a sinalização foi corrigida antes da produção e a execução verificada teve 70 falhas esperadas. Duas fixtures foram alinhadas aos tipos reais: status desconhecida e projeção de TemporalIntent. Ciclos adicionais tiveram 2 falhas/1 sucesso e 3 falhas, depois GREEN. Três testes de serializer foram acrescentados como caracterização de comportamento já verde, totalizando 79. O launcher python -m ruff falhou pelo path relocacionado; o executável Ruff existente foi usado sem instalar dependências.

## 26. Limitações

Os testes não invocam LLMs reais e os probes não medem qualidade de busca/resposta. Não há estudo com usuário, avaliação jurídica independente ou novo experimento científico. A revisão foi independente de código/contratos, não de direito.

Referências/proveniência coerentes continuam dependendo dos builders determinísticos congelados; não se implementou verificador jurídico alternativo. A validação estrutural não prova a correção de todo conteúdo em strings. Dependências Python são wiring confiável de aplicação; a facade não é sandbox contra código Python malicioso. A correlação não é autenticação ou autorização por usuário.

Persistência exige o envelope explícito; não foi conectada ao saver do serviço. Controle de emissão, follow-up, ownership, transporte, frontend e deploy continuam pendentes de fases posteriores. O V2 mantém as limitações documentadas, incluindo datas documentais sem suporte estruturado.

## 27. Preservação

[preservation_before.json](preservation_before.json) e [preservation.json](preservation.json) comparam **555 arquivos previamente versionados**, todos idênticos. Isso inclui Router V1/V2, retrieval, Temporal Intent, Version Filter, grounding, Structured Output V1/V2, registry, corpora, datasets, auditoria anterior e experimentos anteriores.

Os **507 registros**, IDs, documentos, metadados e embeddings float32 são idênticos. Snapshot SHA-256: `ab253a24b756d9f3d3e05aeb49220798b08d947704112327fd894a577bb2b38a`. Foram acrescentados somente dois módulos novos, três arquivos de teste e estes artefatos. A regra .gitattributes vale somente nesta pasta de resultados; nenhuma configuração raiz foi alterada.

## 28. Verificações finais

| Seleção | Resultado |
|---|---:|
| Novos focused | 79 passed |
| Structured Output V1/V2 | 122 passed |
| Cinco arquivos temporais | 93 passed |
| rag_baseline | 487 passed, 10 skipped |
| Legacy core/service/client/app/integration | 63 passed, 2 skipped |
| Suíte completa | 550 passed, 12 skipped |
| Ruff check / format-check, seis arquivos novos | aprovados |
| git diff --check | exit 0 |

As seleções se sobrepõem e não devem ser somadas. Os quatro warnings completos são legados: dois Pydantic de dependências, um AsyncMock no client e um timeout do Starlette TestClient. Não houve falha final nem correção de teste anterior. AppTest é harness isolado, sem frontend ao vivo; testes Docker opt-in foram skipped.

[test_results.json](test_results.json) contém comandos, timestamps, contagens e tempos; stdout técnico está nos arquivos pytest correspondentes. [verification.json](verification.json), [manifest.json](manifest.json) e [ARTIFACTS.json](ARTIFACTS.json) registram verificações, escopo e hashes. O manifesto de hashes exclui a si próprio.

## 29. Commits e limite da entrega

Commits locais:

1. `986f421` — `test: define normative tool contract boundaries` (RED).
2. `d3c5cc8ae9c1925c9c6cd75ee6da70ce88e4051b` — `feat: add normative rag facade` (implementação e regressões).
3. Commit de evidências — `test: verify normative facade integration contracts`; o SHA não consta aqui, pois não pode integrar seu próprio conteúdo.

Sem push, merge, rebase, mudança de default, tool registrada, metadata search, calculator nova, memória conversacional, frontend ou deploy. Nenhuma integração com a infraestrutura legada foi iniciada. A entrega termina nesta fronteira; a próxima etapa depende da revisão do contrato e da facade.
