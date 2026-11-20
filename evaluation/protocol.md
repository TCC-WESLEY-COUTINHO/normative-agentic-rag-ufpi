# Protocolo do piloto: graduação e pós-graduação UFPI

> **Protocolo histórico.** As condições e comandos abaixo registram o experimento anterior à v3.4. Não descrevem a configuração atual; novas execuções exigem diretório de saída novo e os insumos da condição histórica. Veja [reprodução e limites](../docs/REPRODUCAO.md).

## Pergunta e hipótese

Pergunta: a inclusão de uma segunda resolução reduz a recuperação de evidências e a qualidade de respostas de uma baseline RAG densa, sem roteamento?

H1 operacional: para a mesma pergunta explicitamente contextualizada, o índice conjunto apresenta menor Recall@5 de evidências anotadas que o índice isolado. H0 operacional: não há redução detectável neste piloto. Resultados favoráveis ou contrários serão publicados, sem selecionar apenas erros. Não se pretende provar que toda arquitetura RAG é insuficiente nem que agentes são superiores. Um resultado negativo pode orientar comparações futuras (filtro de metadados, busca híbrida, reranking, roteamento, agentes), mas não as substitui.

Este protocolo e os datasets são congelados em commit antes da execução. Qualquer mudança posterior exige nova versão e novo piloto.

## Dados e padrão do gabarito

Origem: `data/questoes_para_avaliar_o_agente.md`, 20 perguntas e respostas. Padrão: linguagem cotidiana de aluno; perguntas diretas e condicionais; prazos, limites, listas e procedimentos; respostas curtas com condições; citações inconsistentes. Não há registro de amostragem, anotadores ou adjudicação no arquivo original. Sua mera existência não comprova validação.

`datasets/graduacao_v1.json` preserva perguntas/respostas originais e contém referência auditada separada. Correções relevantes: frequência arts. 111/112; exame final art. 116; cancelamento de disciplina art. 229; trancamento art. 287; trancamento de curso arts. 292/293; cancelamento por reprovações arts. 344/345; requisitos de láurea arts. 337/338. As referências antigas com números isolados não são assumidas como números de artigo. Ajustes materiais estão registrados por item.

`datasets/pos_graduacao_v1.json` contém 20 perguntas inéditas no mesmo estilo: rendimento/frequência, créditos, aproveitamento, cancelamento/trancamento, desligamento, proficiência, qualificação, defesa, estágio e diploma. O tamanho igual facilita a comparação e o custo inicial; não é cálculo de poder estatístico nem amostra representativa de todas as normas. O conjunto é intencional e de desenvolvimento, sem split artificial em apenas 40 itens.

Cada item registra ID, norma, categoria, pergunta original e com escopo, resposta de referência, fatos obrigatórios, artigos e texto da evidência, nota de auditoria e revisão. Todas as referências são **candidatas**, associadas ao corpus extraído; não constituem gold independente validado. Datas de vigência, remissões conflitantes, omissões e artefatos OCR exigem comparação por avaliadores com o PDF. A resolução 956 informa aplicação aos ingressantes a partir de sua publicação (art. 60); o piloto assume o público ao qual a versão fornecida se aplica, sem certificar legislação vigente em 2026.

Há 376 chunks da graduação e 62 da pós no snapshot esperado. O corpus da pós salta o art. 30; isso é limitação do snapshot e não licença para inventar texto. Nenhuma pergunta selecionada exige esse artigo. Referências distintas podem bastar para responder; os qrels são evidências conhecidas, não julgamento exaustivo de todos os trechos recuperáveis.

## Desenho controlado

- A: índice isolado da norma da pergunta, conhecida por construção (controle com escopo oracle).
- B: índice conjunto com ambas as resoluções, sem filtro, reranker ou agente.
- Mesma pergunta, embedding de consulta, modelo de resposta, temperatura zero, limite de tokens, prompt neutro e top-k=5 nas duas condições. Ordem das condições alternada por item; uma execução por par neste piloto.
- Embeddings calculados uma vez para o snapshot concatenado e reutilizados nas coleções A e B. Nomes e IDs das normas são preservados; fontes não são misturadas silenciosamente.
- Persistência experimental exclusiva em `code/.local/gold_pilot/`. Coleções de uso interativo ficam fora desse diretório.
- O prompt original dizia exclusivamente graduação. O experimental usa 'normas acadêmicas da UFPI' nas duas condições. Manter o prompt de graduação para pós seria um confundidor artificial. Fonte e artigo devem acompanhar afirmações; isso não torna uma citação automaticamente correta.
- As perguntas originais da graduação frequentemente omitem o nível. O escopo explícito é usado simetricamente na avaliação principal; perguntas ambíguas exigirão conjunto separado com comportamento esperado de esclarecimento, não penalização secreta por escolher a norma errada.
- 40 perguntas × 2 condições = 80 respostas. Essa é uma execução exploratória; variação do provedor, temperatura zero e uma repetição não garantem determinismo.

## Métricas automáticas de recuperação

Unidade de relevância: par `(norm_id, artigo)`, não somente número do artigo, pois as resoluções compartilham números. Resultados duplicados contam uma única vez para cobertura. Seja G o conjunto de evidências anotadas e R_k os primeiros k resultados.

- Recall@k = |G ∩ R_k| / |G|, para k=1,3,5. Métrica primária: média por pergunta de Recall@5.
- Hit@k = 1 se ao menos uma evidência de G aparece nos k resultados.
- Evidence-complete@5 = 1 se todas as evidências anotadas aparecem nos cinco resultados. Não implica resposta completa.
- Reciprocal rank@5 = inverso da posição da primeira evidência relevante; zero se não encontrada. A média é MRR@5.
- nDCG@5: relevância binária por par anotado; DCG = soma de rel_i/log2(i+1); normalização pelo ranking ideal com min(|G|,5) itens relevantes.
- Wrong-norm@5 = fração dos resultados recuperados de outra norma. Indicador de mistura de contexto, **não** prova de resposta errada.
- Médias estratificadas por graduação/pós e macrogeral (grupos com o mesmo tamanho). Diferença pareada B−A, com intervalo bootstrap percentil 95%, 5.000 reamostragens de perguntas dentro de cada nível, semente 956. Reportar tamanho amostral. Intervalos são descritivos condicionais à amostra intencional, não inferência sobre todos os usuários. Questões compartilham artigos; dependência pode tornar intervalos otimistas.

Qrels incompletos podem subestimar relevância. Não relatar precisão global como se houvesse julgamento exaustivo. Não usar limiares pós-hoc para declarar sucesso ou fracasso.

## Respostas e revisão

Salvar resposta integral, contexto ordenado, prompt, modelo informado pelo provedor, tempos, uso de tokens quando disponível, falhas e IDs das evidências. Token F1 com a referência é diagnóstico lexical secundário: ignora semântica, condições e negações, portanto **não mede correção normativa**. Métricas automáticas não substituem a anotação por avaliadores independentes. RAGAs/ALCE fundamentam dimensões de avaliação, mas não se afirma execução das suas implementações.

Para consolidar gold: dois avaliadores, independentemente, confrontam cada pergunta/resposta com o PDF, indicam a menor evidência suficiente, verificam ambiguidades e corrigem OCR; registram identidade, data e divergências, adjudicadas por terceiro ou consenso documentado. Congelar nova versão antes de avaliação confirmatória. Não preencher esses campos automaticamente.

Para avaliar geração, embaralhar pares anonimizados e ocultar condição/modelo até o fim. Rubrica por resposta: correção (0 incorreta, 1 parcial, 2 correta), cobertura de cada fato obrigatório (0/1), afirmação sem suporte (0/1 por afirmação) e mistura indevida de norma (0/1). Avaliar precisão das citações (citações que sustentam a afirmação / citações verificadas) e cobertura de citação (afirmações verificáveis com suporte citado / afirmações verificáveis). Coleção de referências retornada pelo retriever não equivale a citação emitida pelo LLM. Ausência de citação deve ser registrada separadamente; denominador zero não vira 100%.

Reportar concordância bruta e Cohen kappa para categorias nominais entre dois avaliadores; usar kappa ponderado explicitado se tratar correção 0–2 como ordinal. A rubrica e os anotadores devem ser descritos no TCC. Escores dos avaliadores e métricas de citação permanecem nulos até anotação. As perguntas desta V1 são respondíveis: não calcular taxa de abstenção correta ou segurança fora de escopo sem conjunto próprio.

## Fundamentação e limites da transferência

1. Manning, Raghavan e Schütze (2008), *Introduction to Information Retrieval*, cap. 8. [Avaliação de rankings](https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html). Fundamenta avaliação baseada em relevância, recall e ganho descontado. Aqui os qrels são por artigo e a amostragem é local.
2. Es et al. (2024), *RAGAs: Automated Evaluation of Retrieval Augmented Generation*, EACL Demo. [DOI 10.18653/v1/2024.eacl-demo.16](https://aclanthology.org/2024.eacl-demo.16/). Motiva separar recuperação, fidelidade ao contexto e qualidade da geração. Não prova validade jurídica nem substitui revisão de especialistas.
3. Gao et al. (2023), *Enabling Large Language Models to Generate Text with Citations*, EMNLP. [DOI 10.18653/v1/2023.emnlp-main.398](https://aclanthology.org/2023.emnlp-main.398/). Fundamenta verificar se a citação sustenta a afirmação e a cobertura das citações, em vez de apenas contar referências.
4. Liu et al. (2024), *Lost in the Middle: How Language Models Use Long Contexts*, TACL. [DOI 10.1162/tacl_a_00638](https://aclanthology.org/2024.tacl-1.9/). Mostra sensibilidade à posição do contexto em seus experimentos e motiva salvar a ordem recuperada; não demonstra que nosso corpus de dois regulamentos reproduz o mesmo efeito.

## Reprodução e proveniência

Executar com uv a partir de `code/`. O runner valida datasets, cria coleções experimentais, executa os pares e grava resultados JSON em diretório de execução novo (recusa sobrescrita). Snapshot inclui SHA-256 dos datasets, corpora, lockfile e código, commit e parâmetros. Os modelos usados são os registrados no manifesto, não inferidos depois. Segredos, headers de autenticação, `.env`, Chroma e caches não são evidências publicáveis.

`uv run python -m rag_baseline.experiment --output ../evaluation/results/pilot_001`

`uv run pytest tests/rag_baseline/test_experiment.py -q`

Antes de um teste confirmatório: revisão dos golds; itens novos independentes; hipóteses e critérios de suficiência definidos antes dos resultados; mais execuções/modelos e análise de poder. Não ajustar o dataset para que a baseline falhe. Caso a baseline tenha bom desempenho, esse resultado também deve integrar o TCC.
