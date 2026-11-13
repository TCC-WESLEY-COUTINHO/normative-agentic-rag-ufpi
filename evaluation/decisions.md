# Justificativas e limites das decisões

Registro explicativo complementar, escrito durante o piloto; não altera o protocolo congelado nem define novos desfechos primários após observar resultados. Referências completas em [references.bib](references.bib).

## Decisões da V1 (preservadas)

| Decisão | Justificativa verificável | Limitação / comparação ainda necessária |
|---|---|---|
| Preservar gabarito original e criar derivado auditável | Mantém proveniência das correções de artigos, condições e exceções; cada item contém texto da evidência extraída | Conferência com OCR não substitui PDF ou dois anotadores independentes |
| 20 perguntas por nível, escopo explícito | Reproduz tamanho e estilo do arquivo original; evita penalizar pós por perguntas sem nível enquanto graduação tem escopo implícito | Amostra intencional e de desenvolvimento; tamanho não decorre de poder estatístico |
| Separar recuperação, geração e citação | RAGAs (Es et al., 2024) distingue dimensões do pipeline; ALCE (Gao et al., 2023) avalia qualidade e suporte de citações | Não executamos essas bibliotecas; rubrica local necessita validação |
| Unidade de relevância `(norma, artigo)` | A mesma numeração existe nas duas resoluções; relevância precisa identificar o documento | Artigo inteiro pode ser maior que a menor evidência necessária; qrels parciais |
| Recall@5 primário, MRR/nDCG secundários | Avaliação de cobertura e ordenação baseada em relevância (Manning et al., 2008) | Encontrar artigo não implica resposta correta; métricas não estabelecem suficiência de uso real |
| Top-k=5, chunks por artigo, embedding e LLM fixos | Mantém escolhas da baseline e limita variáveis alteradas; mesma consulta/vetores para cada par | Conveniência experimental, não configuração ótima comprovada; comparar k, chunking e modelos futuramente |
| Chroma e recuperação densa sem reranker | Reutiliza implementação existente, permitindo baseline reproduzível com poucas mudanças | Escolha de engenharia, não evidência de superioridade sobre busca híbrida ou outros bancos |
| Índice isolado com norma correta versus conjunto | Controla a inclusão de documentos de outra norma; escopo isolado é fornecido por construção | Controle oracle não mede custo/erro de um roteador real; os índices usam busca aproximada |
| Prompt neutro idêntico e temperatura zero | Evita induzir respostas de graduação para perguntas da pós e reduz variação configurável | Provedor pode continuar não determinístico; uma repetição não estima variabilidade de geração |
| Preservar ordem do contexto | A posição pode afetar o uso da evidência (Liu et al., 2024) | O piloto não manipula posições; não permite atribuir causalmente falha ao efeito de posição |
| Diferença pareada e bootstrap estratificado | Compara a mesma pergunta nas duas condições; reamostragem é fundamentada na família bootstrap (Efron, 1979) | 5.000 reamostragens/semente 956 são parâmetros operacionais; dependência entre itens e amostragem intencional limitam generalização |
| Dois anotadores e concordância | Cohen (1960) fornece coeficiente para categorias nominais; acordo não é sinônimo de verdade | Kappa, acurácia e escores humanos ainda não calculados; correção ordinal exige pesos definidos previamente |
| Manter resultados desfavoráveis à hipótese | Evita selecionar erros para sustentar conclusão predeterminada | Bom desempenho neste piloto também não certifica segurança universal |

As publicações fundamentam os métodos e dimensões, não comprovam antecipadamente a adequação jurídica ou a superioridade desta arquitetura. Decisões de conveniência devem ser apresentadas como tal no TCC. Não há base para retroativamente afirmar que cada escolha já existente no projeto foi validada academicamente.

## Revisão V2 aprovada antes da execução

O protocolo aplicável à nova execução é [protocol_v2.md](protocol_v2.md), congelado no commit `c6af890`. A tabela anterior descreve V1; o escopo explícito nas perguntas não se aplica à V2.

| Decisão V2 | Justificativa | Limite |
|---|---|---|
| Perguntas cotidianas sem prefixar resolução/setor | Aproxima o estilo do arquivo original; evita fornecer ao sistema o roteamento que se quer observar | Perguntas sintetizadas não são logs de usuários reais |
| Pós 8 diretas, 8 abertas, 4 ambíguas | Cobre fatos delimitados, síntese/condições e necessidade de esclarecimento | Proporção operacional aprovada, não distribuição populacional nem poder estatístico |
| Preservar 20 perguntas da graduação | Mantém comparação auditável com o material de origem | Não impor artificialmente o balanceamento 8/8/4 à graduação |
| Esclarecimento separado de acerto normativo | [AmbigQA](https://aclanthology.org/2020.emnlp-main.466/) e [Lee et al.](https://aclanthology.org/2023.findings-emnlp.772/) motivam tratar ambiguidade explicitamente | Classificação provisória, pendente de adjudicação humana |
| Frequência comum não exige escolher setor | Ambos os regulamentos sustentam 75%; qrels alternativos fixados antes da geração | Não generalizar equivalência a outras regras; a origem de outra norma não implica erro nesse item |
| Rubrica ordinal 0/1/2 | Decisão aprovada pelo usuário: distinguir erro, incompletude/falta de evidência e resposta completa fundamentada | Não converter presença de artigo automaticamente em nota; revisão de conteúdo necessária |
| Setor explícito, ausência desconhecida | Evita inferência silenciosa de graduação e permite filtrar as duas modalidades de busca | Banco Supabase legado não é automaticamente enriquecido; piloto usa Chroma |
| Mesmo prompt e vetores reutilizados nas três condições | Controla instruções e embeddings entre pares | Não elimina variabilidade/deriva temporal do provedor; apenas uma repetição |
| Metadados com máximo global 10 | Preserva limite solicitado, inclusive união de duas fontes | É busca limitada, não exaustividade normativa; baseline experimental permanece top-k=5 |
| Prosseguir ao conjunto sem corte mínimo (opção 2) | Evita selecionar só perguntas com bom desempenho isolado | Análise primária e falhas ficam registradas; o experimento não parte de conclusão predeterminada |
| Conservar V1 e tentativas interrompidas | Preserva histórico e impede sobrescrita seletiva de resultados | V1 versus V2 não isola efeito de setor: dataset, prompt e fontes mudaram |

As decisões V2 não demonstram superioridade de um agente. O piloto mede uma baseline densa com metadados no embedding/contexto; filtros das ferramentas são verificados em testes de contrato, não em experimento agêntico ao vivo. É necessária uma ablação própria para medir o efeito dos metadados e do roteamento.

## Gabarito da pós com escopo previamente conhecido — revisão 1 (2026-10-20)

Identificador desta revisão: `pos_escopo_conhecido_r1`. Arquivo: [questoes_para_avaliar_o_agente_pos_graduacao.md](../data/questoes_para_avaliar_o_agente_pos_graduacao.md). O escopo de pós-graduação é uma premissa declarada da avaliação, como ocorre com o escopo de graduação no gabarito original; não é uma inferência obtida do setor dos trechos recuperados.

- Preservados integralmente os itens 1–16 e as perguntas 17–18.
- Os itens 17–20 agora esperam resposta normativa direta, com evidência nos arts. 21, I; 38; 37; e 20, § 3º, respectivamente, em vez de perguntar o nível do curso. Essas regras não exigem distinguir mestrado de doutorado.
- No item 19, explicitar “essa mesma matéria” delimita a regra de repetição do cancelamento. No item 20, “nota final” evita confundir nota parcial com resultado final. A linguagem permanece cotidiana.
- A mudança é de contrato do gabarito, não de desempenho observado. Não foi motivada por seleção de respostas corretas ou incorretas; não produz novas notas nem altera a rubrica 0/1/2.

Esta apresentação deixa de ser uma reprodução literal da V2. `evaluation/datasets/pos_graduacao_v2.json` e `.md`, os protocolos congelados e todos os resultados históricos permanecem inalterados. A apresentação anterior pode ser recuperada no commit `806f710`, no mesmo caminho em `data/`; o manifesto de `terminal_ui_001` identifica o código e as entradas efetivamente utilizados naquela rodada. Não aplicar esta revisão retroativamente às métricas existentes nem usar os rótulos de esclarecimento da V2 para avaliar os quatro itens revisados.

Nenhum código, prompt, índice ou filtro foi alterado. O terminal atual transmite o escopo apenas como filtro de recuperação, sem informar ao modelo o nível pessoal do aluno. Antes de executar uma nova avaliação, será necessário alinhar e registrar como a premissa de escopo conhecido será disponibilizada ao sistema, com controles equivalentes entre condições. Uma avaliação conjunta sem nível informado exige gabarito próprio para ambiguidades; não reutilizar automaticamente estas respostas categóricas nesse cenário. A revisão permanece candidata à conferência normativa humana.

## Referências estatísticas complementares (V1 e V2)

- Efron, B. (1979). *Bootstrap Methods: Another Look at the Jackknife*. The Annals of Statistics, 7(1), 1–26. [Registro do artigo](https://www.jstor.org/stable/2958830). Referência fundadora da reamostragem bootstrap; não justifica por si só independência ou representatividade da amostra deste piloto.
- Cohen, J. (1960). *A Coefficient of Agreement for Nominal Scales*. Educational and Psychological Measurement, 20(1), 37–46. [DOI](https://doi.org/10.1177/001316446002000104). Referência do coeficiente nominal; não confundir concordância entre avaliadores com correção normativa.
