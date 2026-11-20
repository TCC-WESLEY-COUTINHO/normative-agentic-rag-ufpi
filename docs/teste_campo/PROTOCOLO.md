# Protocolo do teste de campo — assistente normativo (RAG) para normas acadêmicas da UFPI

Versão do protocolo: 1.3 (2026-11-20).

Histórico: 1.0–1.2 (2026-11-19), versão inicial e aplicação das decisões da seção 18; 1.3 (2026-11-20), versão condensada, sem alteração das regras de coleta e de análise.

Nota de publicação: esta é a versão do protocolo publicada no repositório. O instrumento de coleta próprio (site de coleta), o plano de contingência do pesquisador e o gabarito são materiais de uso interno da pesquisa e não são publicados; as referências a eles foram substituídas por descrições do seu papel, e foram retiradas as informações que antecipariam o gabarito. O desenho, o roteiro, as métricas, a análise, as ameaças à validade e as decisões são os da versão 1.3.

Materiais complementares:

- [`QUESTOES.md`](QUESTOES.md) — enunciados das 20 questões (10 do grupo de graduação e 10 do grupo de pós-graduação).
- Gabarito (resposta, dispositivos, trechos literais e critérios de acerto total e parcial por questão) — uso interno, não publicado e não divulgado aos participantes (decisão D10).
- Documentação operacional do instrumento de coleta e plano de contingência do pesquisador — uso interno, não publicados.

---

## 1. Objetivo

Comparar, com usuários reais (estudantes), a consulta **manual** aos PDFs das resoluções com a consulta **mediada pela ferramenta** (assistente normativo baseado em RAG) quanto a acerto, tempo de resposta e percepção de uso, e observar o comportamento da ferramenta em uso real: recusas, pedidos de esclarecimento, erros e referências citadas.

### 1.1 Perguntas de pesquisa do teste

- **PQ1 (acerto).** Os participantes acertam mais quando usam a ferramenta do que quando consultam apenas os PDFs?
- **PQ2 (tempo).** O tempo médio por resposta é menor com a ferramenta do que com a consulta manual?
- **PQ3 (percepção).** Como os participantes avaliam a agilidade, a confiança, a clareza e a utilidade das referências da ferramenta?
- **PQ4 (comportamento).** Em uso real, com que frequência a ferramenta responde corretamente, erra, recusa ou pede esclarecimento, e como isso afeta a resposta final do participante?

### 1.2 Hipóteses (testes bilaterais, α = 0,05)

- H1₀: a mediana das diferenças de pontuação (ferramenta − manual) por participante é zero.
- H2₀: a mediana das diferenças de tempo médio por resposta (ferramenta − manual) por participante é zero.

PQ3 e PQ4 são descritivas e não têm teste de hipótese.

## 2. Desenho

- **Intra-sujeitos (pareado):** cada participante responde às mesmas 10 perguntas nas duas condições.
- **Ordem fixa**, definida com o orientador: Etapa 2 (manual, só PDFs) e depois Etapa 3 (com a ferramenta); implicações na seção 8.
- Dois grupos independentes, cada um com seus documentos e perguntas:

| Grupo | n | Documentos (PDF) | Questões |
|---|---|---|---|
| Graduação | 10 | Res. 177/2012 CEPEX/UFPI + Res. 1.056/2026 CEPEX/UFPI | G01–G10 |
| Pós-graduação | 10 | Res. 956/2025 CEPEX/UFPI (vigente) + Res. 658/2024 CEPEX/UFPI (revogada) | P01–P10 |

- Unidade de análise: o participante (pontuação total e tempo médio em cada condição); a questão serve só à análise descritiva.
- Instrumento: site de coleta próprio, com um endereço por grupo (graduação e pós-graduação) e painel do aplicador (seção 15); o Google Forms é apenas nível de contingência (seção 17).
- Sessão: presencial, em laboratório, uma única por grupo, com todos os participantes ao mesmo tempo, cada um em seu computador, conduzidos por um aplicador (decisão D4; seção 7).

## 3. Participantes

**Inclusão:** estudante regularmente matriculado na UFPI, em qualquer período, em curso de graduação (grupo de graduação) ou em mestrado ou doutorado stricto sensu (grupo de pós-graduação); idade mínima de 18 anos; aceite do TCLE; familiaridade básica com computador e leitor de PDF. Não há período mínimo (decisão D3): o participante informa o próprio período (ou semestre, na pós-graduação) no perfil, e esse dado é usado apenas na análise descritiva (seção 11).

**Exclusão:** participação no desenvolvimento, na anotação, no gabarito ou no piloto da ferramenta, ou no piloto deste protocolo; uso da ferramenta antes do teste; atuação profissional em secretaria acadêmica, coordenação ou elaboração de normas; na pós-graduação, matrícula apenas como aluno especial.

**Recrutamento e identificação:** amostra de conveniência, convidada por intermédio de docentes do departamento: 10 participantes e 2 reservas por grupo, convidados para a mesma sessão; os reservas ocupam vagas de ausentes ou desistentes antes do início do teste. Cada participante recebe no dia um código (`PART-G01` a `PART-G10`; `PART-P01` a `PART-P10`), cadastrado previamente no painel, válido para um único grupo, uma única sessão e uma única participação, e igual no site e nos formulários de contingência. A lista que liga código e pessoa **não é criada**; se for necessário controlar o comparecimento, usa-se lista de presença em papel, sem o código, descartada ao fim da coleta.

## 4. Consentimento e proteção de dados (LGPD)

### 4.1 Princípio e dados não coletados

A coleta observa os princípios de finalidade e necessidade da LGPD (Lei nº 13.709/2018): apenas os dados mínimos para as perguntas de pesquisa, sem identificar o participante. Não são coletados nome, matrícula, CPF, e-mail, telefone, curso exato (só a grande área), IP, identificador do navegador nem gravações de tela, áudio ou vídeo. O site não tem campos para esses dados nem registra IP, user-agent ou requisições, e seus cookies são apenas técnicos; os formulários de contingência não coletam e-mail nem exigem login.

### 4.2 Dados coletados

Código, grupo, período informado (na pós-graduação, também nível e faixa do ano de ingresso), grande área, duas escalas de familiaridade (normas e assistentes conversacionais), respostas, carimbos de tempo do servidor, questionário pós-teste, anotações da discussão sem nomes, logs da ferramenta vinculados ao código (seção 14) e, havendo contingência, a origem de cada registro e o registro de trocas. Os dados ficam na pasta privada da pesquisa, fora de qualquer repositório.

### 4.3 TCLE simplificado (texto exibido na primeira tela após o código)

Texto do TCLE:

> **Termo de Consentimento Livre e Esclarecido (simplificado)**
>
> Você está sendo convidado(a) a participar de um teste de uma ferramenta que responde dúvidas sobre normas acadêmicas da UFPI, parte do Trabalho de Conclusão de Curso de Wesley Coutinho, orientado pelo Prof. Armando Sousa, no Bacharelado em Ciência da Computação da UFPI.
>
> **O que você fará:** responderá a 10 perguntas sobre normas acadêmicas, primeiro consultando PDFs das resoluções e depois usando a ferramenta, e preencherá um breve questionário de opinião. Ao final, haverá uma conversa em grupo sobre a experiência. Duração estimada: cerca de 2 horas.
>
> **Não é uma prova:** o seu desempenho não será associado a você e não tem nenhum efeito acadêmico. O que está sendo avaliado é a ferramenta e o processo de consulta, não você.
>
> **Riscos e desconfortos:** mínimos, como cansaço ou desconforto por não saber uma resposta. Você pode pular perguntas, fazer pausas ou desistir a qualquer momento, sem precisar justificar e sem nenhum prejuízo.
>
> **Privacidade:** não coletamos seu nome, matrícula ou e-mail. Você será identificado(a) apenas por um código. As perguntas que você digitar na ferramenta serão registradas (com data e hora) junto a esse código; **não digite dados pessoais na ferramenta**. Os dados serão usados somente para fins acadêmicos, apresentados de forma agregada e guardados em local de acesso restrito ao pesquisador e ao orientador. Como são anônimos e não permitem identificar você, esses dados serão mantidos por prazo indeterminado, sempre para fins acadêmicos.
>
> **Discussão em grupo:** as falas serão anotadas sem identificação de quem falou. Não há gravação de áudio nem de vídeo.
>
> **Benefícios:** não há benefício direto. Os resultados podem ajudar a melhorar ferramentas de apoio à consulta de normas.
>
> **Contato:** wesleysousa@ufpi.edu.br.
>
> ( ) Li e concordo em participar. ( ) Não concordo. → encerra a participação.

Observação: o teste não é submetido a Comitê de Ética em Pesquisa (decisão D1); mantêm-se o TCLE, o anonimato e a participação voluntária. O TCLE é idêntico no site e nos formulários de contingência. A recusa encerra a participação sem coletar perfil nem respostas. A desistência pode ser registrada pelo participante a partir da espera das etapas, sem motivo; as respostas já enviadas são mantidas. Para pular uma pergunta, registra-se "não sei".

## 5. Materiais e preparação

- **PDFs** oficiais por grupo (seção 2), com numeração de artigos conferida contra o gabarito, que segue o corpus canônico (consolidação da Res. 177/2012 com alterações posteriores; decisão D2).
- **Ferramenta** em versão congelada durante toda a coleta; a versão (tag/commit), o modelo de linguagem de geração (identificador e provedor), a configuração e a data do índice são registrados na planilha de sessão.
- **Site de coleta** com versão e banco de questões fixos durante toda a coleta.
- **Um computador por participante**, com leitor de PDF (Ctrl+F permitido) e o endereço do site do grupo; a ferramenta só é acessada na Etapa 3, pelo link do site. Em telas 16:9, o site pode ficar em meia tela ao lado do PDF ou da ferramenta (no Windows, tecla Windows + seta para a esquerda ou para a direita).
- **Relógio com segundos projetado**, referência comum para a planilha, o registro de trocas e o nível 3 de contingência; **cronômetro** do aplicador; **planilha de sessão** (data, horários, códigos, versão da ferramenta, ocorrências, início e fim das etapas); materiais de contingência (seção 17); roteiros impressos (seções 7 e 13).
- Pergunta de demonstração, **fora do conjunto de teste**: graduação — "O que é integralização curricular?"; pós — "Quantos períodos letivos regulares um PPG tem por ano?".

**Checklist antes de cada sessão:** (1) ferramenta no ar, na versão congelada, com logs testados pela pergunta de demonstração (registro apagado ou marcado como teste); (2) site verificado, com painel acessível, códigos cadastrados, TCLE e endereço da ferramenta configurados, relógio do servidor sincronizado, backup feito e Etapas 2 e 3 não liberadas; (3) PDFs abertos, sem anotações e com histórico de busca limpo; (4) ferramenta inacessível antes da Etapa 3 e outras fontes (internet, outros assistentes conversacionais, colegas) bloqueadas ou vedadas; (5) checklist do plano de contingência cumprido, sem distribuir antes da necessidade os endereços dos níveis 2 e 3.

**Piloto:** 1 sessão por grupo, com 1–2 pessoas fora da amostra, para calibrar tempos, clareza das perguntas, fluxo do site e captura de logs, com simulacro de contingência. Os resultados não entram na análise. Ajustes de redação são aplicados igualmente ao site e aos formulários antes da coleta; durante a coleta, o banco de questões não muda.

## 6. Formato da sessão

O aplicador lê as falas para o grupo inteiro, libera as etapas para a sessão e só inicia a apresentação da ferramenta e a discussão quando todos concluem o bloco anterior; quem termina antes aguarda em silêncio na tela de espera. Não há limite de tempo por questão nem por etapa (decisão D9). Tempos de referência, calibrados no piloto (a duração das Etapas 2 e 3 é a do participante mais lento):

| Bloco | Duração de referência | Acumulado |
|---|---|---|
| 1. Boas-vindas, TCLE e perfil | 10 min | 0:10 |
| 2. Etapa 1 — aquecimento com os PDFs | 5 min | 0:15 |
| 3. Etapa 2 — 10 perguntas só com PDFs | cerca de 30 min, sem limite | 0:45 |
| 4. Intervalo e apresentação da ferramenta | 5 min + 3 min | 0:53 |
| 5. Etapa 3 — as mesmas 10 perguntas com a ferramenta | cerca de 30 min, sem limite | 1:23 |
| 6. Questionário pós-teste | 10 min | 1:33 |
| 7. Discussão final em grupo | 15 min | 1:48 |

## 7. Roteiro da sessão

Os trechos "Texto lido ao participante" são falas literais do aplicador.

**Bloco 1 — Boas-vindas, TCLE e perfil.** Texto lido ao participante:

> "Obrigado por vir. Hoje vamos testar uma ferramenta que responde dúvidas sobre normas acadêmicas da UFPI. Não é uma prova: o que está sendo avaliado é a ferramenta e o processo de consulta, não vocês. Ninguém será identificado. Vocês vão responder a 10 perguntas duas vezes: primeiro consultando os PDFs das resoluções e depois usando a ferramenta. Por favor, não conversem entre si sobre as perguntas, nem durante nem depois da sessão, até o fim da pesquisa. Digitem o código que receberam e leiam o termo de consentimento na tela. Se tiverem dúvidas, perguntem antes de aceitar."

O aplicador entrega os cartões com os códigos; cada participante informa o código, responde ao TCLE, preenche o perfil e aguarda. Quem não aceita o TCLE é dispensado com agradecimento.

**Bloco 2 — Etapa 1: aquecimento (5 min, cronometrados, com aviso no último minuto).** Texto lido ao participante:

> "Nos próximos 5 minutos, explorem livremente os PDFs que estão abertos. Vejam como estão organizados, os capítulos e o sumário, e testem a busca com Ctrl+F. Ainda não há perguntas. Às vezes uma resolução altera ou revoga outra; vale observar isso."

**Bloco 3 — Etapa 2: consulta manual.** Texto lido ao participante:

> "Agora vocês vão responder às 10 perguntas usando **apenas os PDFs**. Não usem internet, outros programas de IA nem colegas. Respondam com suas palavras, de forma curta, e, se conseguirem, indiquem o artigo que fundamenta a resposta. Salvo indicação em contrário, respondam conforme a norma em vigor hoje. Cada pergunta aparece numa página; a resposta enviada é definitiva, o site passa à pergunta seguinte e não é possível voltar. Não há limite de tempo, e o tempo é registrado automaticamente pelo site. Se não encontrarem a resposta, registrem a melhor resposta que tiverem, ou 'não sei', e avancem. Se quiserem, deixem o site em meia tela ao lado do PDF: no Windows, use a tecla Windows com a seta para a esquerda ou para a direita. Quem terminar aguarda em silêncio na tela de espera. Cliquem em 'Verificar liberação' e, ao meu sinal, em 'Iniciar Etapa 2'."

O aplicador libera a etapa no painel, dá o sinal e anota o horário de início e o de conclusão do último participante; não há aviso de tempo nem encerramento automático. Não responde a dúvidas de conteúdo; a dúvidas de interpretação responde apenas "Responda como você entendeu e, se quiser, anote sua dúvida na resposta" e registra a ocorrência.

**Bloco 4 — Intervalo e apresentação da ferramenta**, quando todos concluem a Etapa 2. Texto lido ao participante (após o intervalo):

> "Agora vocês vão usar a ferramenta. Ela responde dúvidas sobre normas acadêmicas com base nas resoluções e mostra as referências usadas. Vou mostrar uma pergunta de exemplo." *(Demonstração com a pergunta de demonstração do grupo, seção 5.)* "Algumas observações: (1) **não digitem dados pessoais** nas perguntas; (2) podem reformular a pergunta quantas vezes quiserem; (3) a ferramenta pode pedir esclarecimento, por exemplo se a dúvida é de graduação ou pós; nesse caso, respondam a ela; (4) a ferramenta pode recusar ou errar, e a resposta final registrada no site é de vocês; (5) para cada pergunta, abram uma **nova conversa**, se a interface permitir. O link da ferramenta aparece na página de cada pergunta e abre em outra aba; se quiserem, deixem o site e a ferramenta lado a lado, cada um em meia tela, com a tecla Windows e as setas."

Os PDFs ficam **fechados** na Etapa 3 (padrão; decisão D5). Antes de iniciá-la, cada participante confirma, obrigatoriamente, "Não voltarei às respostas da Etapa 2"; a ordem das etapas é fixa mesmo com liberação antecipada.

**Bloco 5 — Etapa 3: com a ferramenta.** Texto lido ao participante:

> "Respondam às mesmas 10 perguntas usando a ferramenta. Vocês podem copiar ou adaptar a pergunta que aparece na tela. Em cada página, registrem a sua resposta final e indiquem o que a ferramenta fez: respondeu, pediu esclarecimento, recusou ou deu erro. Valem as mesmas regras: sem limite de tempo, sem internet e sem colegas. As respostas da Etapa 2 não podem mais ser alteradas. Ao meu sinal, cliquem em 'Iniciar Etapa 3'. Depois da última pergunta, o site apresenta um questionário de opinião; quem terminar aguarda em silêncio até a conversa final."

Valem as condições de tempo da Etapa 2. Falhas técnicas são registradas com horário e código e seguem a seção 17.

**Bloco 6 — Questionário pós-teste**, apresentado pelo site após a décima resposta e respondido no ritmo de cada participante. Texto lido ao participante:

> "Por último, um questionário rápido de opinião. Não há resposta certa. Sejam sinceros, inclusive sobre o que não funcionou."

**Bloco 7 — Discussão final em grupo**, quando todos enviam o questionário (seção 13). Encerramento, texto lido ao participante:

> "Muito obrigado. Peço mais uma vez que não comentem as perguntas com outros colegas até o fim da pesquisa. As respostas corretas são material interno da pesquisa e não serão divulgadas."

Ao fim, o aplicador exporta os dados, faz o backup do banco (seção 15) e completa a planilha de sessão e, se houver, o registro de trocas.

## 8. Ordem fixa: ameaças e mitigação

Com as mesmas perguntas e a ordem fixa, a Etapa 3 recebe os efeitos da Etapa 2: aprendizado, memória e familiaridade com a tarefa, que favorecem a ferramenta em acerto e tempo, e fadiga, em sentido contrário. O desenho não separa totalmente o efeito da ferramenta do efeito de ordem. Mitigações:

1. **Sem retorno:** respostas da Etapa 2 definitivas, sem botão de voltar, alteração recusada pelo servidor após o início da Etapa 3 e nenhuma resposta manual exibida na Etapa 3 (no nível 3 de contingência, seção 9).
2. **Medida independente:** a resposta da própria ferramenta (do log) é corrigida pelo mesmo gabarito; essa acurácia não sofre o efeito de aprendizado e é a medida mais limpa de PQ4.
3. **Origem da resposta:** na Etapa 3, o participante declara se a resposta veio da ferramenta, da ferramenta com a lembrança da etapa manual ou só da lembrança; as análises são repetidas sem as respostas "só da lembrança".
4. **Transições** por questão (erro→acerto, acerto→erro); acerto→erro indica indução a erro pela ferramenta.
5. **Intervalo** entre as etapas e **discussão explícita** da limitação no TCC.

Mitigação opcional (decisão D6): 1 a 2 perguntas inéditas na Etapa 3, analisadas à parte. Um desenho futuro mais robusto usaria dois conjuntos equivalentes de perguntas, com contrabalanceamento AB/BA.

## 9. Medição de tempo

- **Fonte:** o servidor do site, por participante × etapa × questão, sem teto e sem horários anotados pelo participante. O cronômetro na página, se houver, é apenas indicativo.
- **Tempo da questão** = envio − exibição, em segundos com três casas decimais, calculado pelo servidor (UTC, com milissegundos), nunca com valores do navegador. A exibição é a primeira vez em que a página da questão é servida após o início da etapa; recargas, novas abas ou erros não a alteram. O tempo inclui ler, consultar e digitar, como nas duas etapas.
- **Etapa:** o início é registrado quando o participante confirma o início, após a liberação; o fim, na conclusão ou interrupção. **Tempo médio por resposta:** média dos 10 tempos de questão (a mediana também é reportada).
- **Relógio:** sincronizado antes da coleta e inalterado durante a sessão; envio que geraria tempo negativo é recusado.
- **Validação cruzada:** na Etapa 3, os logs da ferramenta conferem o intervalo da questão e medem a latência da ferramenta; o início e o fim das etapas são comparados com a planilha do aplicador.
- **Tratamento:** nenhuma questão é encerrada por tempo; "não sei" mantém o tempo observado e conta como erro, com contagem reportada por etapa. Interrupções registradas são subtraídas do tempo da questão em curso, marcada `ajuste_tecnico=1`, sempre na análise. Tempo ausente ou inválido é recuperado do log ou da planilha, com marcação, ou fica ausente (nunca zero).
- **Falha da medição:** se mais de 20 % dos tempos de questão de uma etapa forem inválidos (esperado apenas no nível 3 de contingência, com horários digitados), o tempo dessa etapa passa a tempo total ÷ questões respondidas, marcado `tempo_estimado=1`; na Etapa 3, pode-se usar os logs. A decisão é registrada antes de abrir os dados de acerto.
- **Separação das etapas no nível 3:** como o Forms não bloqueia o retorno, adotam-se instrução, supervisão, a confirmação obrigatória e auditoria; horário da Etapa 2 posterior ao início da Etapa 3 indica edição, marcada `edicao_suspeita=1` e excluída da análise de acerto da Etapa 2.

## 10. Critério de correção

| Classe | Pontos | Regra objetiva |
|---|---|---|
| **Acerto total** | 1 | A resposta traz a **conclusão correta** e **todos os elementos essenciais** listados no critério de acerto total da questão (gabarito de uso interno) e não contém afirmação normativa errada que contradiga o gabarito. |
| **Acerto parcial** | 0,5 | Conclusão correta com elemento essencial ausente ou impreciso, **ou** elementos corretos sem a conclusão. Os detalhes por questão constam do critério de acerto parcial do gabarito de uso interno. |
| **Erro** | 0 | Conclusão errada; resposta baseada em norma revogada quando a pergunta trata da regra vigente; "não sei"; em branco; ou fora do tema. |

- **Citar o dispositivo não é exigido**; o dispositivo citado é registrado à parte (`dispositivo_correto` = sim/não/não citou) como medida secundária.
- **Informação extra correta** não reduz a nota; **informação extra errada** que mude a orientação ao estudante rebaixa a classe em um nível.
- **Valores numéricos** (prazos, créditos, notas) precisam estar exatos; "dias" no lugar de "dias úteis" é parcial quando a distinção é essencial.
- **Resposta condicional** só é total se a condição for a do gabarito e a resposta para o caso dado estiver explícita.

**Procedimento:** (1) as respostas das duas etapas, unidas entre origens, são exportadas sem etapa e sem código, embaralhadas e identificadas por ID aleatório, com a chave de reidentificação em arquivo separado; (2) **dois corretores** independentes (o pesquisador e um segundo corretor; decisão D7) classificam cada resposta; (3) a concordância é calculada **antes do consenso** por κ de Cohen ponderado linear; (4) divergências são resolvidas por consenso registrado, que dá a nota final; (5) o mesmo vale para as **respostas da ferramenta** extraídas dos logs (última resposta por questão e participante), com as classes adicionais **recusa** e **esclarecimento sem resposta final**, que valem 0 e são reportadas à parte.

## 11. Métricas e análise estatística

- **Por participante e etapa:** pontuação (0–10), acerto estrito (acertos totais), tempo médio por resposta e tempo total, taxa de dispositivo correto (secundária) e, na Etapa 3, consultas por questão, esclarecimentos, recusas e falhas.
- **Por questão (descritivas):** distribuição das classes e tempo médio e mediano por etapa; acurácia da ferramenta (corretas, parciais, erradas, recusas, esclarecimentos); transições manual → ferramenta; quantas vezes o participante adotou ou corrigiu uma resposta errada da ferramenta.
- **Testes (por grupo, n = 10):** Wilcoxon dos postos sinalizados, pareado e bilateral, com **p exato**, sobre d_i = ferramenta − manual em pontuação (H1) e em tempo médio por resposta (H2), reportando o tratamento das diferenças nulas (Wilcoxon ou Pratt); como robustez, **permutação exata por troca de sinais** (2¹⁰ = 1024 combinações).
- **Tamanho de efeito:** rank-biserial pareada, r_rb = (W⁺ − W⁻) / [n(n+1)/2], e mediana das diferenças com IQR; opcionalmente, Hodges–Lehmann com IC 95% por bootstrap.
- **Holm** sobre os 4 testes primários (2 desfechos × 2 grupos), com p brutos e ajustados. Análise conjunta dos 20 participantes apenas como secundária; diferenças entre grupos só descritivas.
- **Poder e sensibilidade:** com n = 10, só efeitos grandes são detectáveis; resultado não significativo **não** é evidência de ausência de efeito, e a ênfase recai sobre os tamanhos de efeito. Repete-se H1 sem as respostas "só da lembrança" e repetem-se os testes com as exclusões S1–S3 (seção 17), definidas antes de abrir os dados de acerto.
- **Descrição:** amostra por grupo (período informado, com distribuição, mediana, mínimo e máximo; nível e faixa de ingresso na pós-graduação; grande área; familiaridade), com resultados também por período quando útil, sem teste; por grupo e etapa, média, desvio-padrão, mediana, IQR, mínimo e máximo, gráfico de pares e tabela por questão; Likert por item (barras empilhadas e mediana), sem tratá-la como intervalar; número de participantes e linhas por origem, se houver contingência.

Script e dados brutos ficam fora do repositório até a decisão sobre o que versionar.

## 12. Questionário pós-teste

Os itens abaixo são apresentados ao participante no site, com a redação literal a seguir.

### 12.1 Escala Likert (1 = discordo totalmente … 5 = concordo totalmente)

1. Com a ferramenta, encontrei as respostas mais rapidamente do que com os PDFs.
2. Confio nas respostas que a ferramenta me deu.
3. As respostas da ferramenta foram claras e fáceis de entender.
4. As referências (resolução/artigo) mostradas pela ferramenta me ajudaram a confiar na resposta ou a conferi-la.
5. Foi fácil formular minhas perguntas para a ferramenta.
6. Quando a ferramenta pediu esclarecimento ou recusou responder, entendi o motivo. (Opção extra: "não aconteceu".)
7. Encontrar as respostas apenas nos PDFs foi difícil.
8. Eu usaria a ferramenta para tirar dúvidas reais sobre normas da UFPI.

### 12.2 Perguntas abertas

As perguntas abertas são opcionais, em respeito à participação voluntária.

1. **Agilidade:** em que situações a ferramenta acelerou ou atrasou sua consulta?
2. **Confiança:** houve alguma resposta da ferramenta em que você desconfiou? Por quê? O que faria você confiar mais?
3. **Clareza:** alguma resposta foi confusa, longa demais ou incompleta? Qual?
4. **Quando a ferramenta errou, recusou ou pediu esclarecimento:** descreva o que aconteceu e como você reagiu.
5. **Melhorias:** o que mudaria na ferramenta ou no processo de consulta às normas?

Opcional (decisão D8): aplicação da System Usability Scale (SUS, 10 itens) no lugar dos itens 3, 5 e 8, para comparação com outros estudos de usabilidade.

## 13. Roteiro da discussão final (15 min)

Conduzida pelo aplicador com todo o grupo. Perguntas norteadoras, com cerca de 3 minutos cada (texto lido ao participante):

- **Agilidade:** "Comparando as duas etapas, o que mudou na forma de chegar à resposta?"
- **Melhoria do processo:** "Em que momentos do curso uma ferramenta assim teria ajudado vocês? Onde vocês buscam essas informações hoje?"
- **Acertos:** "Vocês sentiram que acertaram mais com a ferramenta? Houve alguma pergunta em que a ferramenta atrapalhou?"
- **Comportamento da ferramenta:** "O que acharam quando ela pediu esclarecimento ou recusou? As referências ajudaram?"
- **Temporalidade:** "Perceberam que uma resolução alterava ou revogava a outra? Isso dificultou a consulta manual? A ferramenta lidou bem com isso?"

As falas são anotadas em tópicos, sem nomes (ou só com o código, se o participante concordar), e classificadas por tema (agilidade, confiança, clareza, erros/recusas, temporalidade, sugestões), em análise temática simples.

## 14. Registros da ferramenta

Os logs da ferramenta são independentes do site, que apenas exibe o link na Etapa 3, sem transmitir código, credenciais ou dados do formulário. Por consulta, registram-se: conversa, código do participante (associado pelo aplicador), grupo, questão (atribuída na pós-coleta), horários e latência, textos da pergunta e da resposta, referências exibidas, desfecho (respondeu, pediu esclarecimento, recusou, fallback ou erro técnico), ordem da consulta na questão, telemetria estruturada já existente (sem texto de raciocínio intermediário) e versão da ferramenta. Não se registram IP, user-agent, cookies, nome, e-mail, matrícula nem identificador do dispositivo; se o sistema os registrar por padrão, o registro é desativado ou removido antes do armazenamento. Campos ausentes são completados manualmente ou habilitados **sem alterar o comportamento da ferramenta**. Ao fim de cada sessão, os logs são exportados para a pasta privada (os de instância local à parte) e limpos de dados pessoais acidentais antes de qualquer análise. Usos: acurácia da ferramenta, validação de tempo, contagem de reformulações, esclarecimentos e recusas e exemplos qualitativos anonimizados.

## 15. Instrumento de coleta

O site de coleta tem um endereço por grupo, com o mesmo fluxo, e um painel do aplicador protegido por credencial; implantação, exportação (arquivos, colunas e convenções), backup e restauração estão na documentação operacional do instrumento, de uso interno. Regras: código validado contra a lista; uma página por passo, em ordem fixa, sem retorno, com respostas definitivas gravadas uma a uma; Etapas 2 e 3 iniciadas só após liberação no painel; gabarito nunca enviado ao navegador; banco de questões e opções fixos; sem limite nem aviso de tempo. Em perda de credencial, o aplicador emite pelo painel um código de retomada de uso único, que devolve o participante ao ponto em que estava na mesma instância, sem nunca reabrir a Etapa 2 depois do início da Etapa 3.

**Fluxo:** (1) código; (2) TCLE; (3) perfil; (4) Etapa 2, uma pergunta por página, com "Sua resposta" (obrigatória; aceita "não sei"), "Artigo/dispositivo que fundamenta" (opcional) e "Quão confiante você está nesta resposta?" (1–5); (5) espera e confirmação "Não voltarei às respostas da Etapa 2"; (6) Etapa 3, com os mesmos campos, o link da ferramenta e as perguntas "O que a ferramenta fez?" (respondeu / pediu esclarecimento / recusou / deu erro técnico / respondi sem usar a ferramenta), "Sua resposta final veio de:" (só da ferramenta / da ferramenta e da minha lembrança da etapa manual / só da minha lembrança da etapa manual / outra) e "Quantas vezes você perguntou ou reformulou?" (1 / 2 / 3+); (7) pós-teste (seção 12); (8) agradecimento.

**Perfil:**
- graduação: "Em que período do curso você está?" (numérico); pós: nível (mestrado/doutorado), "Em que período/semestre do curso você está?" (numérico) e ano de ingresso (faixa);
- grande área do curso (categorias gerais, incluindo "Multidisciplinar" e "Prefiro não informar");
- "Com que frequência você consulta resoluções/normas da UFPI?" (1–5);
- "Com que frequência você usa assistentes de IA (chatbots)?" (1–5);
- "Você já leu alguma das resoluções deste teste antes?" (sim/não/em parte).

**Dados:** as respostas são exportadas no formato da planilha de consolidação (uma linha por participante × etapa × questão), para o qual também são convertidos os formulários de contingência. A planilha reúne as respostas, os tempos, as marcações de tratamento (seção 9), os campos da Etapa 3 e as classes atribuídas pelos corretores (seção 10); suas colunas estão na documentação do instrumento. Ao fim de cada sessão, os dados são exportados e o banco é copiado para a pasta privada da pesquisa. Os dados brutos nunca são editados à mão; ajustes e marcações são feitos na análise.

## 16. Ameaças à validade

- **Interna:** ordem fixa e aprendizado, principal limitação (seção 8); fadiga, numa sessão de cerca de 2 h (intervalo); pressa e influência mútua na sessão simultânea (tempo individual, espera silenciosa, nenhum anúncio de quem terminou, vedação de conversa, supervisão); contaminação com reservas não participantes ou entre grupos (pedido de sigilo e gabarito não divulgado); expectativa do aplicador, autor da ferramenta (falas roteirizadas, nenhuma ajuda de conteúdo, correção cega com dois corretores); variação não determinística das respostas da ferramenta (logs e acurácia por resposta); diferenças de infraestrutura e de medição na contingência (`origem`, registro de trocas, S1–S3).
- **Construto:** perguntas fechadas, com gabarito curto, não medem compreensão ampla da norma; o tempo inclui leitura, digitação e pausas; as perguntas simulam dúvidas reais, mas não são espontâneas; a resposta da Etapa 3 mistura ferramenta e julgamento do participante, por isso a acurácia da ferramenta é medida à parte.
- **Externa:** amostra de conveniência pequena e heterogênea, sem período mínimo; resultados restritos a 4 resoluções e 20 perguntas; parte das questões trata de temas dos bancos de desenvolvimento e avaliação da ferramenta (indicado, por questão, no material interno das questões), o que pode tornar a acurácia otimista, e por isso as questões de tema novo (G07, G09, P02, P04, P06, P10) são reportadas à parte.
- **Conclusão:** baixo poder, empates e múltiplas comparações.
- **Materiais:** os PDFs podem divergir do corpus indexado (consolidação, OCR), o que é conferido antes da coleta (D2). Na pós-graduação, o art. 60 da Res. 956/2025 a aplica a quem ingressar a partir da sua publicação; por isso as perguntas têm resposta única (regra igual nas duas resoluções ou situação indicada, como em P04, "vou ingressar").

## 17. Contingência

Resumo do plano de contingência do pesquisador (de uso interno, não publicado), que prevalece em divergência operacional. Princípios: perguntas, ordem e regras não mudam, só a infraestrutura e a forma de medir; cada linha de dado carrega a `origem` (`site`, `site_local` ou `forms`); dados brutos não são editados; nenhum nível identifica o participante; não há versão em papel.

| Nível | Instrumento | Quando é usado |
|---|---|---|
| **1** | Site de coleta em nuvem (HTTPS) | Padrão. |
| **2** | O mesmo site no computador do aplicador, na rede local, com banco separado | O nível 1 falha antes de qualquer participante iniciar a Etapa 2 (ou por decisão prévia). |
| **3** | Google Forms, um formulário por grupo, com o mesmo TCLE e fluxo, sem e-mail, login nem edição após o envio, com horários digitados a partir do relógio da sala e opção de retomada | O nível 1 falha depois do início da Etapa 2, ou o nível 2 também falha. |
| **4** | Interrupção e remarcação da sessão | Níveis 1 a 3 indisponíveis. |

**Gatilho.** Troca-se de nível quando a falha impede o grupo de trabalhar e não se resolve em prazo curto e predefinido; o aplicador é o único decisor e registra o horário pelo relógio da sala. Gatilho principal: nível 1 fora do ar por mais de 2 min contínuos, com troca imediata se ninguém estiver nas Etapas 2 ou 3 e, caso contrário, até 5 min de tentativa de recuperação. Outro exemplo: perda ou inconsistência de dado leva à troca imediata, com preservação do banco. Questões enviadas não são refeitas; quem ainda não iniciou a Etapa 2 refaz código, TCLE e perfil no nível 2, e quem já a iniciou continua no nível 3 a partir da primeira questão não enviada, e a questão em curso é refeita, com a interrupção descontada (`ajuste_tecnico=1`).

**Falha da ferramenta na Etapa 3.** Após até 3 min de recuperação, usa-se instância local **somente** se confirmadas, antes da sessão, a mesma versão congelada, configuração e índice; caso contrário, a Etapa 3 do participante é remarcada com a mesma versão ou analisada à parte como "incompleta por falha técnica". Respostas de versões diferentes nunca são reunidas na mesma Etapa 3.

**Registro de trocas.** Cada troca e cada falha da ferramenta são registradas no momento, por participante afetado: etapa e questão em curso, níveis de origem e destino, horários de detecção, decisão e retomada, duração da interrupção, motivo, gatilho, instância da ferramenta e responsável.

**Análise.** Na união das origens, prevalece por participante × etapa a origem mais completa (mais respostas, mais tempos válidos, medição pelo servidor); trocas no meio da etapa são marcadas `etapa_dividida`, e conflitos são resolvidos por decisão documentada do pesquisador. A análise principal usa todos os dados válidos. Análises de sensibilidade, definidas antes de abrir os dados de acerto: **S1**, sem participantes com qualquer linha fora de `site`; **S2**, sem participantes com remarcação, `etapa_dividida`, instância local da ferramenta ou `edicao_suspeita`; **S3 (tempo)**, só linhas com `tempo_estimado=0` e medição pelo servidor. Reportam-se o n de cada análise, o que mudou, quantos participantes e linhas vieram de cada origem e quantas trocas ocorreram.

## 18. Decisões do pesquisador

**Tomadas (2026-11-19):** D1 — sem submissão a Comitê de Ética em Pesquisa, com TCLE, anonimato e participação voluntária; D3 — sem período mínimo (pós-graduação stricto sensu), com período informado no perfil; D4 — sessão presencial, em laboratório, única por grupo, com discussão em grupo; D9 — sem limite nem aviso de tempo, com tempo medido pelo servidor; D10 — gabarito de uso interno; TCLE com contato wesleysousa@ufpi.edu.br e guarda dos dados anônimos por prazo indeterminado; recrutamento por docentes do departamento; uso do site em meia tela.

**Pendentes:**

- **D2 — Versão dos PDFs:** confirmar que o PDF da Res. 177/2012 é a versão consolidada (com as alterações de 2018–2021 presentes no corpus) e que a numeração dos artigos usados no gabarito coincide com a do PDF; confirmar que o PDF da Res. 1.056/2026 mostra claramente qual dispositivo da Res. 177/2012 é alterado (o texto do corpus tem ruído de OCR nesse ponto).
- **D5 — PDFs na Etapa 3:** fechados (padrão; isola o efeito da ferramenta) ou permitidos para conferência (mais realista, mas mistura as condições).
- **D6 — Perguntas inéditas na Etapa 3** (seção 8): inclusão ou não.
- **D7 — Segundo corretor:** orientador ou colega; correção de 100% das respostas ou de uma amostra (exemplo: 30%) com κ.
- **D8 — SUS:** uso ou não da System Usability Scale completa no pós-teste (10 itens de 1 a 5, com pontuação de usabilidade de 0 a 100).
