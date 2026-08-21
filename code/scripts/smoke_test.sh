#!/bin/sh
set -eu

API_URL="${API_URL:-http://127.0.0.1:8080}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:8501}"
SMOKE_TIMEOUT="${SMOKE_TIMEOUT:-10}"

if ! command -v curl >/dev/null 2>&1; then
  printf '%s\n' "ERRO: curl nao esta disponivel." >&2
  exit 1
fi

request() {
  target_url=$1
  if [ -n "${AUTH_SECRET:-}" ]; then
    curl --fail --silent --show-error --max-time "$SMOKE_TIMEOUT" \
      --header "Authorization: Bearer ${AUTH_SECRET}" "$target_url"
  else
    curl --fail --silent --show-error --max-time "$SMOKE_TIMEOUT" "$target_url"
  fi
}

printf '%s\n' "Verificando API em ${API_URL}/health"
health_response=$(request "${API_URL}/health")
case "$health_response" in
  *'"status":"ok"'*|*'"status": "ok"'*) ;;
  *)
    printf '%s\n' "ERRO: resposta inesperada do healthcheck: ${health_response}" >&2
    exit 1
    ;;
esac

printf '%s\n' "Verificando metadados da API em ${API_URL}/info"
request "${API_URL}/info" >/dev/null

printf '%s\n' "Verificando frontend em ${FRONTEND_URL}/_stcore/health"
request "${FRONTEND_URL}/_stcore/health" >/dev/null

printf '%s\n' "Smoke test concluido com sucesso."
