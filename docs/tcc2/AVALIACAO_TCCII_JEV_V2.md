# Avaliação da A″-J v2 em relação às questões de pesquisa do TCC II

> **Avaliação histórica das condições A, A′, A″-J v1 e v2.** As versões, contagens e estados de defeitos abaixo descrevem aquelas execuções; não representam uma avaliação da geração citada da v3.4. Consulte os [resultados da v3.4](../RESULTADOS.md) e a [proveniência das condições](../PROVENIENCIA.md).

Este documento relaciona as evidências existentes às questões QP1–QP5 do TCC II. A pergunta de pesquisa não foi alterada:

> Como se comporta, e com quais limitações, um assistente para normas universitárias quando as decisões de escopo, nível de ensino e versão são separadas da geração da resposta, e esta é verificada antes da entrega?

## Natureza da evidência

- Todos os resultados são **exploratórios**, obtidos com conjuntos de desenvolvimento.
- Não há avaliação confirmatória executada nem revisão normativa por pessoa qualificada.
- A pesquisa de campo com estudantes não foi realizada.
- Os dados brutos e as anotações do pesquisador estão preservados fora do repositório. As métricas foram recalculadas por um procedimento independente dos scripts originais (§6).

## Versões

| Versão | Identificação | Papel |
|---|---|---|
| **A** | tag `tcc2-cond-A` (código de `8fb690e5`) | Baseline: referência histórica e comparativa |
| **A′** | tag `tcc2-cond-A1` | Intermediária: R1 (esclarecimentos naturais) e R2 (nível declarado persistido) |
| **A″-J v1** | tag `tcc2-cond-v1` | Intermediária: A′ + intérprete Jev + política de transição v1 |
| **A″-J v2** | tag `tcc2-cond-v2` | **Arquitetura selecionada para o protótipo**: v1 + política de transição v2 |

- **Diferença entre A e v2:** só a camada de interpretação e de transição conversacional (R1/R2, nó Jev, política v2). Scope Gate, roteador `intent_v1`, recuperação K = 5, VersionFilter, geração, validador v5, registro normativo e índice são idênticos byte a byte nas quatro versões.
- **Não confundir:** `datasetgold_reviewed_v2` é a segunda versão revisada do gold normativo. Não é a arquitetura A″-J v2.

## Legenda das origens

| Rótulo | Significado |
|---|---|
| **[v2]** | Medido diretamente na v2 |
| **[A]** | Medido na baseline A ou em versões anteriores, antes da v2 |
| **[comum]** | Componente compartilhado: o resultado vale para a v2 em turno único, por identidade de código, mas não foi remedido nela |

---

## QP1 — Escopo e nível de ensino

| Evidência | Origem | Resultado |
|---|---|---|
| Roteadores V1 × V2 (TEST, n = 23) | [A] | V1 16/23 corretas, 0/23 rotas concretas erradas, esclarecimento indevido (UCR) 7/14. V2-D 12/23 e V2-L 13/23, com 10 e 9 rotas erradas. V1 mantido |
| Lote diagnóstico pré-congelamento (n = 35) | [A] | 26/35 decisões corretas; 0/35 níveis errados; UCR 5/14 |
| C2, 40 perguntas isoladas × 3 | [v2] e [A] | Domínio correto 1,00 nas duas; 0 confusões de nível; ação correta A 107/120, v2 108/120 |
| Memória de nível em diálogo (C1) | [v2] | Persistência diferente da esperada: A 0,383 → v2 0,233, rótulos do pesquisador, n = 58: Δ −0,155. **Leitura frágil:** a concordância dos rótulos nesse campo é baixa (κ 0,13) |
| Falha conhecida **G4-014** | [v2] | "e na grad?" depois de uma declaração de pós-graduação recebe o nível persistido "pós" e recupera a Resolução 956/2025. Classe de erro introduzida pela persistência de nível (R2), ausente em A |
| Scope Gate | [comum] | Recusas induzidas por prefixo conversacional (G2-007, G2-009) e erro em "regime domiciliar" (G3-019). Variância em GRAD-15: 3/20 recusas com o pedido idêntico |

**Leitura.** O tratamento de escopo e nível em turno único é o da baseline. A v2 acrescenta memória de nível, que reduz a perda de contexto mas introduz o erro G4-014. O efeito isolado do nível declarado e do Scope Gate não foi medido.

## QP2 — Esclarecimento

É a dimensão diretamente afetada pela nova camada.

**C1:** 60 cenários sintéticos de desenvolvimento, construídos por geração automatizada, × 3 repetições, A × v2. O checkpoint decisivo foi rotulado pelo pesquisador às cegas em relação às saídas. Unidade: cenário, maioria de 3 repetições. IC 95 % por bootstrap agrupado.

| Métrica | Origem | A | v2 | Δ [IC 95 %] |
|---|---|---:|---:|---|
| Decisão conversacional correta (primária) | [v2] | 0,483 | 0,650 | **+0,167 [+0,033; +0,283]** |
| Idem, regra literal de contaminação por terceiro (sensibilidade) | [v2] | — | — | +0,150 [+0,017; +0,267] |
| Pergunta pretendida encaminhada à recuperação | [v2] | 0,333 | 0,550 | +0,217 [+0,100; +0,333] |
| Esclarecimento desnecessário | [v2] | 0,200 | 0,150 | −0,050 [−0,150; +0,067] (inconclusivo) |
| Pergunta descartada | [v2] | 0 | 0 | 0 |
| Falso consumo de pergunta nova (417 checkpoints, rótulos preliminares automatizados) | [v2] | 0 | 0 | 0 |
| Consistência 3/3 | [v2] | 1,00 | 0,90 (rótulos do pesquisador); 0,92 nos originais, 0,945 excluindo erros técnicos | — |
| Respostas aceitas sobre outra pergunta (180 execuções decisivas) | [v2] | 34 | 15 | — |

**Concordância** entre os rótulos do pesquisador e os rótulos preliminares automatizados do conjunto (não atribuídos ao pesquisador):

- decisão preferida: κ 0,71;
- nível do usuário depois do turno: κ 0,13.

**Pertinência da resposta entregue** (verificação H-2: 15 respostas por condição, descritiva):

| | A | v2 |
|---|---:|---:|
| Atende à pergunta pretendida | 6 | 5 |
| Atende, contando as parciais | 8 | 8 |

Parte dos encaminhamentos corretos da v2 termina na resposta de contingência do validador.

**Outras evidências da camada:**

| Evidência | Resultado |
|---|---|
| Política v1 → v2 (Etapa 7, DEV) | Falso consumo 12/417 → 0/417; retomada com nível de terceiro 16 → 0 |
| Critério E6 da Etapa 7 (dentro da gramática fechada) | **Não atendido:** v2 0,67 contra 0,89 de A′ |
| Custo marginal do Jev | ≈ US$ 0,00005 e ≈ 0,5 s por turno interpretado |

**Leitura.** A v2 apresentou ganho exploratório na **decisão** e no **encaminhamento** conversacional em relação a A. **Não demonstrou** melhoria na pertinência da resposta final. Os cenários são sintéticos e foram usados no desenvolvimento, de modo que o resultado não mostra generalização.

## QP3 — Controle temporal

| Evidência | Origem | Resultado |
|---|---|---|
| Condição B × D (5 + 5 perguntas temporais) | [A] | D: 0/15 e 0/20 trechos obsoletos entregues; B: 6/25 e 6/25. Recall menor em D. Não isola o filtro |
| Regressão controlada (22 casos) | [A] | Exposição a norma obsoleta 0/12; preservação histórica 6/6; classificação temporal 22/22 |
| Execução real automática | [A] | Classificação 9/9; exposição 0/10; preservação histórica 1/2; ação esperada 5/9 |
| Falhas registradas | [A] | TEMP-POS-004: comparação recuperou só uma resolução. TEMP-GRAD-005: a resposta negou uma alteração registrada |
| Redação histórica × vigência (TEMP-GRAD-002) | [A] | O defeito `chronology_unresolved` foi eliminado pelos campos `document_year` e `requested_year` |
| C2 (A × v2) | [v2] | Nenhuma evidência não elegível entregue, **mas C2 não contém casos temporais** |

**Leitura.** VersionFilter, intenção temporal e contexto temporal são [comum]. **A v2 não passou por experimento temporal próprio.** Em conversa, o comportamento completo depende também da interpretação anterior ao filtro: o G4-014 mostra que uma decisão errada de nível altera a entrada recebida pelo filtro.

## QP4 — Verificação da resposta

| Evidência | Origem | Resultado |
|---|---|---|
| GEN-01: 30 execuções da mesma pergunta, validador anterior ao congelado | [A] | Aceita na primeira geração 12/30; após nova tentativa 14/30; contingência 4/30; 22 respostas iniciais distintas a T = 0 |
| Rodada final da versão congelada | [A] | 11 gerações: 5 aceitas, 3 após nova tentativa, 3 contingências; **5 de 11 com afirmação sem suporte** |
| Validador variante (96 turnos gravados) | [A] | Menos falsos positivos (27 → 4 e 27 → 9), sem redução de falsos negativos; não adotado |
| Variantes "RAG adaptativo": suficiência pré-geração, recuperação complementar, validação semântica por afirmação | [A] | Nenhum ganho demonstrado; mais abstenções, latência e custo; não promovidas |
| C2, desfechos dos itens `answer` (66 execuções por condição) | [v2] | Aceitas A 39 / v2 41; nova tentativa 10 / 7; contingência 11 / 12 |
| H-2 (pertinência, v2) | [v2] | Ver QP2 |

**Leitura.** Geração e validador são [comum]. **Não há medição de fidelidade normativa da v2**, e o texto não afirma que a v2 a melhore. A taxa de afirmações sem suporte observada na versão congelada (5/11) se aplica à geração comum.

## QP5 — Avaliação com usuários

| Item | Estado |
|---|---|
| Plataforma | **Preparada**: interface web e backend v2 em Docker, execução local com um comando |
| Avaliação formal com estudantes | **Não executada** |
| Protocolo | Previsto no TCC II: participantes de graduação e pós, questionário, observação, tarefas com contrabalanceamento, análise temática |
| Requisitos antes de qualquer coleta | Verificação da necessidade de apreciação pelo sistema CEP/CONEP, termo de consentimento, LGPD, aviso de que as perguntas vão para provedores externos, aviso de que o protótipo pode produzir afirmações sem suporte, versão identificada do sistema |
| Restrição específica da v2 | O G4-014 está aberto; o protótipo não pode ser apresentado como fonte normativa para decisões acadêmicas |

Disponibilizar a interface **não** equivale a ter realizado a pesquisa de campo.

---

## Recuperação (transversal a QP1 e QP3)

| Medição | Origem | Resultado |
|---|---|---|
| C2, gold `reviewed_v2` (`evaluation/datasets/REVIEWED_V2.md`), itens que chegam à recuperação (n = 20) | [v2] e [A] | Recall@5 1,000; MRR@5 0,975; cobertura 1,000, iguais nas duas condições |
| Falhas antes da recuperação | [v2] e [A] | GRAD-02 e GRAD-11 sempre pedem esclarecimento, embora o gold espere resposta direta. Contando esses itens como 0: 0,909 / 0,886 |
| Número de trechos e reordenação (40 perguntas, gold original) | [A] | K = 5: recall 0,954, cobertura 36/40; K = 10 e reordenação sem ganho de ponta a ponta |

Os números das duas medições não são intercambiáveis: diferem no gold, no denominador e na definição.

## Contribuição

O protótipo demonstra a implementação e a caracterização exploratória de um assistente RAG normativo com:

- decisões explícitas de escopo;
- identificação do nível de ensino;
- controle temporal de normas;
- recuperação fundamentada;
- verificação programática da resposta;
- gestão de continuidade conversacional.

A v2 apresentou ganho exploratório na decisão e no encaminhamento conversacional em relação a A. Não demonstrou melhoria na pertinência da resposta final. A fidelidade das respostas segue como a principal limitação.

## §6. Recálculo das métricas

As métricas de C1, C2, C3, H-1 e H-2 foram recalculadas offline a partir dos dados brutos, por procedimento independente dos scripts originais. Os números acima já incorporam as correções:

| Correção | Efeito |
|---|---|
| Erros técnicos de provedor | Excluídos da consistência |
| "Aceitas sobre outra pergunta" | Denominador correto: 180 execuções decisivas |
| Recall de C2 | n = 20 |
| Uso indevido de nível de terceiro | 0/48 nas duas condições, pela definição da Etapa 7 |
| Regra literal de contaminação por terceiro | Relatada como sensibilidade |

Nenhuma correção inverte o sinal de uma estimativa. Uma segunda auditoria por outro auditor permanece prevista.
