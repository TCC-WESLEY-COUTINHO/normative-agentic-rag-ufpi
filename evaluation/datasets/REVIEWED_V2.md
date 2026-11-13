# Gold normativo `datasetgold_reviewed_v2`

Revisão do gold v2 (`graduacao_v2.json`, `pos_graduacao_v2.json`, commit `8fb690e5`) usada na avaliação final do protótipo do TCC II.

- Mesmo esquema e mesmas 40 perguntas (20 de graduação, 20 de pós-graduação).
- Nenhuma pergunta (`question`) e nenhuma ação esperada (`expected_action`) foram alteradas.
- Os arquivos v2 originais permanecem inalterados ao lado destes.

| Arquivo | Conteúdo |
|---|---|
| `graduacao_reviewed_v2.json` | 20 itens de graduação (6 `answer`, 14 `clarify`) |
| `pos_graduacao_reviewed_v2.json` | 20 itens de pós-graduação (16 `answer`, 4 `clarify`) |
| `datasetgold_reviewed_v2.json` | Os dois arquivos combinados |

Os itens são idênticos aos usados na avaliação. O bloco `review` de cada arquivo registra a origem (caminho, commit e SHA-256 do arquivo v2), a data, o escopo, os campos novos e as regras de avaliação.

## Escopo

- 26 propostas de revisão, em 11 dos 40 itens.
- Os 29 itens restantes são idênticos ao gold v2.
- O status dos arquivos permanece `candidate_gold`.
- Não houve revisão normativa por especialista: as referências descrevem o conteúdo das normas indexadas, não uma interpretação jurídica certificada.

## Campos novos

| Campo | Significado |
|---|---|
| `optional_facts` | Fatos aceitos como conteúdo desejável, não exigidos |
| `optional_evidence` | Evidência complementar, fora do conjunto obrigatório. Não entra no denominador de recall nem na relevância do MRR |

## Itens alterados em relação ao gold v2

| Item | Campos alterados |
|---|---|
| GRAD2-001 | `evidence` (art. 359 passou a opcional), `optional_evidence`, `optional_facts`, `reference_answer`, `required_facts`, `audit_note` |
| GRAD2-004 | `audit_note` |
| GRAD2-006 | `conditional_answer`, `optional_facts` |
| GRAD2-009 | `conditional_answer`, `optional_facts` |
| GRAD2-014 | `conditional_answer` |
| GRAD2-015 | `conditional_answer` |
| POS2-002 | `reference_answer` |
| POS2-004 | `reference_answer`, `required_facts` |
| POS2-008 | `reference_answer`, `required_facts` |
| POS2-009 | `optional_facts`, `reference_answer`, `required_facts` |
| POS2-010 | `optional_facts`, `reference_answer`, `required_facts` |

## Regras de avaliação

| Regra | Itens | Conteúdo |
|---|---|---|
| R-CLARIFY-SEPARADA | GRAD2-006, GRAD2-014, GRAD2-015 | A ação de esclarecer e o conteúdo substantivo condicional são avaliados separadamente; a resposta condicional corretamente delimitada é aceita |
| R-POS2-002-NOTA-FINAL | POS2-002 | Aceita resposta direta ou condicionada à "nota final" |
| R-POS2-008-PARCIAL | POS2-008 | Aplicar os 60 dias à entrega da versão final, sem ressalva, atende parcialmente ao primeiro fato: o art. 54, § 1º, fixa o prazo para efetuar as modificações |

## Limitações conhecidas

- **GRAD2-009:** a `conditional_answer` reproduz o art. 287, §§ 3º e 4º, sem resolver a tensão entre eles (regime de blocos × regime de crédito).
- **GRAD2-001:** a relação entre o art. 124, parágrafo único (componentes aproveitados entram no IRA), e o art. 257 (crédito concedido de outra IES não entra) aparece como fato opcional, não exigido.
- **R-CLARIFY-SEPARADA:** a regra vale só para os três itens listados; os demais itens `clarify` não têm regra definida.
- **POS2-010:** o segundo fato obrigatório mantém a redação anterior da expressão "estudos complementares".
- **GRAD2-014:** a `conditional_answer` começa com "Na graduação, Não deve…" (maiúscula preservada da redação original).
- **POS2-019 e POS2-020:** o texto enviado nos experimentos (arquivos Markdown de `data/`) difere do campo `question`.

## Uso

- Na avaliação final, a recuperação foi pontuada lendo estes arquivos JSON diretamente. O harness usado e os registros brutos de execução não fazem parte deste repositório.
- O carregador antigo (`evaluation/adaptive_rag/dataset.py`) lê os caminhos fixos `*_v2.json` e as respostas de referência dos arquivos Markdown. Ele não vê as alterações deste gold.

Resultados obtidos com este gold estão em `docs/tcc2/AVALIACAO_TCCII_JEV_V2.md`.
