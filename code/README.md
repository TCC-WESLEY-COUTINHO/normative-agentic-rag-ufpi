# Chatbot RAG da UFPI

Aplicação de consulta ao Regulamento Geral da Graduação da UFPI. O projeto combina agentes LangGraph, uma API FastAPI, uma interface Streamlit e recuperação vetorial hospedada no Supabase.

Este diretório contém o código executável. O agente padrão é `chatbot_ufpi_v2`, que usa embeddings OpenAI e duas RPCs do Supabase para busca semântica e por metadados.

## Início rápido para desenvolvimento

Pré-requisitos: Python 3.11 ou superior, `uv` e acesso às APIs externas configuradas.

```bash
cp .env.example .env
# Preencha, no mínimo, OPENAI_API_KEY, SUPABASE_URL e SUPABASE_KEY.
# Para execução nativa sem PostgreSQL, altere DATABASE_TYPE=sqlite.
uv sync --frozen
uv run python src/run_service.py
```

Em outro terminal:

```bash
cd code
uv run streamlit run src/streamlit_app.py
```

O backend estará em `http://localhost:8080` e o frontend normalmente em `http://localhost:8501`.

## Docker

- `compose.yaml`: fluxo de desenvolvimento existente, com Compose Watch.
- `compose.prod.yaml`: implantação em servidor, sem publicar PostgreSQL e com persistência e healthchecks.

O procedimento completo, incluindo Supabase, build, backup, restauração e troubleshooting, está em [docs/DEPLOY_LINUX.md](../docs/DEPLOY_LINUX.md).

## Observação sobre a base RAG

Os chunks e scripts de ingestão estão em `scripts/`, mas as definições SQL das tabelas e RPCs do Supabase não estão versionadas. Uma instância nova não pode ser reconstruída integralmente sem recuperar esses objetos do projeto Supabase original; consulte o guia de implantação antes de operar a ingestão.

## Testes

```bash
uv run ruff check .
uv run mypy src/
uv run pytest
```

Alguns testes Docker herdados ainda referenciam um agente desativado. Essa limitação está registrada no guia de implantação.
