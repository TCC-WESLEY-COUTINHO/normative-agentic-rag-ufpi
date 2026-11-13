# Verificação técnica final

Data: 2026-10-20. Código executado: `ebf14b42f458dce674ffda21bca94a31baf9dd1a`. Comandos a partir de `code/`, usando `uv`, ambiente local existente e sem alteração de dependências.

| Verificação | Resultado |
| --- | --- |
| `uv run --no-sync pytest -q` | 162 aprovados, 2 ignorados, 4 avisos; 67,08 s; saída 0 |
| `uv run --no-sync pytest -q tests/rag_baseline` | 99 aprovados, 2 avisos; 63,15 s; saída 0 |
| `uv run --no-sync ruff check src/rag_baseline` | Sem erros; saída 0 |
| Hashes de código/entradas do manifesto CLI 003 | Todos conferem com os arquivos executados |
| Arquivos de execução CLI 003 | Três registros, nenhum erro; hashes registrados no resumo |
| Índice conjunto | 438 IDs distintos, 376 graduação e 62 pós; conferência na indexação real e no manifesto CLI 002 |

Os testes cobrem representação e ordem das 20 perguntas, leitura somente de perguntas sem vazamento do gabarito, fábrica real do serviço, propagação/filtros de setor, compatibilidade com índices legados sem setor, colisões de numeração de artigo entre normas, comparação entre níveis, esclarecimento antes de chamadas remotas, retomada de contexto, erros de lote, proteção de saída e reescrita limitada de exemplos. Testes novos e notas de desenvolvimento ficam locais e ignorados no Git, conforme a orientação do projeto; não são fornecidos como suíte pública adicional.

Uma execução anterior da suíte apresentou timeout de inicialização do teste Streamlit (limite de dez segundos), com 161 aprovados, 1 falha e 2 ignorados. Outra tentativa, concorrente, encontrou `MemoryError` ao iniciar Python. A execução final acima foi feita em sequência e passou com o limite original de dez segundos, sem alteração persistente desse teste. Os avisos remanescentes envolvem deprecações Pydantic/Starlette e um mock assíncrono do cliente legado; não se declara que tenham sido corrigidos nesta tarefa.

Os artefatos históricos de `pilot_003`, datasets V2 e mapa de projeção editorial não foram modificados por esta entrega. CLI 001/002/003 preservam suas versões e resultados separadamente. Sucesso dos testes automatizados e Recall@5 não são uma nota humana de correção normativa; os limites de conteúdo estão nos respectivos relatórios.
