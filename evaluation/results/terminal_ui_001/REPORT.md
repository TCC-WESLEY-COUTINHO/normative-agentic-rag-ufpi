# Exploração — terminal original e seleção explícita de escopo

Foram executadas **80 consultas pelo terminal Rich/API**, com as mesmas duas listas de 20 perguntas, e três consultas interativas adicionais. Nos lotes, houve **73 respostas recebidas e sete falhas operacionais**, preservadas. Não há notas humanas de correção normativa preenchidas.

Este relatório substitui a interpretação operacional das rodadas `cli_001/002/003`, não seus dados históricos. `pilot_003` permanece intacto: usou outro runner e índices físicos isolados/conjunto. Não reatribuir seus resultados à nova interface.

## O que foi corrigido e por quê

A interface reutilizada é `rag_baseline.demo`, da branch `demo/terminal-ui`, referência `3932f45`. Mantém Rich, `/health`, `/query`, referências recuperadas e modo detalhado. Antes da pergunta interativa, o operador escolhe **graduação, pós ou ambas**. `--setor` permite a mesma escolha explícita antes de uma consulta única ou lote; com esse argumento, o escopo fica fixo e é exibido antes das perguntas.

O escopo afeta **somente o filtro de recuperação**. Não é contexto pessoal sobre o curso do aluno, não é anexado à pergunta/prompt e não é inferido de palavras da consulta. As opções graduação/pós aplicam igualdade ao metadado `sector`; ambas deixa os dois corpora elegíveis e retorna top-5 global, sem cotas por setor. Ausência de metadado não vira graduação. A fonte distingue artigos com a mesma numeração em normas diferentes.

O CLI alternativo anterior acrescentou inferência de setor, esclarecimento determinístico e/ou reescrita de respostas. Essas intervenções iam além de recuperação e confundiam a comparação. Foram retiradas deste fluxo; `rag_baseline.chat` agora é apenas alias da mesma interface Rich. O módulo de heurísticas permanece somente para reproduzir a auditoria histórica, não é chamado pela API/terminal atual. **Roteamento automático será avaliado posteriormente na implementação dos agentes.**

São decisões de engenharia e controles acordados para esta exploração, não escolhas cuja superioridade científica esteja demonstrada.

## Configuração e delineamento

Código executado: `5f281a15eab549d15cea429498bd1a4322c15a3f`. O [manifesto](manifest.json) congela código, entradas, configuração e proveniência da UI antes da primeira pergunta. Coleção `ufpi_duas_regulacoes_setor`, **438 IDs distintos**, sendo 376 da graduação e 62 da pós. O índice existente foi reutilizado, sem apagar coleções anteriores.

Nas três seleções, a API injeta exatamente o prompt neutro já usado na V2, SHA-256 `dbe2b931d08dfa564bab82e8528b3dbaf5e15c1a737b09087fc61a40496fde4d`. Modelos configurados: `openai/text-embedding-3-small` e `qwen/qwen3-30b-a3b-instruct-2507`; temperatura zero, máximo 800 tokens e top-k=5. O padrão histórico da biblioteca não é o prompt utilizado pela API nesta execução. Não foram ajustadas instruções após inspeção das novas respostas.

Cada requisição bem-sucedida usa uma chamada de geração, sem correção automática de conteúdo. São transmitidos pergunta original e trechos com fonte, setor e hierarquia. O parser lê apenas as perguntas numeradas, sem enviar respostas, rótulos ou evidências gold. A apresentação da pós preserva literalmente as 20 perguntas V2, na estrutura do gabarito original da graduação; não é novo dataset independente.

Ordem predefinida: pós filtrada + graduação filtrada, análise primária salva, depois as mesmas duas listas com ambas as normas. No máximo dois clientes de lote simultâneos por fase. A [análise primária](PRIMARY_ANALYSIS.md) e seu [resumo](primary_summary.json) foram preservados; a cronologia está em [execution.json](execution.json). Não houve corte mínimo, exclusão de perguntas ou repetição seletiva de falhas.

Aqui, as condições filtradas usam **o mesmo índice conjunto**, não índices físicos isolados. As consultas são embeddadas novamente pela API a cada requisição; não se afirma identidade bit a bit desses vetores. Logo, não é réplica exata do piloto 003. O escopo correto dos lotes filtrados é fornecido pelo operador por construção, não descoberto por um roteador. O limite dez da ferramenta de metadados Supabase permanece inalterado, mas essa ferramenta e o loop agêntico não são executados nesta exploração.

## Recuperação observada

Qrels V2 preexistentes por par `(norma, artigo)`, incluindo alternativas previamente anotadas. As ambiguidades não entram no Recall normativo. Métricas abaixo são condicionais às referências recebidas: uma falha de transporte sem trechos tem recuperação **não observada**, não Recall zero.

| Dataset | Escopo escolhido | Registros | Falhas | Respondíveis com evidência / previstas | Recall@5 | Cobertura completa@5 | Outra norma@5 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pós | Pós | 20 | 1 | 15 / 16 | 1,0000 | 1,0000 | 0,0000 |
| Graduação | Graduação | 20 | 2 | 5 / 6 | 0,9000 | 0,8000 | 0,0000 |
| Pós | Ambas | 20 | 3 | 14 / 16 | 0,9643 | 0,9286 | 0,2714 |
| Graduação | Ambas | 20 | 1 | 5 / 6 | 0,9000 | 0,8000 | 0,0000 |

Hit@5 é 1,0000 nas quatro linhas: cada respondível observada recebeu ao menos um artigo gold, não necessariamente todos. MRR@5: 0,9667 e 0,8631 na pós filtrada/ambas; 1,0000 nas duas seleções da graduação. nDCG@5: 0,9456 e 0,8674 na pós; 0,8453 nas duas seleções da graduação. Recall@1/3 e métricas por item estão em [summary.json](summary.json) e [row_metrics.json](row_metrics.json).

Não subtrair diretamente médias com denominadores diferentes como se fossem os mesmos pares. No [suplemento descritivo de pares observados](paired_observed_summary.json), há 13 dos 16 pares respondíveis da pós com referências em ambas as seleções: Recall@5 de 1,0000 para 0,9615, delta −3,85 pontos percentuais. O único delta negativo observado nesse subconjunto é `POS2-011`, de 1,0 para 0,5. Na graduação, cinco dos seis pares são observáveis nas duas seleções, sem diferença de Recall@5. Os quatro pares incompletos permanecem no total original, sem imputação. A ausência de observação pode não ser aleatória; esse suplemento não é estimador causal ou teste confirmatório.

O indicador de outra norma mede composição do contexto, não erro jurídico por si só: uma regra comum pode admitir evidência de qualquer uma das normas. Os filtros não apresentaram referência observada fora do setor selecionado. Em ambas, mistura de setores é permitida, mas não obrigatória.

## Falhas e qualidade de resposta

As sete falhas foram registradas pelo cliente como `Não foi possível conectar à API.`:

| Item | Escopo | Ação gold |
| --- | --- | --- |
| POS2-002 | Pós | Responder |
| GRAD2-003 | Graduação | Responder |
| GRAD2-012 | Graduação | Esclarecer |
| POS2-010 | Ambas | Responder |
| POS2-015 | Ambas | Responder |
| POS2-020 | Ambas | Esclarecer |
| GRAD2-003 | Ambas | Responder |

Os quatro lotes retornaram código 1, corretamente sinalizando falhas mesmo com 20 registros completos cada. A API permaneceu disponível. A mensagem herdada da UI agrupa exceções de transporte e não distingue timeout de falha de conexão; não concluir que o modelo necessariamente deixou de gerar ou que a recuperação foi zero. O cliente usa timeout de 30 segundos, como na UI original; durações individuais estão nos JSONLs. Não se mudou esse parâmetro no meio da rodada. Requisições podem continuar no servidor depois da desconexão do cliente; concorrência efetiva do provedor não foi medida. Não apresentar estas latências como benchmark de desempenho controlado.

Há sinais de problemas de conteúdo apesar de recuperação completa: a primeira resposta da pós converte 60 horas em uma contagem de faltas sem duração da aula informada. Esse texto foi preservado, sem aplicar a antiga reescrita. Isso demanda revisão de conteúdo; não foi convertido automaticamente em nota 0/1/2.

## Conferência interativa

Após os lotes, a mesma pergunta adicional, `Posso cancelar uma disciplina?`, foi digitada três vezes, sempre depois de escolher o escopo no menu. [interactive.jsonl](interactive.jsonl) contém três respostas, sem erro, e pergunta idêntica. Graduação recuperou apenas graduação; pós recuperou apenas pós; ambas recuperou artigos dos dois setores. O encerramento pelo menu retornou código zero. Esses três registros não entram nas métricas dos 80 itens.

Na seleção ambas, o art.37 da pós foi recuperado em primeiro lugar e o art.229 da graduação em segundo. A resposta, porém, adotou as regras da graduação sem pedir o nível do curso. É observação qualitativa desta conversa, não nova pergunta gold rotulada após o resultado nem taxa geral de erro. Demonstra por que conformidade do filtro e presença de evidência não substituem avaliação da interpretação e da resposta. Não demonstra que agentes resolverão esse comportamento.

## Auditoria, revisão e alcance

O comando `uv run --no-sync python -m rag_baseline.audit_terminal ../evaluation/results/terminal_ui_001` validou as 80 perguntas e sua ordem, seleção declarada, textos/fontes/setores das referências contra os corpora, ranking, ausência de duplicatas e top-k. Métricas foram calculadas com os mesmos qrels/funções da V2; hashes das saídas estão no resumo. Os hashes das entradas/código e a igualdade do resumo primário com os lotes correspondentes também foram conferidos, sem modificar os arquivos históricos.

A [verificação técnica](VERIFICATION.md) registra a suíte final, avisos e falhas anteriores. A checagem da UI bloqueia respostas com referências fora da seleção explícita; esse desvio é violação fatal de protocolo na auditoria, diferente de indisponibilidade operacional sem trechos. Arquivos brutos são preservados em ambos os casos.

As notas 0/1/2 continuam nulas. Aplicar a rubrica já aprovada por revisão de conteúdo, preferencialmente com dois anotadores independentes e adjudicação: erro/não resposta; incompletude ou falta de evidência; resposta correta, completa e fundamentada. As 36 saídas previstas das 18 perguntas ambíguas devem ser avaliadas separadamente quanto a esclarecimento, incluindo suas duas falhas operacionais. Não deduzir nota 2 do Recall ou chamar referências recuperadas de citações efetivamente utilizadas.

Separar recuperação, fidelidade e geração é motivado por [RAGAs (Es et al., 2024)](https://aclanthology.org/2024.eacl-demo.16/); distinguir correção e suporte das citações por [ALCE (Gao et al., 2023)](https://aclanthology.org/2023.emnlp-main.398/). A interpretação das métricas de ranking segue [Manning et al.](https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html). Não executamos esses frameworks nem transferimos seus resultados para este corpus. A rubrica e o delineamento local não são automaticamente validados por citá-los.

Conclusão limitada: o terminal solicitado está integrado à seleção explícita e os filtros/metadados funcionaram nas referências observadas. A recuperação foi alta, mas houve falhas de transporte e comportamentos de resposta que exigem revisão. A exploração não prova insuficiência geral de RAG, superioridade de agentes ou acurácia normativa. Seus limites incluem gold candidato de desenvolvimento, amostra pequena/intencional, evidências incompletas, uma repetição, chamadas em momentos distintos, vetores de consulta recalculados, busca aproximada, ausência de observação em falhas e inexistência de ablação com/sem metadados.

## Reproduzir sem sobrescrever

No código congelado, a partir de `code/`, iniciar a API e abrir a UI em outro terminal:

```powershell
uv sync --frozen
uv run python -m rag_baseline.index --profile duas-regulacoes
uv run uvicorn rag_baseline.api:app --host 127.0.0.1 --port 8080
# Outro terminal, também em code/:
uv run python -m rag_baseline.demo --verbose
```

Para repetir os lotes, usar arquivos novos e a mesma API:

```powershell
uv run python -m rag_baseline.demo --setor pos_graduacao --questions-file ../data/questoes_para_avaliar_o_agente_pos_graduacao.md --output nova_pos_filtrada.jsonl
uv run python -m rag_baseline.demo --setor graduacao --questions-file ../data/questoes_para_avaliar_o_agente.md --output nova_grad_filtrada.jsonl
# Registrar análise primária antes de prosseguir.
uv run python -m rag_baseline.demo --setor ambos --questions-file ../data/questoes_para_avaliar_o_agente_pos_graduacao.md --output nova_pos_ambas.jsonl
uv run python -m rag_baseline.demo --setor ambos --questions-file ../data/questoes_para_avaliar_o_agente.md --output nova_grad_ambas.jsonl
```

A execução registrada usou a porta local 8092 para não substituir serviços existentes; isso não alterou a geração. Segredos permanecem exclusivamente no ambiente local. Notas de desenvolvimento/autoria e testes novos ficam locais/ignorados; configuração, dados brutos, decisões técnicas, auditoria e resultados são versionáveis.
