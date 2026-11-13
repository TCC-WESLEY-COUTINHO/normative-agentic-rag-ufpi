# CLI 003 — regressão dirigida e conversa interativa

Execução real no commit `ebf14b42f458dce674ffda21bca94a31baf9dd1a`, com as duas normas já indexadas na coleção de 438 artigos. O identificador exato do código, parâmetros, prompt e hashes estão em `manifest.json`; este teste não reexecuta as 40 consultas de `cli_002`.

## Checagens

- A pergunta sobre faltas no doutorado terminou sem erro, recuperou o art. 20 da pós e passou pela checagem formal depois de uma reescrita. `generation_attempts: 2` registra as duas chamadas ao mesmo modelo, com os mesmos trechos de evidência. A resposta final não contém o padrão de exemplo numérico não solicitado. A primeira versão não é uma observação independente nem conta como acerto adicional.
- No terminal interativo, a pergunta “Já cancelei uma matéria uma vez. Posso cancelar de novo?” recebeu somente pedido de esclarecimento, sem chamada de geração nem referências. Após a entrada “mestrado”, a mesma pergunta foi retomada, recuperando o art. 37 e outras referências exclusivamente da pós. A resposta menciona a exceção por doença comprovada. `/sair` encerrou com código zero.
- Foram preservados três registros em dois arquivos JSONL novos, sem sobrescrever rodadas anteriores. Não houve erro operacional.

Os campos verificados e hashes das saídas estão em `summary.json`. `attendance_response.jsonl` e `interactive.jsonl` preservam respostas e referências completas. Os números se referem a verificações dirigidas, não a uma estimativa de acurácia geral.

## Limites

O teste confirma execução, retomada do contexto declarado, filtragem de setor e uma proteção formal. Não comprova ausência de omissões, contradições ou citações inexatas. A resposta interativa ainda precisa ser revisada quanto à completude das condições administrativas do art. 37. Os problemas de conteúdo identificados na rodada anterior permanecem documentados em [CLI 002](../cli_002/REPORT.md); não se presume que a checagem de exemplos os tenha resolvido.

As notas de correção 0/1/2 continuam pendentes de revisão. O prompt e a política operacional não devem ser tratados como condições idênticas às do piloto acadêmico `pilot_003`. Esta rodada foi escolhida depois da inspeção de falhas, portanto é uma regressão de desenvolvimento, não um teste confirmatório independente.

## Reprodução

A partir de `code/`:

```powershell
uv run python -m rag_baseline.chat "Quantas faltas posso ter numa disciplina do doutorado sem reprovar?" --json --output nova_frequencia.jsonl
uv run python -m rag_baseline.chat --json --output nova_conversa.jsonl
```

Na conversa, enviar a pergunta de cancelamento, `mestrado` e `/sair`. Usar nomes novos para os arquivos de saída. A CLI usa a configuração local do provedor; respostas remotas podem variar mesmo com temperatura zero.
