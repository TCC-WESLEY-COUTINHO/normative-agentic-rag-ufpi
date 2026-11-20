# Artefatos técnicos e snapshots de execução

`evaluation/` contém datasets candidatos, corpora, protocolos, parâmetros, respostas integrais do modelo, contextos ordenados, métricas automáticas, erros, recibos e auditoria.

## Evidência histórica

Resumos, respostas e métricas documentam as execuções históricas. A publicação retém os recibos necessários às verificações científicas e exclui registros operacionais. `publication_projection.json` registra a projeção editorial e `published_artifacts.json` identifica os arquivos publicados, com hashes normalizados para LF. Uma mudança editorial de hash não constitui nova execução experimental.

Nas pastas `structured_normative_output_v1_001` e `temporal_generation_grounding_v1_001`, foram mantidos os contextos, entradas, respostas, anotações, protocolos, métricas e manifestos necessários aos testes e à comparação das gerações. As anotações preliminares automatizadas usam `automated_preliminary` quando o campo registra essa proveniência; não constituem gold jurídico independente nem certificam correção normativa. Relatórios de desenvolvimento e registros operacionais dessas pastas foram retirados. Os valores das métricas e dos julgamentos foram preservados.

O recibo `router_v2_exploratory_001/preservation_before.json` retém somente o hash do índice consumido pelo executor. Os três `execution_snapshot/preservation_manifest.json` permanecem porque `audit_projection` os lê; os hashes e tamanhos das projeções editoriais foram atualizados junto dos arquivos.

Os bytes históricos de parte dos insumos não são publicados neste repositório; essa categoria é chamada `private_raw_only`. Eles só importam para a auditoria histórica, e nenhuma verificação da projeção depende deles.

## Projeção científica do repositório

`results/pilot_001/`, `results/pilot_003/` e `results/cli_001/` têm `execution_snapshot/`, descrito por `preservation_manifest.json`.

- `byte_preserved`: bytes iguais aos registrados no manifesto da execução.
- `scientific_projection`: `non-scientific metadata normalized`, com hash próprio. Não reproduz o hash histórico nem o substitui.
- `not_included`: insumos registrados no manifesto da execução que não estão no snapshot. É uma declaração da composição do snapshot, não um erro.

Os snapshots de `pilot_001` e `cli_001` são parciais: contêm 3 dos 18 e 18 dos 19 insumos registrados, respectivamente. O de `pilot_003` contém projeção ou cópia de todos os 22 insumos, além da projeção dos registros de execução. Nenhum dos três permite afirmar equivalência de bytes com os arquivos históricos projetados.

Nomes de campos das projeções podem diferir dos registros históricos, por exemplo `review_score_0_2`. `interpretive_note` guarda, em forma neutra, uma ressalva do caso que constava em uma nota antiga; não é lido pelo código de experimento. `candidate_gold` é um estado científico não final: não indica resultado validado, aprovação nem conclusão. Perguntas, referências, fatos obrigatórios, evidências, alternativas suficientes, decisões de esclarecimento, respostas do modelo, prompts, metadados de recuperação, métricas e falhas têm os mesmos valores.

A ausência de um campo ou de uma nota de estado não significa que o item foi revisado, aprovado ou validado.

## Verificações

`audit_projection` verifica somente o que está no repositório, sem chamadas de API e sem gravar relatórios. Confere hashes e tamanhos dos snapshots, recalcula métricas e prompts dos registros projetados e compara seus campos científicos com `rows.jsonl`. Usa funções do código atual, e não atesta os bytes históricos das projeções.

```powershell
uv run --no-sync python -B -m rag_baseline.audit_projection
```

`audit_v2` é a auditoria do layout histórico de `pilot_003`, acrescentada após o congelamento do runner. Exige os bytes históricos, que não estão no repositório, e grava relatório e formulários em um diretório novo ou vazio fora de `evaluation/`, sem regravar os registros dos runs. Não é uma verificação da projeção.

```powershell
uv run --no-sync python -B -m rag_baseline.audit_v2 ../evaluation/results/pilot_003 --raw-snapshot <diretorio> --report-dir <diretorio>
```

## Executores de execução única

`structured_evaluation_v2` guarda em `frozen_hashes` os bytes de código, testes e entradas. Nesta projeção, os hashes dos arquivos editados foram atualizados e as entradas dos registros retirados foram excluídas; os manifestos anteriores são identificados em `publication_projection.json`. Os demais hashes continuam históricos, com as quebras de linha do checkout de origem, e podem divergir do código atual. A projeção não atesta os bytes do commit experimental.

A verificação histórica exige o manifesto e os bytes originais do commit `experimental_head`, na representação de quebra de linha correspondente, junto dos arquivos de saída. A rodada `structured_normative_output_v2_001` não integra este snapshot; o executor permanece para estudos históricos e usa esse nome como saída padrão. Sempre informe `--output <diretório novo>`: a saída padrão ausente não tem manifesto `complete` para bloquear sua reutilização. Nos diretórios que contêm um manifesto `complete`, o `--stage run` recusa uma nova execução.

Uma execução nova usa `--stage prepare --output <diretório novo>`. Antes dele:

- `initial_audit.json` e `execution_log.jsonl` precisam existir em `<diretório novo>`;
- o diretório precisa estar dentro do repositório, em um checkout Git;
- a configuração do modelo precisa ser igual à de `structured_normative_output_v1_001/manifest.json`;
- `temporal_generation_grounding_v1_001/frozen_contexts.json` precisa conferir com o hash registrado no manifesto de `structured_normative_output_v1_001/`, a única conferência feita aqui. Os demais arquivos desse diretório são lidos e congelados como estão, sem comparação com hashes históricos.

O `--stage run` exige credencial do provedor. Uma execução nova não substitui nem reproduz os resultados históricos.

## Auditorias sem escrita na entrada

`audit_cli` e `audit_terminal` não gravam na pasta auditada. O resumo vai para a saída padrão; arquivos são gravados só com `--output-dir <diretório vazio fora da entrada>`. O `summary.json` publicado registra o hash dos arquivos da execução, e uma entrada projetada produz outro `output_sha256`, sem mudança nas métricas.

## Revisão

A promoção para conjunto validado exige revisão. Os escores 0/1/2 permanecem nulos até julgamento do conteúdo e das evidências, e valores nulos não indicam aprovação. Os relatórios técnicos não convertem recuperação em acurácia normativa.

Para preparar a revisão, fornecer cópias separadas do formulário de anotação do run a dois avaliadores, sem `blinding_key.json`, respostas identificadas por condição ou relatório. O texto de uma resposta pode revelar o escopo mesmo assim. Após a primeira anotação de conteúdo, disponibilizar os contextos para revisar suporte e suficiência de evidência; registrar essa etapa e o limite do cegamento. A adjudicação é necessária antes de publicar resultados de acerto.
