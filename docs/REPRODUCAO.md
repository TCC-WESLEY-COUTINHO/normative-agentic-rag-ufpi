# Reprodução e verificações offline

Este snapshot preserva código, corpora, datasets, protocolos e parte das evidências históricas. Não contém todos os dados brutos e anotações das comparações finais. Uma execução nova não reproduz automaticamente os números publicados: provedor, modelo, índice, gold, configuração e repetição precisam ser identificados.

## Preparação e testes

A partir de `code/`, com Python 3.12 e `uv`, instale as dependências fixadas:

```bash
uv sync --frozen
```

No PowerShell, a partir de `code/`:

```powershell
$repoRoot = (Resolve-Path ..).Path
$env:PYTHONPATH="$repoRoot;$repoRoot\code"
uv run --frozen python -m pytest -q -p no:cacheprovider
uv run --frozen ruff check src tests
```

Em Linux/WSL, também em `code/`:

```bash
PYTHONPATH="..:.:src" uv run --frozen python -m pytest -q -p no:cacheprovider
uv run --frozen ruff check src tests
```

Os testes usam intérpretes roteirizados e não chamam provedores. Para executar sem acesso à rede com o ambiente já instalado, defina `UV_OFFLINE=true`. As verificações de software não atribuem qualidade normativa às respostas.

## Conferir a projeção publicada

O inventário [published_artifacts.json](../evaluation/published_artifacts.json) identifica a proveniência e os hashes dos artefatos científicos publicados. O [mapa de projeção](../evaluation/publication_projection.json) registra transformações editoriais; não representa uma nova execução.

A partir de `code/`:

```bash
uv run --frozen python -B -m rag_baseline.audit_projection
```

Esse comando não chama APIs nem grava relatórios. Confere hashes e tamanhos dos snapshots preservados, recalcula métricas dos registros projetados e compara seus campos científicos. Não atesta identidade de bytes com os insumos históricos ausentes. O teste `test_published_artifacts_hashes_are_independent_of_checkout_eol`, em [`test_experiment.py`](../code/tests/rag_baseline/test_experiment.py), verifica o inventário com normalização de quebras de linha.

Para layout, limitações e requisitos da auditoria histórica `audit_v2`, consulte [Artefatos técnicos e snapshots](../evaluation/ARTIFACT_LAYOUT.md). Essa auditoria exige os bytes históricos e um diretório de relatório novo ou vazio fora de `evaluation/`; não deve ser confundida com a conferência da projeção.

## Recalcular o que permanece disponível

Os pilotos preservados têm perguntas, respostas e resumos próprios. São resultados históricos exploratórios, sem atribuição retroativa à v3.4. No piloto V1, o suplemento de recuperação por norma pode ser recalculado, sem API e com saída apenas no terminal:

```bash
uv run --frozen python -m rag_baseline.analyze_experiment ../evaluation/results/pilot_001/rows.jsonl
```

O suplemento complementa o resumo macrogeral original, sem substituí-lo. Para `pilot_003`, use `audit_projection`, mostrado acima: ele recalcula as métricas dos registros projetados com o esquema V2. O analisador V1 não se aplica aos itens de esclarecimento com métricas nulas desse piloto. Os [pilotos e seus protocolos](../evaluation/README.md) descrevem as condições e rubricas.

As auditorias de saídas CLI e terminal também podem ser executadas sem provedor; seus relatórios vão para a saída padrão, e arquivos só são gravados com `--output-dir`, fora da entrada. Consulte o [layout dos artefatos](../evaluation/ARTIFACT_LAYOUT.md#auditorias-sem-escrita-na-entrada).

## Limite da reprodução das comparações finais

Os golds revisados estão em [`evaluation/datasets/`](../evaluation/datasets/), com descrição em [REVIEWED_V2.md](../evaluation/datasets/REVIEWED_V2.md). Gold revisado v2 é uma versão do dataset, diferente da condição de software v2.

Os recálculos de C1, C2, C3 e das anotações finais do pesquisador dependem de registros preservados fora do repositório. Este snapshot também não inclui os registros finais completos dos conjuntos sintético e complexo da comparação v3.4 × v2. Os [resultados](RESULTADOS.md) são relatados com essas limitações; os comandos acima verificam apenas evidências disponíveis.

## Novas execuções com provedor

Não são necessárias para validar a documentação ou executar os testes offline. Exigem credencial, índice adequado e chamadas pagas. Use sempre diretórios novos e preserve configuração, manifesto, respostas e erros; nunca substitua registros publicados.

- Os pilotos têm executores e comandos em [evaluation/README.md](../evaluation/README.md).
- O executor [`evaluation/adaptive_rag/run.py`](../evaluation/adaptive_rag/run.py) mantém as condições experimentais anteriores; não constitui, por si só, uma réplica da v3.4.
- As execuções estruturadas têm pré-requisitos de preparação e manifestos completos descritos em [Artefatos técnicos](../evaluation/ARTIFACT_LAYOUT.md#executores-de-execução-única). Use `--output <diretório novo>`; o nome padrão da segunda rodada estruturada não está publicado neste snapshot. O estado `complete` só bloqueia reutilização quando há um manifesto nesse estado no diretório de saída.

Para execução do protótipo, veja [Instalação](INSTALACAO.md). `GET /prototype/identity` informa tag e commit fornecidos ao build, arquitetura e configuração em execução; sem `PROTOTYPE_GIT_COMMIT`, o commit é `unknown`. Na v3.4, o build não verifica o manifesto congelado de fontes da v2; os manifestos históricos servem à conferência das respectivas tags.
