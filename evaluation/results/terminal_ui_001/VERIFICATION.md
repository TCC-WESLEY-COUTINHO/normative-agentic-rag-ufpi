# Verificação técnica — escopo explícito no terminal original

Código executado: `5f281a15eab549d15cea429498bd1a4322c15a3f`. Data de referência: 2026-10-20, America/Sao_Paulo.

| Comando/verificação | Resultado observado |
| --- | --- |
| `uv run --no-sync pytest -q` | 155 aprovados, 2 ignorados, 4 avisos; 92,40 s; saída 0 |
| Testes direcionados de terminal, auditor, API e serviço | 29 aprovados antes da checagem adicional de escopo |
| Testes finais de terminal e auditor | 17 aprovados; 14,99 s |
| `uv run --no-sync ruff check src/rag_baseline` | Sem erros; saída 0 |
| `rag_baseline.demo --help` e alias `rag_baseline.chat --help` | Mesmas opções de UI, escopo, lote e saída |
| Quatro lotes reais | 80 registros; 73 respostas recebidas e sete falhas preservadas; saída 1 por lote |
| Menu real antes da pergunta | Graduação, pós e ambas verificadas; três registros adicionais sem erro; encerramento 0 |
| Auditor de respostas | Perguntas/ordem, escopos, fontes, texto, ranking, duplicatas e top-k validados |
| Integridade | Entradas e código iguais ao manifesto; resumo primário e hashes de seus lotes preservados |

Testes novos observaram falha antes da implementação: escopo ignorado/inferido, reescrita não solicitada, ausência de menu, falta de proteção da saída e retorno zero em interrupção de lote. A versão corrigida usa Chroma real em fixtures pequenas e simula apenas a fronteira remota, preservando a construção real do cliente/API. Não se usam respostas simuladas como resultados da exploração publicada.

Uma execução anterior apresentou `test_app_simple_non_streaming`: timeout original de dez segundos, com 149 aprovados, 1 falha, 2 ignorados e 4 avisos. Outra apresentou `test_two_stages_keep_all_pairs_and_reject_mutated_results`: erro interno Chroma `Nothing found on disk`, com 153 aprovados, 1 falha, 2 ignorados e 4 avisos. Esse teste passou isoladamente, sem mudanças, e a suíte final acima passou em sequência. Não foi demonstrada a causa definitiva dessas falhas intermitentes; não foram alterados o limite do Streamlit, o runner histórico ou o armazenamento para escondê-las.

Os quatro avisos finais são de deprecações Pydantic/Starlette e mock assíncrono do cliente legado; não foram corrigidos nesta tarefa. `uv lock` só tornou explícita a dependência Rich já usada na branch original, sem mudar versões de pacotes; a resolução mostrou aviso de versão Supabase já bloqueada/yanked, fora do caminho Chroma/API desta exploração.

Os testes locais antigos do CLI alternativo exigiam o comportamento agora rejeitado. Foram arquivados, sem apagá-los; os novos testes substituem esse contrato. Contagens de testes não são métricas de qualidade normativa ou evidência de superioridade de arquitetura.

`pilot_003`, os datasets V2, o mapa de projeção editorial e `cli_001/002/003` não foram reescritos. A presente exploração tem diretório, código de referência e controles próprios. A aprovação técnica dos filtros não constitui aprovação das respostas.

Os cinco JSONLs novos mantêm os bytes originais, inclusive CRLF emitido no Windows. O atributo Git `-text` impede normalização de fim de linha; identidade entre blob preparado para commit e arquivo bruto é conferida em `archive_integrity.json`. Isso preserva os SHA-256 registrados sem reformatar respostas após a execução.
