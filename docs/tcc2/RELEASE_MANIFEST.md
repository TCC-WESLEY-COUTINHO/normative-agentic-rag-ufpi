# Manifesto da release do protótipo TCC II (A″-J v2)

**Estado: preparada localmente e não publicada.** Nenhum push foi feito.

## 1. Referências locais da release

| Tipo | Nome | Commit | Conteúdo |
|---|---|---|---|
| Tag | `exp-baseline-2026-11-04` | `8fb690e` | Baseline experimental |
| Tag | `tcc2-cond-A` | `c8746b6` | Condição A (código de `8fb690e`, mais o executor de avaliação) |
| Tag | `tcc2-cond-A1` | `3f11b4f` | Condição A′ |
| Tag | `tcc2-cond-v1` | `923d2de` | Condição A″-J v1 |
| Tag | `tcc2-cond-v2` | `0433c0b` | **Condição A″-J v2** |
| Branches | `main` e `release/tcc2-prototype` (mesmo commit) | HEAD | v2, interface Bisco, Docker, gold `reviewed_v2` e documentação |
| Branches | `tcc2/cond-A`, `fix/baseline-conversation-r1-r2`, `experiment/conversation-interpreter-a2`, `experiment/conversation-interpreter-a2-v2` | — | Uma por condição |

Em checkout novo, cada tag de condição reproduz todos os arquivos dos manifestos SHA-256 registrados: A 201, A′ 202, v1 213 e v2 215.

## 2. Imagens

| Imagem | Origem | Verificação no build |
|---|---|---|
| `tcc2-prototype-backend:<tag>` | `deploy/backend/Dockerfile` | Fontes do backend idênticas ao manifesto congelado (114 arquivos, comparação com quebras de linha normalizadas) |
| `tcc2-prototype-interface:<tag>` | `deploy/interface/Dockerfile` | — |

Nenhuma credencial é incluída nas imagens.

## 3. Varredura de publicação

| Verificação | Resultado |
|---|---|
| Segredos em todo o histórico (todas as refs), varredura automática | 206 achados, todos falsos positivos: 197 hashes SHA-256 em manifestos, 6 parâmetros `key=` de URLs públicas do SIGAA para os PDFs das resoluções, 2 fingerprints GPG públicos da imagem oficial do Python e 1 placeholder (`SEU_AUTH_SECRET`) |
| `.env` ou arquivos de chave versionados | Nenhum, em todo o histórico. Só `.env.example` |
| Maior arquivo do histórico | 19,1 MB (`evaluation/results/container_runtime_smoke_v1_001/initial_audit.json`), abaixo do limite do GitHub |
| Revisão dos commits locais não publicados | Os commits da release não foram sinalizados. Commits históricos anteriores têm termos de processo de revisão e de ferramentas em registros de experimentos e mensagens; precisam de decisão do pesquisador antes de publicar o histórico integral |

## 4. Restrições de redistribuição: não publicar sem decisão

| Material | Motivo |
|---|---|
| `articles/study/*.pdf`, `articles/writing/*.pdf` | Artigos e livros de terceiros, protegidos por direito autoral (por exemplo, *Writing for Computer Science*, Springer) |
| `TCC.pdf`, `paper_tcc.pdf` | Trabalho de Melo e Sousa; publicação depende dos autores |
| `data/*.pdf` | Ato normativo público da UFPI. Redistribuição provavelmente admissível, mas confirmar |
| Índice Chroma (`.local/index`) | Não versionado: arquivo grande, derivado e reconstruível a partir do corpus |
| Dados brutos de execução e anotações do pesquisador | Mantidos fora do repositório |

Como esses PDFs já estão no histórico, **publicar o histórico integral os redistribui**.

## 5. Recomendação de publicação

Criar um **repositório público separado**, com um único commit inicial gerado a partir da árvore de `release/tcc2-prototype`:

- sem `articles/*.pdf`, `TCC.pdf` e `paper_tcc.pdf`;
- com tags equivalentes às condições, ou com os manifestos das condições anexados;
- preservando o histórico experimental completo apenas no repositório privado.

Essa via não reescreve o histórico existente nem exige force push. Executá-la depende de autorização do pesquisador, bem como a escolha da licença das contribuições do TCC II.
