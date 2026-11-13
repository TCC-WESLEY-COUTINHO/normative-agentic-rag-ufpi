# Protocolo V2 — perguntas naturais, setor e ambiguidade

## Decisões aprovadas antes da execução

Pós: 20 perguntas cotidianas, sem prefixo de resolução: 8 diretas, 8 abertas, 4 ambíguas. A divisão é uma escolha operacional deste piloto, não estimativa de distribuição real nem cálculo de poder. Diretas pedem fatos delimitados em um artigo; abertas exigem explicação de procedimento ou combinação de condições (em um ou mais artigos). Ambíguas têm prioridade de classificação quando falta o nível do curso e há interpretações normativas diferentes.

Graduação: manter literalmente as 20 perguntas originais, sem impor retrospectivamente 8/8/4. No universo destes dois regulamentos, IRA, Exame Final e Láurea são pistas de graduação; 5 perguntas têm essas pistas. A pergunta de frequência também é respondível sem escolher setor, porque a regra de 75% é comum. As outras 14 são anotadas como dependentes de esclarecimento do nível para aplicar a resposta condicionada. Essa classificação não estima a frequência de ambiguidade em produção. Não comparar os níveis como amostras de dificuldade equivalente.

Os 40 itens são candidatos a gold. A V1 e pilot_001 são preservados. A V2 é conjunto de desenvolvimento, influenciado pela inspeção da V1, não teste confirmatório independente. A conferência visual de evidências da pós contra o PDF não equivale a revisão por dois especialistas. As perguntas, fatos e referências devem ser revisados antes de uso confirmatório.

## Três condições, duas fases

1. Índice isolado da pós: 20 perguntas da pós, 62 chunks.
2. Índice isolado da graduação: 20 perguntas originais, 376 chunks.
3. Índice conjunto: as mesmas 40 perguntas, 438 chunks.

Concluir a pós isolada primeiro; registrar a análise primária dos isolados; depois executar o conjunto. **Não exigir percentual mínimo nem eliminar perguntas por desempenho.** Erros de dados/código devem ser relatados; uma correção após congelamento exige nova execução/versão, não substituição silenciosa de resultados. Fazer a comparação de todos os itens, inclusive erros e ambiguidades.

Esta execução usa a baseline densa Chroma, não o loop agêntico Supabase. Setor e fonte aparecem nos embeddings e contextos de ambas as condições. O conjunto não recebe filtro derivado do rótulo gold. O isolado é controle de escopo oracle por construção; não demonstra competência de roteamento. A disponibilidade de filtros nas ferramentas semântica/por metadados é validada em testes separados; este piloto não mede benefício causal de agentes ou da inclusão de metadados. Isso requer ablação controlada futura com/sem setor.

## Controle de confundidores

Mesmo system prompt neutro, byte a byte e com SHA-256, nas três condições; mesmo modelo, temperatura zero, limite de geração, top-k=5 para a baseline e embeddings calculados uma vez/reutilizados. Fonte da graduação recebe identificação da resolução no corpus derivado, mantendo o texto normativo original. Nenhuma pergunta recebe prefixo técnico, referência, categoria, setor esperado, resposta gold ou histórico inventado.

Uma pergunta ambígua continua ambígua mesmo no índice isolado: corpus disponível não informa o nível pessoal do aluno. O comportamento esperado é pedir esclarecimento, sem escolher uma regra categórica. Não simular segundo turno nesta execução. Os artigos associados às ambíguas sustentam apenas a resposta **condicionada** ao nível, não uma exigência de recuperar aqueles artigos para fazer a pergunta de esclarecimento.

Ordem fixa isolados → conjunto é exigência do fluxo aprovado e pode introduzir confundimento temporal do provedor; uma repetição não mede variabilidade. Não comparar V1 versus V2 como efeito isolado de setor: perguntas, prompt e apresentação de fonte também mudaram.

## Avaliação 0/1/2 aprovada pelo usuário

| Nota | Pergunta respondível |
|---|---|
| 0 | Erro material ou não respondeu. |
| 1 | Resposta incompleta sem erro material; ou correta, mas sem recuperar os trechos necessários do gold. |
| 2 | Correta e completa, cobrindo os fatos obrigatórios com evidências gold recuperadas suficientes. |

Erro material prevalece. Registrar separadamente correção, completude, cobertura por fato e recuperação para não atribuir toda falha ao retriever. Trecho alternativo potencialmente válido deve ir para adjudicação dos qrels; não fingir que as referências são exaustivas nem alterar o mesmo teste depois de ver a saída.

Ambíguas: 2 quando pede o nível necessário sem antecipar conclusão normativa; 1 quando o esclarecimento é incompleto, sem erro material; 0 quando assume nível/aplica regra incorreta ou não faz o esclarecimento necessário. Taxa de esclarecimento adequado é separada da taxa de acerto normativo; não agregar as duas como se fossem tarefas idênticas.

Recuperação automática: Recall@1/3/5, Hit@k, MRR@5, nDCG@5, cobertura completa@5 e fração de outra norma, usando par `(norma, artigo)`. **Excluir ambíguas dessas métricas normativas**, mostrando o denominador: pós 16, graduação 6. Registrar resultados por categoria e por nível. Nos pares respondíveis calcular diferença conjunto − isolado e bootstrap percentil 95%, 5.000 reamostragens/semente 956 por nível, com limites de dependência/amostra intencional já descritos na V1. Não chamar recall de acurácia.

Notas 0/1/2 exigem julgamento de conteúdo; campos de avaliação ficam nulos. Não inferir nota 2 apenas porque Recall@5=1. Para avaliação acadêmica independente, dois anotadores revisam respostas e PDFs sem acesso à condição; adjudicam divergências; reportar acordo/kappa conforme protocolo V1.

## Metadados e buscas

Contrato JSON bruto: `metadados.setor` em `graduacao|pos_graduacao`; modelos internos Chroma: `sector`. Ausente significa desconhecido, não graduação. Hierarquia conceitual: setor → fonte/norma → níveis presentes → artigo. A pós tem capítulos sem títulos; a validação não pode exigir título inexistente. Mesmos números de artigo em normas diferentes não são IDs iguais.

Supabase semântico: `setor`, `fonte` OU `fontes` opcionais; sem escopo não adicionar filtro de graduação. Preservar limite semântico existente de 4. Metadados: limite **global 10**, inclusive quando duas fontes são consultadas; consultar cada fonte usando contrato de igualdade existente e intercalar resultados por posição. Não alegar busca exaustiva. Falhas de uma fonte não viram resultado completo silenciosamente. Na condição pós usar a fonte da pós; na geral as duas fontes explicitamente. Banco Supabase existente não é migrado/destruído automaticamente; nova carga precisa consumir os corpora enriquecidos e RPCs compatíveis.

## Fundamentação

As dimensões recuperação/geração/citações seguem a motivação de RAGAs e ALCE, e as métricas de ranking seguem Manning et al.; referências e limites em [protocolo V1](protocol.md) e [decisões](decisions.md).

- Min et al. (2020), [AmbigQA](https://aclanthology.org/2020.emnlp-main.466/), trata múltiplas interpretações plausíveis e desambiguação de perguntas. Motiva anotar ambiguidade, sem transferir seus resultados numéricos para a UFPI.
- Lee et al. (2023), [Asking Clarification Questions to Handle Ambiguity in Open-Domain QA](https://aclanthology.org/2023.findings-emnlp.772/), investiga perguntas de esclarecimento. Motiva a ação `clarify`; nossa rubrica 0/1/2 e divisão 8/8/4 são decisões locais, não reproduções de métricas desses papers.

## Reprodução (uv, a partir de code/)

```powershell
uv run python -m rag_baseline.experiment_v2 --validate-only
uv run python -m rag_baseline.experiment_v2 --output ../evaluation/results/pilot_002 --stage isolated
# Inspecionar primary_summary.json e respostas; registrar análise sem mudar configuração.
uv run python -m rag_baseline.experiment_v2 --output ../evaluation/results/pilot_002 --stage combined
```

O manifesto congela datasets, corpora, código, lockfile, prompt e modelos; a segunda fase rejeita alterações. Resultados e recibos são preservados, sem segredos. O cache local de vetores tem hash e não é versionado. Uma nova execução usa outro diretório; não sobrescrever piloto existente. Perfis CLI adicionais: `graduacao-setor-v2` e `pos-graduacao-setor-v2`; os perfis antigos continuam disponíveis para os corpora originais.

### Evidências equivalentes pré-definidas

GRAD2-004 (média final): art.111 OU conjunto art.117+118 são suficientes. A V1 já havia identificado art.118 como pertinente; incorporá-lo antes da V2 evita repetir um falso negativo conhecido. Esta é mais uma razão para tratar V2 como desenvolvimento, não teste independente.

GRAD2-002 (frequência): art.111 OU art.112 da graduação OU art.20 da pós sustentam independentemente o fato comum. `alternative_evidence_sets` explicita os três conjuntos suficientes; para cada métrica de relevância usar o máximo entre conjuntos (não exigir os três simultaneamente). `wrong_norm_at_5` continua indicando apenas origem diferente do dataset, não erro normativo: nesse item outra norma pode ser evidência válida. Alternativas fixadas antes da geração.
