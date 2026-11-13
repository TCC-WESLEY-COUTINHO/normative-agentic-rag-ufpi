# CLI 002 — verificação conjunta das duas listas

Rodada operacional real no commit `97327fa8cee65c6ed37ec0918d5666053806873b`. Coleção `ufpi_duas_regulacoes_setor`, com 438 IDs distintos: 376 da graduação e 62 da pós. As duas listas numeradas foram lidas pelo comando `rag_baseline.chat`; somente as perguntas foram enviadas, sem respostas gold. Configuração, prompt integral e hashes estão em `manifest.json`.

Foram concluídas 40 consultas, sem erro de execução. A proteção determinística de escopo solicitou esclarecimento em 18 casos; essas saídas não foram geradas pelo modelo e não demonstram capacidade de desambiguação aprendida. As 22 consultas restantes tiveram geração com recuperação de cinco artigos.

| Grupo | Total | Respondíveis | Esclarecimentos | Recall@5 | Evidência completa@5 | Norma incorreta@5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pós-graduação | 20 | 16 | 4 | 1,0000 | 1,0000 | 0,0000 |
| Graduação | 20 | 6 | 14 | 0,9167 | 0,8333 | 0,0000 |

Métricas calculadas apenas nas perguntas respondíveis, com pares norma/artigo e as alternativas de evidência previamente anotadas. `summary.json` e `row_metrics.json` permitem inspecionar os cálculos; os arquivos `*_responses.jsonl` preservam respostas e trechos integrais. Não houve referências de outro setor nas perguntas com nível explícito.

## Limites observados

Recuperação correta não equivale a resposta normativa correta. A resposta à terceira pergunta da graduação começa negando o Exame Final e termina concedendo-o, além de extrapolar os fatos pessoais informados. A resposta sobre proficiência no mestrado contém referências/formulações que exigem conferência com o artigo recuperado. A primeira resposta da pós acrescenta exemplos numéricos não solicitados. Esses registros não foram corrigidos retroativamente.

A correção posterior de exemplos numéricos não está neste commit: seu teste dirigido deve ser consultado em `cli_003`. Ela não valida todas as condições, exceções, citações ou contradições. As notas humanas 0/1/2 continuam nulas; não se declara acurácia de conteúdo nem prontidão para aconselhamento normativo sem revisão.

Esta é uma rodada de desenvolvimento com inspeção e ajustes de implementação, não uma ablação controlada nem substituição de `pilot_003`. O prompt operacional e a proteção de escopo diferem do experimento acadêmico anterior. Não usar esses números para atribuir causalmente ganhos aos metadados, nem para concluir que uma classe inteira de RAG é insuficiente.

## Reprodução

A partir de `code/`, com as configurações locais e acesso ao provedor:

```powershell
uv run python -m rag_baseline.chat --questions-file ../data/questoes_para_avaliar_o_agente_pos_graduacao.md --json --output nova_pos.jsonl
uv run python -m rag_baseline.chat --questions-file ../data/questoes_para_avaliar_o_agente.md --json --output nova_grad.jsonl
uv run python -m rag_baseline.audit_cli ../evaluation/results/cli_002
```

Para reproduzir o comportamento desta rodada, usar o commit registrado no manifesto. Novas execuções usam arquivos novos; a CLI recusa sobrescrita. Respostas remotas podem variar mesmo com temperatura zero.
