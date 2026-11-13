# Artefatos técnicos e snapshots de execução

`evaluation/` contém datasets candidatos, corpora, protocolos, parâmetros, respostas integrais do modelo, contextos ordenados, métricas automáticas, erros, recibos e auditoria. Anotações internas de desenvolvimento, autoria editorial e registros de revisão preliminar não fazem parte dos artefatos técnicos.

## Evidência histórica

Manifestos, resumos, `audit.json`, relatórios e verificações de cada execução permanecem congelados e documentam o que ocorreu na época. Os hashes originais dos manifestos continuam identificando os insumos efetivamente usados, e relatórios antigos podem citar o local anterior desses arquivos. `publication_projection.json` registra os hashes anteriores e publicados dos arquivos cuja representação editorial mudou. Não interpretar a mudança de hash de um dataset como nova execução experimental.

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

`structured_evaluation_v2` guarda em `frozen_hashes` os bytes de código, testes e entradas do commit da execução, com as quebras de linha do checkout de origem. Por isso, `verify_hashes` falha em commits posteriores: é o comportamento esperado para um registro congelado, não um defeito nem uma perda de dados.

A verificação histórica usa os bytes da execução: o commit `experimental_head` do manifesto, na representação de quebra de linha que corresponde a cada hash, junto dos arquivos de saída da execução. Com esses bytes, os 69 caminhos conferem sem alterar nenhum hash. A verificação não faz chamadas de API. O `--stage run` da própria execução recusa uma nova execução, porque o manifesto está `complete`.

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
