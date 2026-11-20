# Análise primária — antes da busca em ambas

> **Registro histórico.** Configuração, resultados, contagens de testes e estados descritos referem-se à execução documentada, anterior à v3.4. Para a versão atual, consulte o [guia de evidências e reprodução](../../README.md).

As duas listas filtradas foram concluídas com 20 registros cada. Houve uma falha de transporte na pós e duas na graduação, registradas na UI sem trechos retornados; ambos os processos terminaram com código 1. São 37 respostas recebidas, não 40 respostas corretas.

Na pós, das 16 respondíveis, há evidência observável em 15: Recall@5 e cobertura completa@5 são 1,0000. Na graduação, das seis respondíveis, cinco têm evidência observável: Recall@5 0,9000 e cobertura completa@5 0,8000. Os itens com falha não recebem Recall zero por imputação. A fração de outra norma nas referências observadas é zero nos dois filtros. As 18 perguntas anotadas para esclarecimento permanecem fora dessas métricas.

Resultados calculados a partir das saídas reais com `experiment_v2.metrics_for` e qrels V2 preexistentes; valores e hashes estão em `primary_summary.json`. Isso valida o filtro e caracteriza a recuperação observada, mas não aprova automaticamente as respostas. Por exemplo, a primeira resposta da pós converte carga horária em uma quantidade de faltas sem duração da aula informada. Não foi corrigida nem substituída; a nota de conteúdo exige revisão.

Conforme o método predefinido e a opção anteriormente aprovada de não estabelecer corte mínimo, prosseguir às mesmas 40 perguntas com escopo ambas, sem excluir itens, repetir seletivamente falhas ou alterar prompt/parâmetros. O controle é filtro no mesmo índice conjunto; não índices físicos isolados. Esta análise e os hashes dos lotes filtrados serão preservados após a segunda fase.
