# Análise primária — índices isolados

> **Registro histórico.** Configuração, resultados, contagens de testes e estados descritos referem-se à execução documentada, anterior à v3.4. Para a versão atual, consulte o [guia de evidências e reprodução](../../README.md).

Registro elaborado após a conclusão da fase isolada e antes da execução conjunta. Snapshot experimental: commit `c6af890`; parâmetros e hashes no manifesto. A primeira fase terminou em `2026-10-19T22:39:16.323033+00:00`.

| Conjunto | Itens | Respondíveis | Esclarecimento esperado | Recall@5 | Cobertura completa@5 | Erros de geração |
|---|---:|---:|---:|---:|---:|---:|
| Pós | 20 | 16 | 4 | 1,0000 | 1,0000 | 1 |
| Graduação | 20 | 6 | 14 | 0,9167 | 0,8333 | 0 |

Índices: pós 62 artigos; graduação 376. Na pós, diretas e abertas tiveram Recall@5=1,0000, com oito perguntas em cada estrato. Na graduação, diretas=1,0000 (n=3) e abertas=0,8333 (n=3). As perguntas cujo resultado esperado é esclarecer o nível não entram nas métricas de recuperação normativa.

`POS2-016` recuperou todas as evidências gold, mas não produziu resposta: `OpenRouter retornou HTTP 504`. Trata-se de falha operacional de geração; não excluir o item nem repetir seletivamente a chamada neste piloto. Os escores de revisão permanecem nulos. Recuperar todos os artigos não equivale a responder corretamente ou de forma completa.

Decisão de continuidade: aplicar a opção 2 aprovada, sem percentual mínimo de aprovação, mantendo as 40 perguntas, incluindo a falha operacional e as ambiguidades. Executar o índice conjunto com o mesmo prompt, configurações e vetores, conforme protocolo congelado. As métricas desta análise não estabelecem correção do conteúdo nem adequação dos esclarecimentos.
