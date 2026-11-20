# Protocolo do teste de campo — assistente normativo (RAG) para normas acadêmicas da UFPI

Versão 1.4 (publicada, 2026-11-20). Histórico: versões 1.0 a 1.3 (2026-11-19 e 2026-11-20), de trabalho; versão 1.4, publicada.

Materiais complementares:

- [`QUESTOES.md`](QUESTOES.md) — enunciados das 20 questões (10 do grupo de graduação e 10 do grupo de pós-graduação).
- [`data/resolucoes/`](../../data/resolucoes/) — PDFs das resoluções entregues aos participantes, os mesmos usados pelo assistente.
- O gabarito (resposta, dispositivos e critérios de acerto por questão) é de uso interno da pesquisa e não é publicado nem divulgado aos participantes.

---

## 1. Objetivo e perguntas de pesquisa

Comparar, com estudantes da UFPI, a consulta **manual** aos PDFs das resoluções com a consulta **mediada pela ferramenta** (assistente normativo baseado em RAG) quanto a acerto, tempo de resposta e percepção de uso, e observar o comportamento da ferramenta em uso real.

- **PQ1 (acerto).** Os participantes acertam mais com a ferramenta do que consultando apenas os PDFs?
- **PQ2 (tempo).** O tempo médio por resposta é menor com a ferramenta do que com a consulta manual?
- **PQ3 (percepção).** Como os participantes avaliam a agilidade, a confiança, a clareza, a utilidade das referências e a usabilidade da ferramenta?
- **PQ4 (comportamento).** Com que frequência a ferramenta responde corretamente, erra, recusa ou pede esclarecimento, e como isso afeta a resposta final do participante?

## 2. Hipóteses

Testes bilaterais, com α = 0,05:

- **H1₀:** a mediana das diferenças de pontuação (ferramenta − manual) por participante é zero.
- **H2₀:** a mediana das diferenças de tempo médio por resposta (ferramenta − manual) por participante é zero.

PQ3 e PQ4 são descritivas, sem teste de hipótese.

## 3. Desenho

- **Intra-sujeitos (pareado):** cada participante responde às mesmas 10 perguntas nas duas condições.
- **Ordem fixa:** primeiro a Etapa 2 (consulta manual, só com os PDFs); depois a Etapa 3 (com a ferramenta). A numeração acompanha a do instrumento de coleta.
- **Dois grupos independentes**, cada um com seus documentos e suas perguntas:

| Grupo | Participantes | Documentos (PDF) | Questões |
|---|---|---|---|
| Graduação | 10 | Res. 177/2012 CEPEX/UFPI (consolidada) + Res. 1.056/2026 CEPEX/UFPI | G01–G10 |
| Pós-graduação | 10 | Res. 956/2025 CEPEX/UFPI (vigente) + Res. 658/2024 CEPEX/UFPI (revogada) | P01–P10 |

- **PDFs:** os mesmos arquivos usados pelo assistente, em [`data/resolucoes/`](../../data/resolucoes/) — graduação: [`resolucao_177_2012_cepex_consolidada_2023.pdf`](../../data/resolucoes/resolucao_177_2012_cepex_consolidada_2023.pdf) e [`resolucao_1056_2026_cepex.pdf`](../../data/resolucoes/resolucao_1056_2026_cepex.pdf); pós-graduação: [`resolucao_956_2025_cepex.pdf`](../../data/resolucoes/resolucao_956_2025_cepex.pdf) e [`resolucao_658_2024_cepex.pdf`](../../data/resolucoes/resolucao_658_2024_cepex.pdf).
- **Unidade de análise:** o participante (pontuação e tempo médio em cada condição); a questão serve à análise descritiva.
- **Instrumento:** site de coleta próprio, com um endereço por grupo, uma pergunta por página, respostas definitivas e sem retorno, e tempo registrado pelo servidor. A ferramenta é usada em versão congelada durante toda a coleta.

## 4. Participantes

**Inclusão:** estudante regularmente matriculado na UFPI, em curso de graduação (grupo de graduação) ou em mestrado ou doutorado stricto sensu (grupo de pós-graduação), de qualquer período; idade mínima de 18 anos; aceite do termo de consentimento; familiaridade básica com computador e leitor de PDF. O período cursado é informado no perfil e usado só na descrição da amostra.

**Exclusão:** participação no desenvolvimento, na anotação, no gabarito ou no piloto da ferramenta ou deste protocolo; uso da ferramenta antes do teste; atuação profissional em secretaria acadêmica, coordenação ou elaboração de normas; na pós-graduação, matrícula apenas como aluno especial.

**Recrutamento e identificação:** amostra de conveniência, convidada por intermédio de docentes do departamento, com 10 participantes por grupo. Cada participante recebe no dia um código (`PART-G01` a `PART-G10`; `PART-P01` a `PART-P10`), válido para uma única participação. Não se cria lista que ligue código e pessoa.

## 5. Sessão

Sessão presencial, única por grupo, com 1 hora de duração e todos os participantes ao mesmo tempo, cada um em seu computador, conduzidos por um aplicador.

- **Graduação:** 24/11/2026, das 14h às 15h, no laboratório Leg01.
- **Pós-graduação:** 24/11/2026, das 16h às 17h, na sala da pós-graduação.

| Bloco | Duração de referência | Graduação | Pós-graduação |
|---|---|---|---|
| 1. Boas-vindas, termo de consentimento e perfil | 5 min | 14h00–14h05 | 16h00–16h05 |
| 2. Etapa 2 — 10 perguntas só com os PDFs | cerca de 22 min | 14h05–14h27 | 16h05–16h27 |
| 3. Intervalo, demonstração e preparação da ferramenta | 5 min | 14h27–14h32 | 16h27–16h32 |
| 4. Etapa 3 — as mesmas 10 perguntas com a ferramenta | cerca de 20 min | 14h32–14h52 | 16h32–16h52 |
| 5. Questionário pós-teste, com a SUS | 8 min | 14h52–15h00 | 16h52–17h00 |

1. **Boas-vindas, termo e perfil.** Apresentação do teste, entrega dos códigos, aceite do termo de consentimento e preenchimento do perfil (período, frequência de consulta às normas e de uso de assistentes, leitura prévia das resoluções). A recusa encerra a participação sem coleta de dados.
2. **Etapa 2 — consulta manual.** Respostas curtas, com o próprio texto do participante, consultando só os PDFs (busca no leitor permitida); sem internet, outros assistentes ou colegas. Indicar o artigo que fundamenta a resposta é opcional, e "não sei" é aceito. Dúvidas de conteúdo não são respondidas pelo aplicador.
3. **Intervalo, demonstração e preparação.** Começa quando todos concluem a Etapa 2 ou, no máximo, ao fim do tempo de referência dessa etapa. Demonstração da ferramenta com uma pergunta fora do conjunto de teste e orientações de uso (não digitar dados pessoais, reformular à vontade, responder a pedidos de esclarecimento). Quem ainda estiver na Etapa 2 continua sem interrupção e recebe as orientações individualmente ao concluí-la.
4. **Etapa 3 — com a ferramenta.** Antes das perguntas, o site apresenta um **passo de preparação**: o participante abre a ferramenta em outra aba, entra com o e-mail institucional e confirma no site; o tempo da etapa só começa a contar **após essa confirmação**. Os PDFs ficam **fechados** na Etapa 3, e as respostas da Etapa 2 não podem mais ser alteradas. Em cada pergunta, além da resposta final, o participante indica o que a ferramenta fez (respondeu, pediu esclarecimento, recusou, deu erro), a origem da resposta (ferramenta, ferramenta e lembrança da etapa manual, ou só lembrança) e o número de consultas.
5. **Questionário pós-teste.** Apresentado pelo site após a última pergunta da Etapa 3 (seção 7).

**Tempo e encerramento.** Não há limite de tempo por pergunta nem por etapa, mas a sessão termina no horário fixo (15h na graduação; 17h na pós-graduação). O aplicador avisa 10 min antes do fim de referência de cada etapa e do fim da sessão. No horário de término, a coleta é encerrada: a questão em curso e as não alcançadas ficam como **"não respondida"**, tratadas como dado ausente — não têm tempo, não são corrigidas e não se confundem com "não sei", que é resposta enviada e conta como erro.

**Piloto:** uma sessão por grupo, com 1–2 pessoas fora da amostra, para calibrar tempos, clareza das perguntas e fluxo do site; os resultados não entram na análise.

## 6. Privacidade e consentimento

A coleta segue os princípios de finalidade e necessidade da LGPD (Lei nº 13.709/2018).

- **Anonimato:** o participante é identificado apenas pelo código. Não são coletados nome, matrícula, CPF, e-mail, telefone, IP ou identificador do navegador.
- **Login institucional:** o acesso ao site exige o e-mail @ufpi.edu.br, usado só para liberar a entrada e não registrado junto às respostas.
- **Sem gravação** de tela, áudio ou vídeo.
- **Voluntariedade:** é possível pular perguntas ou desistir a qualquer momento, sem justificativa e sem prejuízo; as respostas já enviadas são mantidas.
- **Guarda:** os dados, anônimos, ficam em local de acesso restrito ao pesquisador e ao orientador, fora de qualquer repositório, e são mantidos por prazo indeterminado, apenas para fins acadêmicos.

**Termo de Consentimento Livre e Esclarecido (resumo).** O termo convida o estudante a testar uma ferramenta que responde dúvidas sobre normas acadêmicas da UFPI, no âmbito do Trabalho de Conclusão de Curso. Informa que serão respondidas 10 perguntas, primeiro com os PDFs e depois com a ferramenta, seguidas de um questionário, em cerca de 1 hora; que não se trata de prova e que o desempenho não é associado ao participante; que os riscos são mínimos (cansaço ou desconforto por não saber uma resposta); que as perguntas digitadas na ferramenta são registradas junto ao código, e por isso não se devem digitar dados pessoais; e que os dados são usados de forma agregada, sem benefício direto ao participante. O termo completo é apresentado no início da sessão, e só participa quem o aceita.

## 7. Medidas

**Acerto.** Cada resposta é classificada pelo gabarito em acerto total (1 ponto: conclusão correta com todos os elementos essenciais), acerto parcial (0,5: conclusão correta com elemento essencial ausente ou inexato, ou elementos corretos sem a conclusão) ou erro (0: conclusão errada, norma revogada aplicada a pergunta sobre a regra vigente, "não sei", em branco ou fora do tema). Citar o dispositivo não é exigido; o dispositivo citado é registrado como medida secundária. Informação extra errada que mude a orientação ao estudante rebaixa a classe em um nível; valores numéricos (prazos, créditos, notas) devem estar exatos. A pontuação por participante e etapa vai de 0 a 10 (média dos pontos × 10).

**Correção cega.** As respostas das duas etapas são exportadas sem etapa e sem código, embaralhadas e identificadas por um ID aleatório, com a chave de reidentificação guardada à parte; a classificação pelo gabarito é feita sem acesso à etapa nem ao participante, e a chave só é usada depois de todas as respostas classificadas. A resposta da própria ferramenta, extraída dos registros, é corrigida pelo mesmo gabarito (com as classes adicionais recusa e esclarecimento sem resposta final), o que dá uma medida de acurácia da ferramenta livre do efeito de aprendizado (PQ4).

**Tempo.** Medido pelo servidor do site para cada participante, etapa e questão: envio da resposta menos exibição da página, sem valores do navegador. Na Etapa 3, a medição começa na confirmação do passo de preparação, de modo que o login não entra no tempo. O tempo médio por resposta é a média dos tempos das questões respondidas (com a mediana também reportada). Interrupções técnicas registradas são descontadas.

**Proporção respondida.** Por grupo e etapa, a proporção de questões respondidas e a de participantes com as 10 questões respondidas, além do número de "não respondida" por questão.

**Percepção (PQ3).** Questionário pós-teste com:

- **SUS (System Usability Scale)**, 10 itens de 1 a 5, sobre a ferramenta (não sobre o site), na tradução para o português brasileiro de Lourenço, Carmona e Lopes (2022) da escala de Brooke (1996); escore de 0 a 100, calculado só com os 10 itens respondidos;
- **8 itens Likert** (1 = discordo totalmente a 5 = concordo totalmente) sobre agilidade, confiança, clareza, utilidade das referências, facilidade de formular perguntas, compreensão de recusas e esclarecimentos, dificuldade da consulta aos PDFs e intenção de uso;
- **5 perguntas abertas**, opcionais, sobre agilidade, confiança, clareza, episódios de erro, recusa ou esclarecimento, e melhorias.

**Registros da ferramenta.** Por consulta: código do participante, horários e latência, pergunta, resposta, referências exibidas e desfecho (respondeu, pediu esclarecimento, recusou ou erro técnico). Não se registram IP, cookies, nome, e-mail, matrícula nem identificador do dispositivo.

## 8. Análise

- **Análise primária, por grupo, nos pares completos:** par completo é a questão respondida pelo mesmo participante nas duas etapas; pontuação e tempo médio de cada etapa são calculados só nesses pares, e entram nos testes os participantes com ao menos um par completo.
- **Testes:** Wilcoxon dos postos sinalizados, pareado, bilateral, com p exato, sobre d = ferramenta − manual em pontuação (H1) e em tempo médio por resposta (H2); como robustez, teste de permutação exata por troca de sinais.
- **Tamanho de efeito:** correlação rank-biserial pareada e mediana das diferenças com IQR.
- **Múltiplas comparações:** ajuste de Holm sobre os 4 testes primários (2 desfechos × 2 grupos), com p brutos e ajustados. Diferenças entre grupos são apenas descritivas.
- **Sensibilidade**, definida antes de abrir os dados de acerto: (a) só participantes com as 10 questões respondidas nas duas etapas; (b) pontuação no pior caso, com "não respondida" contada como erro; (c) H1 repetida sem as respostas declaradas como vindas só da lembrança da etapa manual.
- **Poder:** com até 10 participantes por grupo, só efeitos grandes são detectáveis; resultado não significativo não é evidência de ausência de efeito, e a ênfase recai sobre os tamanhos de efeito.
- **SUS e questionário:** SUS descrita por grupo (média, desvio-padrão, mediana e n de questionários completos), sem teste de hipótese; itens Likert descritos por item (distribuição e mediana).
- **Descritivas por questão:** distribuição das classes de acerto, tempos, acurácia da ferramenta e transições entre as etapas (erro → acerto e acerto → erro).

## 9. Ameaças à validade

- **Ordem fixa:** a Etapa 3 recebe efeitos de aprendizado e memória da Etapa 2, que favorecem a ferramenta, e de fadiga e pressão de tempo, em sentido contrário. Mitigação parcial: respostas da Etapa 2 definitivas, acurácia da ferramenta medida à parte, declaração da origem da resposta e análises de sensibilidade. A limitação é registrada no TCC; um desenho futuro usaria dois conjuntos equivalentes de perguntas com contrabalanceamento.
- **Horário fixo de término:** pode deixar perguntas sem resposta, sobretudo na Etapa 3; tratado com "não respondida" como dado ausente, pares completos e análises de sensibilidade.
- **Aplicador autor da ferramenta:** nenhuma ajuda de conteúdo aos participantes e correção cega pelo gabarito.
- **Validade externa:** amostra de conveniência pequena, restrita a 4 resoluções e 20 perguntas; parte das questões trata de temas usados no desenvolvimento da ferramenta, e as de tema novo (G07, G09, P02, P04, P06, P10) são reportadas à parte.
- **Construto e materiais:** perguntas com gabarito curto não medem compreensão ampla da norma; o tempo inclui leitura e digitação; o texto indexado pela ferramenta pode ter ruído de extração ausente na leitura direta do PDF.

## Responsáveis e contato

Pesquisa do Trabalho de Conclusão de Curso de **Wesley Coutinho**, sob orientação do **Prof. Armando Sousa**, no Bacharelado em Ciência da Computação da UFPI. Contato: wesleysousa@ufpi.edu.br.
