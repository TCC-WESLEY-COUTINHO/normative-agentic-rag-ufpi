# Gold complexo v3 (`gold_v3_complexo.json`)

Conjunto de 31 perguntas usado no [conjunto complexo](../../docs/RESULTADOS.md#conjunto-complexo) da comparação exploratória v3.4 × v2. É um conjunto de desenvolvimento, não uma avaliação de generalização.

- SHA-256 de `gold_v3_complexo.json`: `e0f0949504a2d6df7c6e1ee767fb4298403c4eae8f88f0e431fa81553ea353df` (idêntico ao arquivo final registrado na construção do conjunto; nenhum campo foi removido ou alterado).
- Normas: Res. 177/2012 (graduação), Res. 1.056/2026 (altera a 177/2012), Res. 956/2025 (pós-graduação stricto sensu, vigente) e Res. 658/2024 (pós-graduação, revogada pela 956/2025), identificadas como `ufpi-177-2012`, `ufpi-1056-2026`, `ufpi-956-2025` e `ufpi-658-2024`.

## Composição

| Tipo (`tipo`) | Itens | Ação esperada |
|---|---:|---|
| `sintese` — junta 2 a 4 artigos ou dispositivos | 4 | `answer` |
| `excecao` — regra geral com exceção, vedação ou condição | 4 | `answer` |
| `caso_concreto` — aplica a regra a dados informados | 4 | `answer` |
| `temporal` — depende de alteração ou revogação | 4 | `answer` |
| `premissa_falsa` — a resposta corrige a premissa | 4 | `answer` |
| `comparacao` — mesma questão na graduação e na pós | 4 | `answer` |
| `sem_resposta` — assunto não regulado pelas normas | 4 | `abstain` |
| `ambigua` — duas leituras normativas no mesmo nível | 3 | `clarify` |

Por nível (`nivel`): 14 `graduacao`, 13 `pos_graduacao` e 4 `ambos`. IDs `G3-01` a `G3-32`, sem `G3-27`.

Campos: `id`, `nivel`, `tipo`, `pergunta`, `acao_esperada`, `evidencia` (pares norma–artigo), `fatos_obrigatorios`, `resposta_referencia` e `justificativa` (por que o item pertence ao tipo e por que a ação esperada é essa).

## Construção

- Foram redigidas 32 perguntas, 2 de graduação e 2 de pós-graduação por tipo, mais 4 de comparação, somente a partir do texto integral das quatro resoluções, artigo por artigo.
- Para cada norma, sorteou-se uma ordem dos artigos ainda não usados nos conjuntos de perguntas anteriores; as perguntas partem do início dessa ordem, e artigos já usados entram apenas quando indispensáveis (por exemplo, nas perguntas temporais de graduação, que dependem da Res. 1.056/2026). A redação seguiu a regra de não repetir assunto entre perguntas.
- Cada item passou por um procedimento de revisão com decisão do pesquisador, confrontado com o texto das resoluções: clareza e nível, coerência do tipo, ação esperada, evidência, fatos obrigatórios e resposta de referência.
- Resultado: 1 item excluído (`G3-27`, tipo `ambigua`, cujas duas leituras não levavam a regras concorrentes) e 6 itens corrigidos (`G3-03`, `G3-04`, `G3-13`, `G3-14`, `G3-28` e `G3-31`), com ajustes na evidência, nos fatos obrigatórios ou na resposta de referência. Os demais itens foram mantidos sem alteração.
- Não houve revisão normativa por especialista: as respostas de referência descrevem o conteúdo das normas indexadas, não uma interpretação jurídica certificada.

Versão legível, gerada do JSON: [GOLD_V3_COMPLEXO.md](GOLD_V3_COMPLEXO.md).
