# Terminal original — escopo explícito e validação

## Contrato aprovado

Reutilizar `rag_baseline.demo` da branch `demo/terminal-ui` (commit de referência `3932f45`), preservando interface Rich e comunicação HTTP com a API. Selecionar graduação, pós-graduação ou ambas uma vez ao iniciar, antes da primeira pergunta. Manter a seleção até o usuário digitar `voltar` no campo da pergunta e escolher outro escopo no menu. O roteamento automático pertence à futura implementação de agentes; não faz parte desta baseline.

A seleção altera somente o conjunto elegível na recuperação. Não determina o nível pessoal do aluno, não é acrescentada à pergunta/prompt, não é inferida por palavras como mestrado/IRA e não força esclarecimento. O modelo continua recebendo os trechos recuperados, seus metadados e a pergunta original. Esclarecer ou responder é saída do modelo a avaliar, não uma resposta construída por código.

## Implementação e controles

- Coleção conjunta `ufpi_duas_regulacoes_setor`: 376 artigos da graduação e 62 da pós, 438 IDs distintos. Seleção graduação/pós aplica igualdade ao metadado `sector`; ambas não aplica filtro. Não é exigida presença dos dois setores no top-5.
- Fonte, setor e hierarquia são mantidos no embedding/contexto e nas referências disponíveis. Setor ausente continua desconhecido; não recebe valor padrão de graduação. Filtro explícito não é removido silenciosamente em índices sem setor.
- Mesma recuperação densa Chroma e top-k=5 nos três escopos. O limite global dez da ferramenta por metadados Supabase não muda; essa ferramenta não é executada nesta exploração.
- O terminal/API injeta o prompt neutro **já existente no piloto V2**, SHA-256 `dbe2b931d08dfa564bab82e8528b3dbaf5e15c1a737b09087fc61a40496fde4d`. Não foi criado um prompt para cada setor ou ajustado após respostas desta rodada. O padrão histórico da biblioteca permanece apenas para compatibilidade de chamadas diretas, fora desta exploração.
- Uma chamada de geração por consulta bem-sucedida, sem reescrita, juízo automático de conteúdo ou resposta de esclarecimento determinística. Mesmo modelo, temperatura e limite de tokens nas três seleções, registrados no manifesto.
- O menu é apresentado uma vez ao iniciar a sessão interativa e novamente somente ao digitar `voltar`. A seleção atual aparece antes das perguntas e persiste após entrada vazia ou erro de consulta. `voltar` é navegação local, não é enviado como pergunta à API. `--setor` define o escopo inicial interativo, que também pode ser trocado; em lote/consulta única, o escopo fica fixo.
- Sem `sector` na API, a busca é conjunta, não graduação inferida. A UI sempre transmite a seleção. A API padrão usa o perfil conjunto; perfis/índices legados são preservados.
- `--questions-file` lê somente as linhas numeradas, sem transmitir respostas, rótulos, evidências ou setor gold. `--output` cria JSONL novo, registra erro por consulta e recusa sobrescrita. Interrupção de lote retorna código não zero e preserva registros parciais.

## Exploração predefinida

As mesmas 20 perguntas da pós V2, na apresentação numerada original, e as mesmas 20 da graduação. Não eliminar itens difíceis, mudar gold ou repetir seletivamente respostas após inspeção.

1. Pós: 20 perguntas com seleção prévia `pos_graduacao`.
2. Graduação: 20 perguntas com seleção prévia `graduacao`.
3. Ambas: as duas listas completas, 40 perguntas com seleção prévia `ambos`.

São 80 consultas, usando a mesma coleção conjunta e filtros distintos, **não três índices físicos separados**. Portanto o contraste é escopo filtrado versus não filtrado nesse índice aproximado; não é réplica exata do piloto 003. Os corpora já indexados são reutilizados. As consultas são embeddadas novamente a cada requisição normal da API, sem afirmar identidade bit a bit dos vetores entre chamadas.

Concluir e registrar os dois lotes filtrados antes dos lotes conjuntos. Duas listas em paralelo por fase são aceitáveis para esta exploração operacional; registrar ordem, limites de concorrência e códigos de saída. Isso não controla deriva temporal do provedor. Uma repetição, amostra intencional de desenvolvimento e gold candidato limitam a inferência; não é teste confirmatório independente nem avaliação de agentes.

O escopo dos lotes filtrados é fornecido pelo operador por construção. Não se mede taxa de acerto de roteamento nem custo/erro de um futuro roteador automático. A pergunta continua sem indicação extra de curso pessoal, mesmo no escopo filtrado; a ação esperada das ambiguidades V2 não é alterada retroativamente.

## Métricas e revisão

Aplicar os qrels V2 existentes por par (norma, artigo), incluindo alternativas previamente declaradas. Nas respondíveis: Recall@1/3/5, Hit@k, MRR@5, nDCG@5, cobertura completa@5 e fração de outra norma. Denominadores previstos por condição: pós 16 e graduação 6. Nas ambiguidades (4 pós, 14 graduação), avaliar esclarecimento separadamente por revisão, sem Recall normativo.

Se a API falhar na geração sem devolver os trechos, a recuperação dessa consulta é **não observada**, não Recall zero. Registrar erros e o denominador observado das métricas. Não excluir silenciosamente tais itens da contagem total ou imputar qualidade normativa.

Referência fora do escopo escolhido é diferente de indisponibilidade HTTP: viola o contrato da condição. A UI conserva o resultado bruto com erro e não o apresenta como resposta válida. O auditor rejeita a execução inteira nesse caso, mesmo com erro registrado, em vez de publicar médias de uma condição que o servidor não respeitou. Arquivos incompletos ou perguntas alteradas também são violações fatais; os dados brutos continuam disponíveis para diagnóstico.

A rubrica 0/1/2 já aprovada permanece: 0 erro/não resposta; 1 incompleta sem erro material ou correta sem evidência necessária; 2 correta, completa e fundamentada. Campos de revisão ficam nulos. Recuperação completa não equivale à nota 2 e não valida as citações geradas. Não atribuir nota por busca de palavras, nem usar respostas corrigidas manualmente no lugar das saídas.

A separação entre recuperação, fidelidade e geração é motivada por [RAGAs (Es et al., 2024)](https://aclanthology.org/2024.eacl-demo.16/); correção de resposta e suporte de citações por [ALCE (Gao et al., 2023)](https://aclanthology.org/2023.emnlp-main.398/). As métricas de ranking seguem [Manning et al., avaliação de recuperação ordenada](https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html). Não estamos executando as bibliotecas RAGAs/ALCE, e esses trabalhos não validam nossa divisão de 20 perguntas ou escolhas de engenharia.

## Histórico e auditoria

`cli_001/002/003` são rodadas anteriores de desenvolvimento. O CLI alternativo introduziu inferência de setor, esclarecimento determinístico e/ou reescrita, além de prompt diferente. Seus resultados não representam o fluxo agora solicitado e não são uma comparação causal com o terminal corrigido. Preservar arquivos e manifestos, sem corrigir respostas retroativamente ou transferir seus escores para nova execução.

O relatório da nova exploração fica em `results/terminal_ui_001/REPORT.md`, com manifesto, respostas brutas e auditoria próprios. O relatório e os bytes históricos de `pilot_003` não serão reescritos como se tivessem usado a nova UI. Nenhuma conclusão geral de insuficiência de RAG ou superioridade de agentes está predefinida.

`terminal_ui_001` foi executado com o código `5f281a15eab549d15cea429498bd1a4322c15a3f`, que reapresentava o menu a cada pergunta interativa. A correção posterior para manter o escopo na sessão altera somente a navegação interativa; não altera o contrato de recuperação, o prompt ou o escopo fixo dos lotes. Os registros e métricas daquela execução permanecem históricos, sem reexecução ou atribuição retroativa desta navegação.

Notas editoriais/autoria e exploração de desenvolvimento não fazem parte dos artefatos técnicos. Dados, configuração, decisões técnicas, auditoria e resultados verificáveis são artefatos versionáveis. Novos testes seguem locais/ignorados por orientação do projeto.

## Verificação da navegação persistente — 2026-10-20

As contagens abaixo são resultados registrados da execução histórica de 2026-10-20. Foram preservadas como parte do registro do experimento e não foram revalidadas na criação dos `execution_snapshot/`.

Executado em `code/`, via `uv run --no-sync`:

- `pytest -q tests/rag_baseline/test_terminal_scope.py`: 17 aprovados. Inclui persistência do escopo, troca explícita, entrada vazia, falha de consulta e troca do escopo inicial definido por argumento.
- `ruff check` e `ruff format --check` sobre o terminal e seu arquivo de testes: aprovados.
- `pytest -q`: duas execuções com 157 aprovados, 2 ignorados e 1 falha, em 112,61 s e 76,96 s. A falha em ambas foi `tests/app/test_streamlit_app.py::test_app_simple_non_streaming`, por timeout de 10 s na inicialização do Streamlit legado, antes de enviar pergunta.
- O teste Streamlit repetido junto com os testes do terminal passou: 18 aprovados em 13,84 s. Isso não resolve nem identifica conclusivamente a causa da falha na suíte completa; essa limitação permanece aberta. Não foram alterados o Streamlit nem seu timeout.

Esses testes verificam o software, não atribuem qualidade normativa às respostas. Os novos testes permanecem locais/ignorados; nenhum resultado experimental foi reescrito ou produzido nesta correção.

## Uso a partir de code/

Terminal 1:

```powershell
uv sync --frozen
uv run python -m rag_baseline.index --profile duas-regulacoes
uv run uvicorn rag_baseline.api:app --host 127.0.0.1 --port 8080
```

Terminal 2:

```powershell
uv run python -m rag_baseline.demo --verbose
uv run python -m rag_baseline.demo --setor pos_graduacao --question "Quantos créditos preciso no mestrado?"
uv run python -m rag_baseline.demo --setor ambos --questions-file ../data/questoes_para_avaliar_o_agente_pos_graduacao.md --output respostas_novas.jsonl
```

`rag_baseline.chat` é alias da mesma UI, não outro serviço. `voltar` retorna à seleção de escopo; `sair` encerra. Arquivos de saída devem ter nomes novos; a chave permanece exclusivamente no ambiente local. A nova API padrão consulta o índice conjunto; o comando de indexação sem perfil continua o legado da graduação, portanto usar o perfil explícito mostrado acima.
