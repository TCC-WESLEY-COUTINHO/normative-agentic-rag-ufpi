# Implantação do chatbot RAG da UFPI em Linux

Este guia descreve o que pode ser reproduzido a partir do repositório na revisão atual. Os comandos de produção usam Docker Compose e devem ser executados a partir de `code/`.

## 1. Arquitetura resumida

O projeto contém quatro componentes operacionais:

1. **Streamlit**: interface web, publicada na porta `8501`.
2. **FastAPI/LangGraph**: API e execução dos agentes, na porta `8080`. O agente padrão é `chatbot_ufpi_v2`.
3. **PostgreSQL local**: checkpoints, histórico e store do LangGraph. Não é a base vetorial do RAG.
4. **Supabase remoto**: base de conhecimento do RGG, acessada por RPC. Os embeddings das consultas são gerados pela OpenAI.

Fluxo principal:

```text
navegador -> Streamlit:8501 -> FastAPI:8080 -> OpenAI (LLM e embeddings)
                                            -> Supabase (RPCs do RAG)
                                            -> PostgreSQL (memória LangGraph)
```

A API e o frontend ficam vinculados, por padrão, a `127.0.0.1` nas portas `8080` e `8501`, respectivamente. O PostgreSQL não publica porta no host.

O `compose.prod.yaml` atual provisiona PostgreSQL e deve ser tratado como uma implantação PostgreSQL. O código também suporta SQLite e MongoDB, mas usar esses backends exige adaptar serviços, dependências, volumes, redes e variáveis do Compose.

## 2. Pré-requisitos

No servidor, são necessários:

- Linux de 64 bits suportado pelo Docker;
- acesso administrativo para instalar software e administrar o serviço Docker;
- Git;
- Docker Engine;
- plugin Docker Compose V2;
- `curl` para o smoke test;
- acesso de saída HTTPS aos endpoints da OpenAI e do projeto Supabase;
- credenciais válidas para OpenAI e Supabase;
- definição pré-existente dos objetos RAG no Supabase.

Em Debian/Ubuntu, Git, certificados e curl podem ser instalados com:

```bash
sudo apt-get update
sudo apt-get install -y git ca-certificates curl
```

Instale Docker Engine e o plugin Compose pelo procedimento oficial correspondente à distribuição: <https://docs.docker.com/engine/install/>. Depois valide:

```bash
git --version
docker --version
docker compose version
curl --version
docker run --rm hello-world
```

Se o usuário não tiver acesso ao socket Docker, execute os comandos Docker com `sudo` ou configure a delegação conforme a política do servidor. Pertencer ao grupo `docker` equivale, na prática, a conceder privilégios elevados.

**LACUNA DE REPRODUTIBILIDADE:** o repositório não define distribuição Linux, versões mínimas de Git/Docker para produção nem procedimento de endurecimento do daemon. O Compose de desenvolvimento menciona Compose `>=2.23.0` por causa do modo Watch; o arquivo de produção requer Compose V2.

Python não é necessário no host para a implantação com Docker. Para desenvolvimento nativo, instale Python 3.11 ou superior e `uv`; as imagens usam Python 3.12.3.

## 3. Requisitos mínimos conhecidos

Conhecidos pelo código:

- arquitetura capaz de executar imagens Linux de Python 3.12 e PostgreSQL 16;
- portas TCP `8501` para o frontend e `8080` para acesso local à API;
- armazenamento persistente para PostgreSQL;
- DNS e saída TCP/443 para OpenAI e Supabase;
- relógio do servidor sincronizado para TLS e chamadas de API.

**LACUNA DE REPRODUTIBILIDADE:** não há medições ou limites mínimos de CPU, RAM, disco, IOPS, concorrência ou latência. Dimensione inicialmente em ambiente de homologação e monitore memória, disco do PostgreSQL, tempo de resposta e consumo das APIs externas.

## 4. Clonagem do projeto

A origem registrada no repositório é:

```bash
git clone https://github.com/TCC-WESLEY-COUTINHO/rag-chatbot-ufpi.git
cd rag-chatbot-ufpi
git status --short
git rev-parse --short HEAD
```

O último comando registra a revisão implantada. Os demais comandos deste guia partem de:

```bash
cd code
```

Não use o endereço `JoshuaC215/agent-service-toolkit`; ele pertence ao template original.

## 5. Preparação das variáveis de ambiente

Crie o arquivo local e proteja sua leitura:

```bash
cd code
cp .env.example .env
chmod 600 .env
```

Edite `.env` e preencha, no mínimo:

```dotenv
OPENAI_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
POSTGRES_PASSWORD=
AUTH_SECRET=
```

Use um valor aleatório forte para `POSTGRES_PASSWORD`. `AUTH_SECRET` pode ficar vazio para a aplicação executar, mas seu uso é fortemente recomendado em qualquer implantação em servidor; quando definido, também deve ser aleatório e forte. Como o código monta a URI PostgreSQL sem URL-encoding, limite `POSTGRES_USER`, `POSTGRES_PASSWORD` e `POSTGRES_DB` a letras, números, `_` e `-`.

Não coloque aspas desnecessárias, não versione `.env` e não reutilize senhas pessoais.

Antes do build, confirme que o arquivo continua ignorado:

```bash
git check-ignore .env
git status --short
```

## 6. Explicação das variáveis

### Obrigatórias para o chatbot UFPI

| Variável | Uso confirmado no código |
| --- | --- |
| `OPENAI_API_KEY` | LLM OpenAI e embeddings `text-embedding-3-small` usados nas consultas RAG. |
| `SUPABASE_URL` | URL do projeto Supabase que contém a base do RGG. |
| `SUPABASE_KEY` | Chave usada pelo cliente Supabase para executar RPCs. O nível de privilégio esperado não está documentado. |

Embora o framework aceite outros provedores de LLM, o RAG UFPI continua exigindo OpenAI para embeddings.

### Obrigatória no Compose de produção

| Variável | Uso |
| --- | --- |
| `POSTGRES_PASSWORD` | Senha do PostgreSQL de memória/checkpoints; o Compose recusa valor ausente. |

### Opcionais com padrão no Compose de produção

| Variável | Uso |
| --- | --- |
| `POSTGRES_USER` | Usuário do PostgreSQL; padrão `rag_chatbot`. |
| `POSTGRES_DB` | Banco do LangGraph; padrão `rag_chatbot`. |
| `DATABASE_TYPE` | `postgres` nesta implantação. Embora o código aceite `sqlite` e `mongo`, esses backends exigem adaptar o Compose. |
| `AUTH_SECRET` | Bearer token da API. Opcional para execução, mas fortemente recomendado em servidor. |

O Compose força `POSTGRES_HOST=postgres`, `POSTGRES_PORT=5432`, `HOST=0.0.0.0` e `PORT=8080` dentro dos containers.

### Opcionais do fluxo principal

| Variável | Padrão/comportamento |
| --- | --- |
| `DEFAULT_MODEL` | Com OpenAI ativa, `gpt-4o-mini` quando não informado. |
| `POSTGRES_APPLICATION_NAME` | Identifica pools; padrão do template no código é `agent-service-toolkit`. |
| `POSTGRES_MIN_CONNECTIONS_PER_POOL` | Padrão `1`. |
| `POSTGRES_MAX_CONNECTIONS_PER_POOL` | Padrão no código `1`; exemplo recomenda `3`. Deve ser maior ou igual ao mínimo. |
| `API_BIND_ADDRESS` | Endereço publicado da API; produção usa `127.0.0.1` por padrão. |
| `FRONTEND_BIND_ADDRESS` | Endereço publicado do Streamlit; padrão `127.0.0.1`. Use `0.0.0.0` explicitamente apenas para exposição direta intencional. |
| `AGENT_URL` | URL da API usada pelo frontend; sobrescrita para `http://agent_service:8080` no Compose. |
| `MODE` | Valor `dev` habilita reload do Uvicorn; deixe vazio em produção. |
| `LANGCHAIN_*` | Configuração opcional de tracing LangSmith lida pela classe Settings. |
| `LANGFUSE_*` | Tracing Langfuse opcional. |

### Configurações alternativas ainda suportadas

O código mantém suporte a Azure OpenAI, DeepSeek, Anthropic, Google Gemini, Vertex AI, Groq, OpenRouter, AWS Bedrock, Ollama e endpoint compatível com OpenAI. As respectivas variáveis permanecem no `.env.example`.

Fora do `compose.prod.yaml` atual, o código permite `DATABASE_TYPE=sqlite`, usando `SQLITE_DB_PATH`, ou `DATABASE_TYPE=mongo`, usando obrigatoriamente `MONGO_HOST`, `MONGO_PORT` e `MONGO_DB`; as três variáveis de autenticação Mongo devem ser definidas juntas. O store de longo prazo do modo Mongo continua em memória, conforme o código. Não basta alterar `DATABASE_TYPE` no `.env`: adapte o Compose para o backend escolhido.

`AWS_KB_ID`, `OPENWEATHERMAP_API_KEY` e os provedores alternativos vieram do template e atendem agentes ou ferramentas fora do fluxo UFPI padrão. `LANGSMITH_*` foi mantido comentado por compatibilidade potencial de bibliotecas, mas a classe Settings lê `LANGCHAIN_*`.

## 7. Diferença entre os bancos e serviços

| Componente | Finalidade | Persistência |
| --- | --- | --- |
| PostgreSQL do Compose | Checkpoints, histórico e store do LangGraph | Volume `postgres_data`; estruturas criadas pelas bibliotecas LangGraph na inicialização. |
| Supabase remoto | Chunks, embeddings e RPCs de recuperação do RGG | Gerenciado fora deste Compose e fora deste repositório. |
| SQLite | Alternativa local de checkpoint | Exige Compose adaptado; store de longo prazo em memória. |
| MongoDB | Alternativa de checkpoint | Não provisionado pelo Compose; store de longo prazo em memória. |
| Chroma | Implementação RAG legada disponível em scripts/tools | Diretório local `chroma_db`; não usado pelos agentes UFPI registrados. |

O PostgreSQL local não recebe embeddings e não precisa de pgvector para a função de memória observada no código.

## 8. Configuração da base de conhecimento

O material versionado está em:

- `scripts/RGG_markdown.txt`: fonte textual usada pelos chunkers;
- `scripts/chunks_v2.py`: extrai um chunk por artigo;
- `scripts/chunks_v2.json`: chunks v2 já gerados;
- `scripts/embedding_load_v2.py`: gera embeddings e insere os registros;
- `scripts/chunks.py`, `chunks.json` e `embedding_load.py`: versão legada.

Metadados v2 produzidos:

- `fonte`;
- `titulo_numero`, `titulo_nome`;
- `capitulo_numero`, `capitulo_nome`;
- `secao_numero`, `secao_nome`;
- `subsecao_numero`, `subsecao_nome`;
- `artigo_numero`, `artigo`.

Para regenerar apenas o JSON, a partir de `code/scripts`:

```bash
python chunks_v2.py
```

Esse comando exige Python e sobrescreve `chunks_v2.json`; revise o diff antes de aceitar uma nova versão.

Para ingerir em uma base já preparada:

```bash
cd code/scripts
python embedding_load_v2.py
```

O script usa `OPENAI_API_KEY`, `SUPABASE_URL` e `SUPABASE_KEY`, gera embeddings em lotes de 100 e insere na tabela `documentos_embeddings_v2`.

A ingestão não é idempotente: não há upsert, chave natural, limpeza ou detecção de duplicatas. Faça backup e confirme que a tabela de destino está no estado esperado antes de executar.

## 9. Configuração de Supabase e pgvector

O cliente da aplicação chama o Supabase por HTTPS; nenhum container Supabase é iniciado localmente.

Evidências do uso vetorial:

- modelo fixo `text-embedding-3-small`;
- vetor da consulta enviado como `query_embedding`;
- limiar padrão `0.4`;
- quatro resultados na busca semântica;
- filtros enviados como objeto `filtros_metadados`.

A presença de RPCs de similaridade sobre embeddings indica uso de um tipo vetorial e provavelmente da extensão PostgreSQL `vector` (pgvector), mas a extensão não é declarada no repositório.

**LACUNA DE REPRODUTIBILIDADE:** não existem migrations, dumps de schema ou SQL para habilitar pgvector, criar tabelas, índices, políticas RLS, permissões ou RPCs. Recupere as definições originais do projeto Supabase e versione-as posteriormente. Não tente reconstruí-las apenas a partir deste guia.

**LACUNA DE REPRODUTIBILIDADE:** o código não informa se `SUPABASE_KEY` deve ser uma chave anônima, de serviço ou outra chave, nem quais políticas RLS permitem a operação. Aplique o menor privilégio possível depois de recuperar a configuração original.

## 10. Objetos externos exigidos pelo código

### Objetos atuais

`match_documentos_v2` recebe:

```text
query_embedding: lista de números
match_threshold: número
match_count: inteiro
filtros_metadados: objeto
```

O código espera uma lista de linhas contendo:

- `conteudo`;
- `metadados`;
- `similarity` para a busca semântica.

`match_documentos_metadados_only` recebe:

```text
filtros_metadados: objeto
match_count: inteiro
```

O código espera `conteudo` e `metadados`; `similarity` é aceito se existir.

A ingestão v2 escreve na tabela `documentos_embeddings_v2`, com campos inferidos `conteudo`, `embedding` e `metadados`. A definição da RPC não permite provar que ela lê essa mesma tabela.

### Objetos legados

Os scripts antigos citam:

- tabela `documentos_embeddings`, incluindo um campo `id`;
- RPC `match_documentos`;
- os mesmos parâmetros básicos de busca vetorial.

**LACUNA DE REPRODUTIBILIDADE:** a dimensionalidade não é fixada no código, pois a chamada OpenAI omite o parâmetro `dimensions`. A coluna SQL deve coincidir com a dimensão devolvida pelo modelo, mas a declaração da coluna não está presente.

## 11. Build

Valide primeiro a interpolação do Compose, sem iniciar serviços:

```bash
cd code
docker compose --env-file .env -f compose.prod.yaml config
```

Depois construa as imagens:

```bash
docker compose --env-file .env -f compose.prod.yaml build --pull
```

O backend instala as dependências travadas por `uv.lock`. O frontend instala apenas o grupo `client`.

**LACUNA DE REPRODUTIBILIDADE:** as imagens base usam tags (`python:3.12.3-slim` e `postgres:16`), não digests imutáveis. Builds em datas distintas podem incorporar camadas diferentes dentro da mesma tag.

## 12. Inicialização dos serviços

```bash
docker compose --env-file .env -f compose.prod.yaml up -d
docker compose --env-file .env -f compose.prod.yaml ps
```

Ordem esperada:

1. PostgreSQL inicia e passa em `pg_isready`;
2. a API inicia, cria/configura estruturas do LangGraph e responde em `/health`;
3. o Streamlit inicia e responde em `/_stcore/health`.

A rede `database` é interna. A API também participa da rede `app` para acessar o frontend e obter saída para OpenAI/Supabase.

## 13. Verificação de saúde

```bash
curl --fail --silent --show-error http://127.0.0.1:8080/health
curl --fail --silent --show-error http://127.0.0.1:8501/_stcore/health
docker compose --env-file .env -f compose.prod.yaml ps
```

A API deve retornar `{"status":"ok"}`. Se Langfuse estiver habilitado, o resultado também informa seu estado.

O endpoint `/health` não executa uma consulta OpenAI/Supabase. Ele prova que o processo está vivo; como a inicialização da API abre a persistência, uma falha inicial de PostgreSQL impede o serviço de ficar saudável.

## 14. Smoke tests

Execute:

```bash
./scripts/smoke_test.sh
```

Se `AUTH_SECRET` estiver definido, exporte-o apenas na sessão que executa o teste:

```bash
AUTH_SECRET='valor-do-ambiente' ./scripts/smoke_test.sh
```

Para URLs diferentes:

```bash
API_URL=http://127.0.0.1:8080 \
FRONTEND_URL=https://chatbot.exemplo.edu.br \
AUTH_SECRET='valor-do-ambiente' \
./scripts/smoke_test.sh
```

O script valida `/health`, `/info` e o healthcheck do Streamlit. Ele não envia pergunta ao LLM e não altera dados.

Validação manual do RAG, que consome API externa e exige a base Supabase real:

```bash
curl --fail --silent --show-error \
  --header 'Content-Type: application/json' \
  --header 'Authorization: Bearer SEU_AUTH_SECRET' \
  --data '{"message":"O que o RGG informa sobre matrícula?"}' \
  http://127.0.0.1:8080/chatbot_ufpi_v2/invoke
```

Remova o cabeçalho Authorization somente se `AUTH_SECRET` estiver vazio. Verifique se a resposta contém fundamentação recuperada do RGG.

## 15. Acesso ao frontend

No próprio servidor, o endereço padrão é:

```text
http://127.0.0.1:8501
```

Para servidores, o modelo recomendado é manter `FRONTEND_BIND_ADDRESS=127.0.0.1` e publicar o frontend por meio de proxy reverso com HTTPS. Configure `FRONTEND_BIND_ADDRESS=0.0.0.0` explicitamente somente quando houver intenção de exposição direta da porta `8501`; nesse caso, restrinja o acesso com firewall. A API permanece acessível apenas no loopback por padrão.

**LACUNA DE REPRODUTIBILIDADE:** domínio, DNS, certificado TLS, proxy reverso, firewall e autenticação de usuário final não estão definidos no repositório. O `AUTH_SECRET` protege a API entre frontend e backend, mas não implementa login de usuários no Streamlit. Uma implantação pública exige revisão de segurança e TLS antes da exposição.

## 16. Logs

Todos os serviços:

```bash
docker compose --env-file .env -f compose.prod.yaml logs --tail=200
```

Por serviço, com acompanhamento:

```bash
docker compose --env-file .env -f compose.prod.yaml logs --tail=200 --follow agent_service
docker compose --env-file .env -f compose.prod.yaml logs --tail=200 --follow streamlit_app
docker compose --env-file .env -f compose.prod.yaml logs --tail=200 --follow postgres
```

Não publique logs sem revisar tokens, entradas dos usuários e dados retornados por integrações.

## 17. Parada e reinício

Reiniciar sem rebuild:

```bash
docker compose --env-file .env -f compose.prod.yaml restart
```

Parar containers preservando volumes:

```bash
docker compose --env-file .env -f compose.prod.yaml stop
```

Parar e remover containers/redes, preservando volumes:

```bash
docker compose --env-file .env -f compose.prod.yaml down
```

Subir novamente:

```bash
docker compose --env-file .env -f compose.prod.yaml up -d
```

## 18. Atualização de versão

1. Registre a revisão atual e faça backup.
2. Confira alterações locais.
3. Atualize sem criar merge automático.
4. Refaça build e recrie os serviços.
5. Execute os smoke tests e a validação manual RAG.

```bash
git status --short
git rev-parse --short HEAD
git pull --ff-only
cd code
docker compose --env-file .env -f compose.prod.yaml build --pull
docker compose --env-file .env -f compose.prod.yaml up -d
./scripts/smoke_test.sh
```

Não execute a atualização se `git status --short` mostrar alterações não compreendidas. O repositório não contém migrations próprias; bibliotecas LangGraph podem ajustar estruturas ao iniciar, portanto mantenha backup do PostgreSQL.

## 19. Persistência

Com o nome de projeto definido no Compose, os volumes esperados são:

- `rag-chatbot-ufpi_postgres_data`: dados PostgreSQL;
- `rag-chatbot-ufpi_app_state`: volume reservado pelo serviço da API; só armazena o arquivo SQLite em um Compose adaptado para esse backend.

Liste-os sem modificar dados:

```bash
docker volume ls --filter label=com.docker.compose.project=rag-chatbot-ufpi
```

Supabase é persistência externa e não está coberto pelos volumes Docker. Logs dos containers não são configurados com retenção específica pelo repositório.

## 20. Backup

Crie um diretório de backup protegido fora do checkout:

```bash
sudo install -d -m 700 /srv/backups/rag-chatbot-ufpi
```

Backup lógico do PostgreSQL:

```bash
docker compose --env-file .env -f compose.prod.yaml exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > /srv/backups/rag-chatbot-ufpi/postgres.dump
```

Confirme que o arquivo não está vazio:

```bash
test -s /srv/backups/rag-chatbot-ufpi/postgres.dump
```

Em uma implantação adaptada para SQLite, pare a API antes de copiar o arquivo:

```bash
docker compose --env-file .env -f compose.prod.yaml stop agent_service
docker compose --env-file .env -f compose.prod.yaml cp \
  agent_service:/app/state/checkpoints.db \
  /srv/backups/rag-chatbot-ufpi/checkpoints.db
docker compose --env-file .env -f compose.prod.yaml start agent_service
```

**LACUNA DE REPRODUTIBILIDADE:** o repositório não define backup do Supabase, retenção, criptografia, teste de restauração ou objetivos RPO/RTO. Use o mecanismo suportado pelo plano do Supabase e inclua schema, funções, políticas e dados vetoriais.

## 21. Restauração

A restauração abaixo substitui objetos existentes no banco LangGraph. Faça-a somente com backup validado e janela de manutenção.

```bash
docker compose --env-file .env -f compose.prod.yaml stop agent_service streamlit_app
docker compose --env-file .env -f compose.prod.yaml exec -T postgres \
  sh -c 'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < /srv/backups/rag-chatbot-ufpi/postgres.dump
docker compose --env-file .env -f compose.prod.yaml start agent_service streamlit_app
./scripts/smoke_test.sh
```

Em uma implantação adaptada para SQLite, com a API parada:

```bash
docker compose --env-file .env -f compose.prod.yaml stop agent_service
docker compose --env-file .env -f compose.prod.yaml cp \
  /srv/backups/rag-chatbot-ufpi/checkpoints.db \
  agent_service:/app/state/checkpoints.db
docker compose --env-file .env -f compose.prod.yaml start agent_service
```

**LACUNA DE REPRODUTIBILIDADE:** não é possível documentar uma restauração integral do Supabase sem o schema e as RPCs originais. Recupere e teste esses artefatos antes de declarar recuperação de desastre atendida.

## 22. Troubleshooting

### Compose informa que POSTGRES_PASSWORD não está definida

Preencha `POSTGRES_PASSWORD` em `code/.env` e repita `docker compose ... config`.

### API reinicia ou fica unhealthy

```bash
docker compose --env-file .env -f compose.prod.yaml logs --tail=200 postgres agent_service
```

Verifique credenciais PostgreSQL, espaço em disco e se o máximo de conexões é maior ou igual ao mínimo.

### Erro “At least one LLM API key must be provided”

Defina `OPENAI_API_KEY` para o chatbot UFPI. Outros provedores podem iniciar o framework, mas não substituem a OpenAI no embedding RAG atual.

### Erro SUPABASE_URL/SUPABASE_KEY não definidos

As variáveis precisam existir no ambiente de `agent_service`. Confira:

```bash
docker compose --env-file .env -f compose.prod.yaml config
```

Não cole a saída completa em chamados públicos, pois ela pode conter segredos.

### RPC não encontrada ou erro de schema

Confirme no projeto Supabase original as RPCs `match_documentos_v2` e `match_documentos_metadados_only`, suas permissões e a tabela consultada. O SQL não está no repositório.

### Busca retorna “Nenhum resultado encontrado”

Verifique se a tabela correta foi ingerida, se os metadados v2 existem, se o modelo da coluna corresponde ao `text-embedding-3-small` e se o threshold da aplicação (`0.4`) é compatível. Não altere o threshold sem revisão funcional.

### Frontend recebe 401 da API

Garanta que `AUTH_SECRET` tenha o mesmo valor no backend e no frontend. O backend carrega `.env`; o Compose repassa explicitamente apenas `AUTH_SECRET` e `AGENT_URL` ao frontend.

### Frontend não abre externamente

O padrão publica `8501` apenas em `127.0.0.1`. Para acesso externo, configure o proxy reverso/HTTPS recomendado ou defina `FRONTEND_BIND_ADDRESS=0.0.0.0` explicitamente e revise as regras de firewall.

### Healthcheck do Compose antigo falha com curl

O `compose.yaml` de desenvolvimento usa `curl` dentro das imagens, mas os Dockerfiles não o instalam. Use `compose.prod.yaml` no servidor; ele usa a biblioteca padrão do Python.

### Testes Docker falham procurando o agente chatbot

O teste `tests/integration/test_docker_e2e.py` é herdado do template e pede o agente `chatbot`, que está comentado no registro atual. Essa falha não deve ser corrigida reativando agentes sem decisão funcional.

## 23. Remoção segura dos recursos do projeto

Para remover apenas containers e redes deste projeto, preservando dados:

```bash
cd code
docker compose --env-file .env -f compose.prod.yaml down --remove-orphans
```

Para remover também volumes persistentes e imagens construídas localmente, faça backup e confirme que está no checkout correto. O comando seguinte é destrutivo e os volumes não são recuperáveis pelo Docker:

```bash
docker compose --env-file .env -f compose.prod.yaml down \
  --remove-orphans --volumes --rmi local
```

Depois, se desejado, remova manualmente o checkout. Não apague volumes, bancos ou projetos Supabase por nome genérico. O comando acima é limitado aos recursos identificados pelo projeto Compose `rag-chatbot-ufpi`; ele não remove o projeto Supabase remoto nem o diretório de backups.
