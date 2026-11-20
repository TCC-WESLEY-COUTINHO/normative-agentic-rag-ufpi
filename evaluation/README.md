# Evidências acadêmicas: piloto multi-resolução

> **Registro histórico dos pilotos e das avaliações anteriores à v3.4.** O gold revisado
> é descrito em [`datasets/REVIEWED_V2.md`](datasets/REVIEWED_V2.md)
> (`datasetgold_reviewed_v2`: arquivos `*_reviewed_v2.json`); a versão do gold não é a versão do sistema.
> As [evidências históricas por questão de pesquisa](../docs/tcc2/AVALIACAO_TCCII_JEV_V2.md)
> distinguem as condições anteriores. Para a v3.4, consulte [resultados](../docs/RESULTADOS.md)
> e [reprodução e limites](../docs/REPRODUCAO.md).

Este diretório contém artefatos científicos. Os dois conjuntos são **candidatos a gold**, sem caráter de gabarito normativo independente. O gabarito original da graduação permanece preservado em `data/questoes_para_avaliar_o_agente.md`.

## V2 para revisão — perguntas naturais e setor

- [Piloto V2 concluído: resultados e limites](results/pilot_003/REPORT.md).
- [Separação dos artefatos técnicos e arquivo local](ARTIFACT_LAYOUT.md), com [mapa de hashes](publication_projection.json).

- [Pós V2: 8 diretas, 8 abertas, 4 ambíguas](datasets/pos_graduacao_v2.md).
- [Graduação V2: perguntas originais e ações esperadas](datasets/graduacao_v2.md).
- [Integridade técnica e limites dos candidatos](datasets/VALIDATION_V2.md).
- [Protocolo V2 e rubrica 0/1/2](protocol_v2.md).
- `corpora/*_setor_v2.json`: cópias derivadas com setor explícito e identificação de fonte; conteúdo normativo preservado. A V1 abaixo permanece como registro do primeiro piloto.

## Artefatos

- [Graduação: 20 perguntas e respostas](datasets/graduacao_v1.md), com [anotações e evidências](datasets/graduacao_v1.json).
- [Pós-graduação: 20 perguntas e respostas](datasets/pos_graduacao_v1.md), com [anotações e evidências](datasets/pos_graduacao_v1.json).
- [Protocolo congelado antes da execução](protocol.md): hipótese, condições, fórmulas, rubrica de avaliação e limitações.
- [Registro de justificativas](decisions.md) e [bibliografia BibTeX](references.bib).
- [Relatório do piloto concluído](results/pilot_001/REPORT.md): métricas, casos exploratórios, ameaças à validade e conclusão.
- `results/pilot_001/`: manifesto, respostas/contextos integrais, métricas e formulário de revisão.

## Como reproduzir

Os comandos abaixo executam o piloto denso histórico, com corpora e prompt próprios; não reproduzem o fluxo conversacional nem a geração citada da v3.4. A partir de `code/`, com dependências gerenciadas por uv:

```powershell
uv sync --frozen
uv run --frozen python -m rag_baseline.experiment --validate-only
uv run --frozen python -m rag_baseline.experiment --output ../evaluation/results/pilot_v1_nova_execucao
```

O segundo comando não chama APIs. O terceiro usa a chave local configurada, gera embeddings e respostas remotas com custo; exige um nome de saída novo. Não versionar `.env`, credenciais, caches ou bancos Chroma. Uma nova execução não deve substituir a anterior. Conferir modelos e hashes no manifesto, pois a configuração local pode mudar.

Para recalcular o suplemento por nível, sem API e sem alterar resultados:

```powershell
uv run python -m rag_baseline.analyze_experiment ../evaluation/results/pilot_001/rows.jsonl
```

Esse pós-processador foi acrescentado após o congelamento do runner. `per_norm_summary.json` complementa, sem substituir, o `summary.json` original. Usa o mesmo método e parâmetros bootstrap por nível; não modifica o desfecho primário macrogeral.

## Revisão

Validar os candidatos contra os PDFs originais antes de chamá-los de gold independente. Para avaliar respostas, entregar **cópias separadas** de `review_template.json` a dois avaliadores; não entregar `blinding_key.json`, `rows.jsonl` ou o relatório até encerrarem a anotação. A chave é publicada para auditabilidade, portanto o cegamento depende desse controle de acesso e não é garantido pelo repositório público. Evidências recuperadas não são incluídas no formulário para não revelar a condição; a avaliação de citações deve consultar também os PDFs completos, pois os qrels não são exaustivos.

Os campos de avaliação estão nulos de propósito. Não transformar métricas de recuperação ou similaridade lexical em acurácia das respostas. A comparação avalia uma configuração específica, não toda a família RAG nem a superioridade de agentes.
