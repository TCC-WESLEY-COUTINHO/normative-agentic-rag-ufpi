# Duas demos temporais

As saídas preservadas usam o mesmo código `82b83ae`, coleção de 507 registros,
modelo, embedding e prompt das comparações. Foram executadas pelo terminal
existente com a API FastAPI em processo (`TestClient`) e chamadas reais ao
provedor. São verificações funcionais adicionais; não entram nas métricas B/D.

## Reprodução ao vivo

Na pasta `code/`, usando o ambiente configurado, iniciar a API existente:

```powershell
python -m uvicorn rag_baseline.api:app --host 127.0.0.1 --port 8080
```

Em outro terminal:

```powershell
python -m rag_baseline.demo --setor automatico --verbose --question "Na pós-graduação da UFPI, com qual antecedência mínima a defesa de dissertação ou tese deve ser divulgada atualmente?"
python -m rag_baseline.demo --setor automatico --verbose
```

Na segunda demo, informar:

> Qual é a regra vigente do art. 68, §4º da graduação da UFPI para designar o
> coordenador de estágio em cursos de programas institucionais com docentes
> selecionados por edital, sem vínculo com a UFPI?

Se o Router solicitar esclarecimento, repetir apenas o nível já informado:
"Graduação da UFPI". Essa informação não é inventada a partir do retrieval.
O resultado não é garantido por temperatura zero; os pedidos indevidos de
esclarecimento observados são preservados, sem ajuste do Router.

## Pós: revogação integral

- Saída real: [demo_pos_terminal.txt](demo_pos_terminal.txt).
- Resposta e auditoria: [demo_pos_response.jsonl](demo_pos_response.jsonl).
- Rota: pós-graduação; 658 excluída previamente com base na 956, art. 62, VI;
  contexto final somente da 956.
- A competição real entre 658/956 está no par `TEMP-POS-001` B/D em
  [comparison.json](comparison.json). O verbose de D mostra a exclusão prévia;
  não chama esses documentos de candidatos efetivamente recuperados em D.
- [pos_same_candidates_replay.json](pos_same_candidates_replay.json) aplica
  deterministicamente o filtro aos cinco candidatos reais de B: remove os
  dois da 658 e preserva três da 956. Esse replay não faz nova recuperação
  nem geração; D recuperou cinco após pré-exclusão.

## Graduação: alteração parcial

- Saída interativa real: [demo_grad_interactive_terminal.txt](demo_grad_interactive_terminal.txt).
- Resposta e auditoria: [demo_grad_interactive_response.jsonl](demo_grad_interactive_response.jsonl).
- Rota: graduação; bloco `ALTERAÇÃO PARCIAL` identifica norma-base 177/2012,
  art. 68, §4º, ato 1.056/2026, regra de precedência e redação aplicável.
- O artigo 68 permanece com seu ID; somente o texto introdutório do §4º é
  substituído em memória. Alíneas e outros artigos continuam no contexto.
- [grad_same_candidates_replay.json](grad_same_candidates_replay.json) contém
  o chunk original, ato alterador, redações e contexto final sobre os candidatos B.

Uma execução adicional anterior no modo não interativo pediu esclarecimento
indevido: [demo_grad_terminal.txt](demo_grad_terminal.txt) e
[demo_grad_response.jsonl](demo_grad_response.jsonl). Ela foi mantida.
A execução interativa subsequente respondeu em uma consulta, sem precisar
consumir o esclarecimento preparado. Não se apresenta apenas a tentativa
favorável como estimativa de confiabilidade do Router.
