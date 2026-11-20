# Demos reais de roteamento V2

> **Registro histórico.** Configuração, resultados, contagens de testes e estados descritos referem-se à execução documentada, anterior à v3.4. Para a versão atual, consulte o [guia de evidências e reprodução](../../README.md).

Traces da primeira rodada de `stability_001`, selecionados pela regra do protocolo. Nenhuma pergunta foi reformulada. O experimento mede somente roteamento; nenhum probe alimentou respostas ou referencias finais.

Comando real, a partir de `code/`:

```powershell
python -m rag_baseline.experiment_v2 --routing-v2-stage stability --repetitions 10 --calibration ../evaluation/results/router_v2_exploratory_001/dev_001/frozen_threshold_windows_v1.json --output ../evaluation/results/router_v2_exploratory_001/stability_001
```

O destino acima ja existe: para reproduzir, use outro diretorio. Todos os 60 pares ficam preservados em [pairs.jsonl](stability_001/pairs.jsonl). [Tres traces completos](demo_traces.json).

## Exemplo 1: CONTROL-POS, repeticao 1

> Na pós-graduação, posso cancelar uma disciplina?

| Politica | V1 | Probe | Rota final | Judge | Erro |
|---|---|---|---|---|---|
| intent_v1 | pos_graduacao | False | pos_graduacao | not_called | nenhum |
| adaptive_distribution_v2 | pos_graduacao | False | pos_graduacao | not_called | nenhum |
| adaptive_llm_v2 | pos_graduacao | False | pos_graduacao | not_called | nenhum |

Uma chamada V1 compartilhada; zero embeddings, retrievals e judges adicionais nas tres politicas.

## Exemplo 2: SMOKE-004, repeticao 1

> Posso cancelar uma disciplina?

| Politica | V1 | Probe | Rota final | Judge | Erro |
|---|---|---|---|---|---|
| intent_v1 | esclarecer | False | esclarecer | not_called | nenhum |
| adaptive_distribution_v2 | esclarecer | True | esclarecer | not_called | nenhum |
| adaptive_llm_v2 | esclarecer | True | esclarecer | invalid | judge_invalid |

Probe SHA-256: `25cc18043b49e466fd6e943ecce56599a127d606ed2a8489f91fa9873d104a76`. Mesmo objeto para R1/R2. Threshold: **0,65**.

Counts: `{'graduacao': 8, 'pos_graduacao': 2}`. Massas: `{'graduacao': 1.5956349206349207, 'pos_graduacao': 1.3333333333333333}`. Dominancia: **0.544777**.

| Rank | ID | Setor | Distancia cosseno |
|---:|---|---|---:|
| 1 | `ufpi-956-2025-art-37-idx-000035` | pos_graduacao | 0.315154 |
| 2 | `ufpi-177-2012-art-229-idx-000227` | graduacao | 0.326024 |
| 3 | `ufpi-658-2024-art-37-idx-000036` | pos_graduacao | 0.334744 |
| 4 | `ufpi-177-2012-art-347-idx-000345` | graduacao | 0.353153 |
| 5 | `ufpi-177-2012-art-344-idx-000342` | graduacao | 0.355195 |
| 6 | `ufpi-177-2012-art-349-idx-000347` | graduacao | 0.362113 |
| 7 | `ufpi-177-2012-art-352-idx-000350` | graduacao | 0.368852 |
| 8 | `ufpi-177-2012-art-343-idx-000341` | graduacao | 0.373442 |
| 9 | `ufpi-177-2012-art-345-idx-000343` | graduacao | 0.376611 |
| 10 | `ufpi-177-2012-art-348-idx-000346` | graduacao | 0.377337 |

R1 preservou esclarecimento com evidencia mista abaixo do threshold. R2 terminou em esclarecimento por **fallback de saida invalida**: isso e erro nas metricas, nao sucesso semantico do judge. A tentativa foi mantida.

## Exemplo 3: TEMP-GRAD-001, repeticao 1

> Qual é a regra vigente do art. 68, §4º da graduação da UFPI para designar o coordenador de estágio em cursos de programas institucionais com docentes selecionados por edital, sem vínculo com a UFPI?

| Politica | V1 | Probe | Rota final | Judge | Erro |
|---|---|---|---|---|---|
| intent_v1 | esclarecer | False | esclarecer | not_called | nenhum |
| adaptive_distribution_v2 | esclarecer | True | graduacao | not_called | nenhum |
| adaptive_llm_v2 | esclarecer | True | graduacao | valid | nenhum |

Probe SHA-256: `fb146e2552780d9e7411e6cd4bac7a0f16a24e400635ae0aaa45c2d557be94d4`. Mesmo objeto para R1/R2. Threshold: **0,65**.

Counts: `{'graduacao': 7, 'pos_graduacao': 3}`. Massas: `{'graduacao': 2.328968253968254, 'pos_graduacao': 0.6}`. Dominancia: **0.795150**.

| Rank | ID | Setor | Distancia cosseno |
|---:|---|---|---:|
| 1 | `ufpi-1056-2026-art-1-idx-000000` | graduacao | 0.250853 |
| 2 | `ufpi-177-2012-art-68-idx-000067` | graduacao | 0.291571 |
| 3 | `ufpi-658-2024-art-51-idx-000050` | pos_graduacao | 0.293338 |
| 4 | `ufpi-177-2012-art-65-idx-000064` | graduacao | 0.295938 |
| 5 | `ufpi-177-2012-art-87-idx-000086` | graduacao | 0.311278 |
| 6 | `ufpi-956-2025-art-41-idx-000039` | pos_graduacao | 0.313239 |
| 7 | `ufpi-177-2012-art-88-idx-000087` | graduacao | 0.315605 |
| 8 | `ufpi-177-2012-art-64-idx-000063` | graduacao | 0.318746 |
| 9 | `ufpi-177-2012-art-66-idx-000065` | graduacao | 0.331652 |
| 10 | `ufpi-658-2024-art-53-idx-000052` | pos_graduacao | 0.331695 |

O nivel graduacao estava escrito na pergunta. V1 pediu esclarecimento; o probe concentrou massa na graduacao e R1/R2 recuperaram a rota esperada nesta chamada. O caso pertence somente a DEV/regressao e nao comprova ganho geral.
