# Backend of the TCC II prototype: frozen A''-J v2 (LangGraph + Jev + transition policy v2).
# Build context: repository root (see compose.demo.yaml). Credentials are never copied.
FROM python:3.12.3-slim

ARG PROTOTYPE_GIT_TAG=tcc2-cond-v2
ARG PROTOTYPE_GIT_COMMIT=unknown
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local/ \
    UV_COMPILE_BYTECODE=0 \
    PYTHONPATH=/app/code/src \
    PROTOTYPE_GIT_TAG=${PROTOTYPE_GIT_TAG} \
    PROTOTYPE_GIT_COMMIT=${PROTOTYPE_GIT_COMMIT}

WORKDIR /app/code
COPY code/pyproject.toml code/uv.lock ./
RUN pip install --no-cache-dir uv==0.10.12 \
    && uv sync --frozen --no-install-project --no-dev \
    && pip uninstall -y uv

# Frozen sources; the interface files are removed so the image holds the backend only.
COPY code/src/ ./src/
RUN rm -rf src/streamlit_app.py src/client src/chat_ui src/static
# Normative registry and the four corpora of the duas-regulacoes profile (runtime and reindexing).
COPY data/normative_registry.json /app/data/normative_registry.json
COPY evaluation/corpora/graduacao_setor_v2.json evaluation/corpora/pos_graduacao_setor_v2.json evaluation/corpora/1056_2026_temporal_v1.json evaluation/corpora/658_2024_temporal_v1.json /app/evaluation/corpora/
COPY deploy/backend/frozen_sources.py deploy/backend/backend_sources.lfnorm.json deploy/backend/prototype_launcher.py deploy/backend/healthcheck.py /app/deploy/

# The build fails if any backend file differs from the frozen v2 manifest.
RUN python /app/deploy/frozen_sources.py verify /app /app/deploy/backend_sources.lfnorm.json \
    && echo "PROTOTYPE_BACKEND_MANIFEST_SHA256=$(sha256sum /app/deploy/backend_sources.lfnorm.json | cut -d' ' -f1)" > /app/deploy/manifest.env

RUN useradd --uid 1000 --create-home app && mkdir -p /app/state /app/index && chown app:app /app/state /app/index
USER app

EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=6s --start-period=40s --retries=12 CMD ["python", "/app/deploy/healthcheck.py"]
CMD ["sh", "-c", ". /app/deploy/manifest.env && export PROTOTYPE_BACKEND_MANIFEST_SHA256 && exec python /app/deploy/prototype_launcher.py"]
