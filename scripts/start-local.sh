#!/bin/sh
# Linux/WSL/EC2 equivalent of start-local.cmd.
set -eu
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "[erro] .env ausente (copie .env.example)" >&2; exit 1; }
grep -q '^OPENROUTER_API_KEY=..*' .env || { echo "[erro] OPENROUTER_API_KEY vazio em .env" >&2; exit 1; }
grep -q '^POSTGRES_PASSWORD=..*' .env || { echo "[erro] POSTGRES_PASSWORD vazio em .env" >&2; exit 1; }
[ -f "${INDEX_DIR:-./.local/index}/chroma.sqlite3" ] || { echo "[erro] indice Chroma ausente" >&2; exit 1; }
docker compose -f compose.demo.yaml up --build -d --wait --wait-timeout 300
echo "Interface: http://127.0.0.1:${INTERFACE_PORT:-8501}"
