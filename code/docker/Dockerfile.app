# LEGADO: serviço anterior ao protótipo do TCC II (imagem da interface usada pelos composes legados). Para o protótipo atual (A''-J v2 com a
# interface Bisco), use compose.demo.yaml e scripts/start-local.cmd, na raiz do repositório.
FROM python:3.12.3-slim

WORKDIR /app/code

ENV UV_PROJECT_ENVIRONMENT="/usr/local/"
ENV UV_COMPILE_BYTECODE=1
ENV PYTHONPATH="/app/code/src"

COPY pyproject.toml .
COPY uv.lock .
RUN pip install --no-cache-dir uv

# Install only the dependencies needed for the client application
# --frozen: Use exact versions from the lock file
# --only-group client: Only install dependencies marked as part of the "client" group in pyproject.toml
RUN uv sync --frozen --only-group client --no-install-project

COPY src/client/ ./src/client/
COPY src/schema/ ./src/schema/
# The shared transport schema imports contracts from rag_baseline.
COPY src/rag_baseline/ ./src/rag_baseline/
COPY src/chat_ui/ ./src/chat_ui/
COPY src/static/ ./src/static/
COPY src/streamlit_app.py ./src/streamlit_app.py

# Fonts and the Bisco rig (src/static/bisco) are served from src/static, in every deployment of this image.
ENV STREAMLIT_SERVER_ENABLE_STATIC_SERVING=true

CMD ["streamlit", "run", "src/streamlit_app.py"]
