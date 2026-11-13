# Web interface of the TCC II prototype (Streamlit, Bisco). Talks to the backend over the
# internal Docker network; holds no credentials and no RAG pipeline.
FROM python:3.12.3-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local/ \
    PYTHONPATH=/app/code/src \
    STREAMLIT_SERVER_ENABLE_STATIC_SERVING=true \
    STREAMLIT_CLIENT_TOOLBAR_MODE=minimal \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_HEADLESS=true

WORKDIR /app/code
COPY code/pyproject.toml code/uv.lock ./
RUN pip install --no-cache-dir uv==0.10.12 \
    && uv sync --frozen --only-group client --no-install-project \
    && pip uninstall -y uv

COPY code/src/client/ ./src/client/
COPY code/src/schema/ ./src/schema/
# The shared transport schema imports contracts from rag_baseline (no pipeline is run here).
COPY code/src/rag_baseline/ ./src/rag_baseline/
COPY code/src/chat_ui/ ./src/chat_ui/
COPY code/src/static/ ./src/static/
COPY code/src/streamlit_app.py ./src/streamlit_app.py

RUN useradd --uid 1000 --create-home app
USER app

EXPOSE 8501
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=12 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)"]
CMD ["streamlit", "run", "src/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
