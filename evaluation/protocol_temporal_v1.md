# Protocolo temporal V1 — dois casos documentais reais

> **Protocolo histórico.** As condições e comandos abaixo registram o experimento anterior à v3.4. Não descrevem a configuração atual; novas execuções exigem diretório de saída novo e os insumos da condição histórica. Veja [reprodução e limites](../docs/REPRODUCAO.md).

Dataset candidato de desenvolvimento, com uma execução exploratória por condição.
Este protocolo acrescenta dois corpora ao snapshot conjunto; os dados, IDs, vetores
e resultados anteriores permanecem congelados. Não constitui certificação jurídica
integral de vigência nem estudo confirmatório.

## Relações e evidência

1. Pós: a 658/2024 é integralmente revogada pela 956/2025, art. 62, VI.
   Os dois textos estão no índice; perguntas históricas podem usar a 658 com aviso.
2. Graduação: a 1.056, de **17/08/2026**, art. 1º, altera o texto introdutório
   do art. 68, §4º, do Anexo à 177/2012. A norma-base e suas alíneas a–g continuam
   elegíveis. O ato abre exceção para cursos em políticas/programas institucionais
   com docentes selecionados por edital; não elimina a regra geral.

A 177 consolidada foi conferida na fonte oficial idêntica ao PDF local (SHA-256),
especialmente p. 23. A revogação foi conferida na última página do pacote oficial
CEPEX 953–956 (p. 22 do PDF, p. 17 impressa da 956). A alteração foi conferida na
página única da 1.056. URLs, hashes e localização ficam na proveniência.
Erros OCR de símbolos, linhas pontilhadas e assinatura são preservados e declarados;
nenhum deles fundamenta uma diferença textual inventada.

As datas de assinatura identificam os atos. Os dispositivos de eficácia da 956
(art. 63) e da 1.056 (art. 2º) remetem à publicação; sua data não é inferida.
"Atual" significa a precedência expressamente documentada **entre os atos deste
snapshot fechado**, sem decidir retroatividade, transição de turmas ou direitos
adquiridos. O status global desconhecido da 177/956/1.056 é preservado; não autoriza
marcar a 177 como revogada nem ignorar a alteração expressa.

## Pipeline, índice e intervenção

Usar exclusivamente `ingest_documents`: PDF UFPI → conversor Docling existente
(Tesseract português, página completa) → Markdown intermediário → parser estrutural
existente → JSON por artigo → validação. Copiar para o RAG apenas JSON final e
proveniência. Alterações genéricas do parser são verificadas contra a saída antiga
da 956, sem reprocessar os corpora usados nos experimentos anteriores.

O indexador incremental exige fontes explícitas novas, verifica colisões antes
de chamadas, calcula embeddings somente para IDs ausentes e usa `collection.add`.
Não chama reset, synchronize ou upsert. Snapshots por ID incluem SHA-256 de texto,
metadados canônicos e vetor float32 little endian; verificar todos os 438 registros
anteriores após a adição. A origem histórica dos vetores antigos continua sem recibo.

Revogação: preservar a pré-exclusão por fonte antes do top 5 e a checagem defensiva
posterior. Pré-exclusão não é uma remoção de candidato recuperado. Comparar os
contextos B/D e apresentar também replay do filtro sobre os candidatos reais B,
com `pre_filter_references`, `removed_references` e `final_references`.

Alteração parcial: não excluir a fonte 177 no Chroma. Se seu art. 68 for recuperado,
substituir em memória somente a ocorrência única da redação anterior comprovada
pela redação exata do ato alterador, com atribuição explícita da fonte. Preservar
ID, distância, demais parágrafos e alíneas. Registrar original, resultado e regra
de precedência em `amended_references`. Se o trecho não coincidir, excluir somente
o chunk-alvo com `amendment_unresolved` e informar insuficiência; nunca declarar
revogação da norma-base. O corpus e o embedding originais não mudam.

Não forçar recuperação do ato alterador nem acrescentar um sexto chunk. O registro
documental pode fornecer a redação aplicável quando o chunk-base é recuperado;
essa aplicação é auditada separadamente do retrieval do ato. Não alterar Router,
modelo, embedding, temperatura, top_k=5, prompt principal V2, API ou Chroma.

História explícita ("como era", "qual era", "na época", "regra antiga" etc.)
mantém o texto original com aviso no contexto. "Segundo a 658/2024" também libera
a norma expressamente revogada, por consulta ao registry. Termos atuais ("hoje",
"atual", "vigente" etc.) têm precedência; simples menção do número não basta.
Comparações antigas/novas declaram a intenção histórica sem exigir regra atual
para um aluno específico. A heurística permanece limitada e independente do Router.

## Amostra e condições

Congelar os itens e qrels antes das chamadas. Cinco perguntas da pós e cinco da
graduação, separadas por `domain` e `temporal_relation` (`revocation`, `amendment`).
As referências contêm texto exato dos corpora, localização nos PDFs e fatos
candidatos. Não renomear o conjunto como gold validado; julgamentos dos avaliadores nulos.

| Condição | Setor | Version Filter |
|---|---|---|
| A `oracle` | manual/candidato | desligado |
| B `both` | ambas | desligado |
| C `router` | Router existente | desligado |
| D `router-version` | Router existente | ligado |

Executar obrigatoriamente B e D nos cinco itens de cada domínio, em quatro
diretórios novos. A/C ficam disponíveis no mesmo runner. Executar também smoke
A/B/C/D dos quatro itens existentes, com saídas novas. B×D combina roteamento e
versionamento; não atribuir toda diferença causalmente ao filtro. O replay sobre
os mesmos candidatos B isola apenas o mecanismo, sem nova geração ou métrica de
qualidade de resposta. Não ajustar perguntas, qrels ou configuração após resultados.

## Métricas e denominadores

Reutilizar Recall@5 e Wrong-norm@5 por `(norm_id, artigo)`. `applicable_norm_ids`
declara, antes das chamadas, os atos que sustentam a resposta: base e alterador
podem ser legítimos simultaneamente. Não contar origem diferente como erro jurídico.
Recall mede os documentos no contexto final, inclusive chunk-base com redação
atualizada; não concede um hit de retrieval ao ato que não foi recuperado.

- **Obsolete Context Rate@5:** chunks de normas inteiras expressamente obsoletas
  entregues como atuais / chunks entregues nas consultas com geração. Microagregar
  contagens; histórico não é exposição como atual. Não confundir com alteração parcial.
- **Compliance Violation Rate:** consultas com geração e ao menos um contexto de
  norma obsoleta **ou redação anterior de dispositivo alterado entregue como atual** /
  consultas com geração. É exposição de contexto, não julgamento jurídico da resposta.
- **Current-Norm Hit@5:** presença de ao menos um par em `current_evidence` no contexto
  final. Inclui suporte do ato alterador exato aplicado pelo registry, registrado em
  `amended_references`; isso não muda o Recall de retrieval. Sem qrels atuais: nulo.
- **Outdated Provision Exposure Rate (OPER):** para consultas **atuais** previamente
  anotadas com `target_provision`, número de consultas com geração nas quais a redação
  anterior exata desse dispositivo foi entregue como aplicável / número dessas
  consultas com geração. Históricas e consultas a outros dispositivos ficam fora.
  Sem consultas elegíveis: nulo. Falhas/esclarecimentos sem geração são contabilizados
  separadamente; uma recuperação vazia não recebe crédito automático de qualidade.

Registrar numeradores/denominadores, falhas e alterações aplicadas. Reportar por
domínio e relação, sem inferência populacional. Taxa zero com baixo Recall não
demonstra qualidade. A validade material e qualidade das respostas exigem revisão
por avaliadores independentes; não usar GraphRAG ou RAGAS nesta etapa.

## Reprodução

Na pasta `code/`, com ambiente configurado e coleção incrementada:

```powershell
# Geração histórica; o runner seleciona o perfil duas-regulacoes e exige seu índice.
$env:GENERATION_MODE="free_text_v2"
python -m rag_baseline.experiment_v2 --condition both --dataset ../evaluation/datasets/temporal_pos_v1.json --output ../evaluation/results/temporal_pos_B_001
python -m rag_baseline.experiment_v2 --condition router-version --dataset ../evaluation/datasets/temporal_pos_v1.json --output ../evaluation/results/temporal_pos_D_001
python -m rag_baseline.experiment_v2 --condition both --dataset ../evaluation/datasets/temporal_graduacao_v1.json --output ../evaluation/results/temporal_grad_B_001
python -m rag_baseline.experiment_v2 --condition router-version --dataset ../evaluation/datasets/temporal_graduacao_v1.json --output ../evaluation/results/temporal_grad_D_001
```

O runner valida todos os corpora e o índice sem modificá-los, salva configuração,
hashes, textos/contextos pré/pós, redações aplicadas e recibos disponíveis. Não salva
segredos, raciocínio interno ou notas de avaliação fabricadas. Saídas antigas nunca são
sobrescritas. Nenhum push ou merge faz parte desta tarefa.
