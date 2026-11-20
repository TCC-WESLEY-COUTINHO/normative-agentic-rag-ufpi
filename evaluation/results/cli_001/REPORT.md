# CLI 001 — rodada de desenvolvimento

> **Registro histórico.** Configuração, resultados, contagens de testes e estados descritos referem-se à execução documentada, anterior à v3.4. Para a versão atual, consulte o [guia de evidências e reprodução](../../README.md).

Execução real do novo comando `rag_baseline.chat` com as duas normas na coleção `ufpi_duas_regulacoes_setor`: 376 artigos da graduação e 62 da pós, 438 IDs distintos. Foram enviadas as 20 perguntas originais da pós V2, lidas da apresentação numerada, sem as respostas de referência. Há 20 registros e nenhum erro operacional.

Nas 16 perguntas respondíveis, Recall@5 e cobertura completa@5 foram 1,0000. As quatro perguntas com ação esperada de esclarecimento ficam fora dessas métricas. Todas as respostas desta rodada foram geradas pelo modelo; ainda não havia a proteção determinística de escopo da rodada posterior. Escores de conteúdo permanecem nulos.

As respostas integrais e referências estão em `pos_responses.jsonl`; parâmetros e hashes de código em `manifest.json`; recuperação recalculada em `summary.json` e `row_metrics.json`. Um snapshot parcial dos módulos desta execução está em `execution_snapshot/`; `preservation_manifest.json` distingue arquivos preservados, projeções e o que não foi incluído. O manifesto registra árvore de trabalho em desenvolvimento, anterior ao commit da implementação final.

Esta rodada foi usada para desenvolvimento de comportamento, inclusive concisão, orientação sobre unidades e tratamento de nível ausente. Foi preservada e não será substituída pela rodada posterior. A comparação entre as duas não é ablação controlada nem validação independente de acurácia normativa; ver [protocolo operacional](../../CLI_VALIDATION.md).
