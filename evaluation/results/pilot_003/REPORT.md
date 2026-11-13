# Piloto 003 — perguntas naturais e metadados de setor

Foram concluídos 40 pares de execução: 80 registros, 79 respostas e uma falha HTTP 504 preservada. Os índices contêm 62 artigos da pós, 376 da graduação e 438 no conjunto. A fase isolada começou em 19/10/2026 e a fase conjunta terminou em 20/10/2026, no fuso America/Sao_Paulo.

O Recall@5 da pós caiu de 1,0000 para 0,9375, diferença de −6,25 pontos percentuais, com intervalo bootstrap 95% [−15,625; 0,000] p.p. A graduação permaneceu em 0,9167. O intervalo da pós inclui zero. Estes são resultados de recuperação de uma amostra intencional de desenvolvimento; não demonstram insuficiência geral de RAG ou superioridade de agentes.

## Condições e controle

Snapshot de execução: commit `c6af8906dac40b8d58e26afe998b4311ec8d7f66`. Mesmo system prompt neutro, SHA-256 `dbe2b931d08dfa564bab82e8528b3dbaf5e15c1a737b09087fc61a40496fde4d`, nas três condições. Embeddings `openai/text-embedding-3-small`, geração `qwen/qwen3-30b-a3b-instruct-2507`, temperatura zero, máximo 800 tokens, top-k=5. Vetores calculados uma vez e reutilizados.

A pós contém 8 perguntas diretas, 8 abertas e 4 ambíguas. A graduação mantém as 20 perguntas originais: 6 respondíveis e 14 provisoriamente classificadas para esclarecimento do nível. Há uma regra comum de frequência e alternativas de evidência previamente definidas; detalhes no [protocolo](../../protocol_v2.md).

Os índices isolados recebem a norma correta por construção. O conjunto consulta os dois corpora sem filtro do rótulo gold. O setor aparece nos metadados, embeddings e contextos. O método executado é a baseline densa Chroma. Os filtros das ferramentas Supabase foram verificados em testes locais; este piloto não executa o loop agêntico nem mede o efeito causal de incluir setor.

A [análise primária](PRIMARY_ANALYSIS.md) foi registrada antes da fase conjunta. A opção 2 foi aplicada: nenhum item foi eliminado por desempenho e não houve corte mínimo de aprovação. A tentativa anterior [pilot_002](../pilot_002/FAILURE.md) falhou na conexão antes das respostas e foi preservada.

## Recuperação

Perguntas de esclarecimento não têm Recall normativo. Os denominadores são 16 para a pós e 6 para a graduação; a proporção de ambiguidades entre níveis não representa dificuldade equivalente.

| Conjunto | Condição | n respondíveis | Recall@5 | MRR@5 | nDCG@5 | Cobertura completa@5 | Outra norma@5 |
|---|---|---:|---:|---:|---:|---:|---:|
| Pós | Isolado | 16 | 1,0000 | 0,9375 | 0,9259 | 1,0000 | 0,0000 |
| Pós | Conjunto | 16 | 0,9375 | 0,8490 | 0,8274 | 0,8750 | 0,2875 |
| Graduação | Isolado | 6 | 0,9167 | 1,0000 | 0,8710 | 0,8333 | 0,0000 |
| Graduação | Conjunto | 6 | 0,9167 | 1,0000 | 0,8710 | 0,8333 | 0,0000 |

Na pós direta (n=8), Recall@5 permaneceu em 1,0000; nas abertas (n=8), caiu de 1,0000 para 0,8750. Na graduação, diretas (n=3) permaneceram em 1,0000 e abertas (n=3) em 0,8333. Hit@5 foi 1,0000 em todos esses grupos: todas as perguntas respondíveis receberam ao menos um artigo anotado, o que não garante que receberam todos os fatos necessários.

| Contraste conjunto − isolado | Pares respondíveis | Diferença Recall@5 | IC bootstrap 95% |
|---|---:|---:|---:|
| Pós | 16 | −6,25 p.p. | [−15,625; 0,000] p.p. |
| Graduação | 6 | 0,00 p.p. | [0,000; 0,000] p.p. |

Bootstrap percentil com 5.000 reamostragens e semente 956 por nível. O intervalo degenerado da graduação descreve os deltas observados; não demonstra equivalência populacional. Perguntas compartilham artigos e a amostra é pequena e intencional.

Apenas dois pares perderam Recall@5; ambos são abertos da pós:

| Item | Isolado | Conjunto | Alteração verificável |
|---|---:|---:|---|
| POS2-010 | 1,0 | 0,5 | Art.36 presente; art.3 sai do top-5 no conjunto. |
| POS2-011 | 1,0 | 0,5 | Art.38 presente; art.37 sai do top-5 no conjunto. |

Nos outros 20 pares respondíveis, Recall@5 permaneceu igual. Nenhum melhorou nessa métrica. Isso não estabelece igualdade das respostas, do ranking ou do contexto. A presença de outra norma indica composição do contexto; por exemplo, a regra comum de frequência permite evidência alternativa de outro setor.

## Respostas, falhas e revisão

`POS2-016 / isolated` retornou `OpenRouter retornou HTTP 504`, apesar da recuperação completa. O item está nos dados e no denominador original. Na condição conjunta foi produzida resposta; não houve repetição seletiva da chamada isolada. Uma comparação de qualidade precisa separar indisponibilidade operacional, recuperação e julgamento do conteúdo.

Os escores 0/1/2 e as taxas de esclarecimento adequado não têm anotação independente registrada. Não é válido deduzir nota 2 de Recall@5=1. A rubrica aprovada exige: 0 para erro ou ausência de resposta; 1 para incompletude sem erro material ou falta de evidência necessária; 2 para resposta correta, completa e sustentada. Nas ambíguas, avaliar a solicitação de nível antes de aplicar regra. As 36 saídas das 18 perguntas de esclarecimento estão preservadas, sem misturá-las ao acerto normativo.

Há [80 formulários](review_template.json) com campos de revisão nulos. Usar cópias independentes para dois avaliadores e adjudicar divergências. Não entregar a [chave](blinding_key.json), os registros identificados por condição ou este relatório durante a primeira anotação. O texto pode revelar a condição; a revisão posterior das evidências reduz o cegamento. O gold candidato, fatos obrigatórios e classificação de ambiguidades também precisam ser revisados.

## Auditoria e organização

[Auditoria recalculada](audit.json): 80 combinações únicas, 40 perguntas com ambas as condições, métricas por linha e resumos primário/final iguais à recomputação; prompt de cada linha igual à construção com pergunta e contexto, sem anotações gold adicionais; hash do system prompt verificado. Os 22 hashes de arquivos do snapshot de execução foram conferidos.

[rows.jsonl](rows.jsonl) mantém perguntas, respostas integrais, contextos ordenados, evidências, falhas e recibos. [summary.json](summary.json) contém resultados por categoria e contraste pareado. [manifest.json](manifest.json) registra parâmetros e hashes da execução. A representação técnica publicada separa metadados editoriais. [publication_projection.json](../../publication_projection.json) liga os hashes anteriores aos publicados, sem alterar métricas ou o conteúdo científico. Ver [organização dos artefatos](../../ARTIFACT_LAYOUT.md).

Recibos disponíveis: 79 gerações, 181.818 tokens e soma `usage.cost` de 0,02183149; 8 requisições de embedding, 101.902 tokens e soma 0,00203804. São números informados pelo provedor. A chamada com erro não tem recibo de uso; não presumir ausência de cobrança. O intervalo de calendário entre fases inclui interrupção do trabalho, e não é medida de latência.

O pós-processador de auditoria foi acrescentado após o congelamento do runner e não altera o desfecho experimental. Recalcular a partir de `code/`:

```powershell
uv run --no-sync python -m rag_baseline.audit_v2 ../evaluation/results/pilot_003
```

## Alcance da evidência

Verificação final via `uv run --no-sync pytest -q`: **138 passed, 2 skipped, 4 warnings**, em 59,61 segundos. Houve um timeout de 10 segundos no teste de interface Streamlit em uma execução anterior; o teste passou isoladamente e a suíte completa posterior passou sem mudança para relaxar esse limite. Os quatro avisos são de dependências e mocks já observados. Testes novos permanecem locais e ignorados pelo Git, conforme solicitado. Ruff dos módulos alterados passou.

A inclusão da segunda norma reduziu a cobertura anotada em duas perguntas abertas da pós nesta configuração. O intervalo descritivo inclui ausência de diferença. A recuperação foi alta no controle isolado, porém precisão e completude das respostas exigem revisão de conteúdo. O experimento não prova que RAG é insuficiente em geral nem que um agente resolveria essas falhas.

As limitações incluem gold candidato de desenvolvimento, evidências não exaustivas, distribuição diferente de ambiguidades, tamanhos desiguais de corpus, uma repetição por condição, intervalo temporal entre fases e possível variação do provedor. O snapshot da pós não contém art.30. Não houve comparação controlada com/sem setor, busca híbrida, reranker ou roteamento. A próxima evidência confirmatória exige gold revisado, perguntas independentes e ablações predefinidas. Fundamentação e referências estão no [protocolo](../../protocol_v2.md) e no [registro de decisões](../../decisions.md).
