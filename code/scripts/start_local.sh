#!/bin/bash
# LEGADO: serviço anterior ao protótipo do TCC II (launcher operacional; exige o container de API antigo). Para o protótipo atual (A''-J v2 com a
# interface Bisco), use compose.demo.yaml e scripts/start-local.cmd, na raiz do repositório.
# Starts the frozen API container and the operational UI, on loopback. Prints no environment values.
set -eu
cd "$(dirname "$0")/.."
API=ufpi-tcc-local-agent_service-1
EXPECTED=sha256:b3bfa6344a5a12637ed67ea6fcf30cb660deba512a2498c62a7d69068e452dbb
IMAGE=ufpi-tcc-local-streamlit_app:ui-rev-3
COMPOSE="docker compose -p ufpi-tcc-ui -f compose.operational.yaml"

if ! docker container inspect "$API" >/dev/null 2>&1; then
  echo "Container da API ausente: $API. Veja backup/RESTORE do freeze." >&2
  exit 1
fi
ACTUAL=$(docker inspect "$API" --format '{{.Image}}')
if [ "$ACTUAL" != "$EXPECTED" ]; then
  echo "A API nao corresponde ao baseline: $ACTUAL. Nada foi iniciado." >&2
  exit 1
fi
# Each address comes in brackets, so an empty one (all interfaces) is still seen.
BINDINGS=$(docker inspect "$API" --format '{{range $port, $list := .HostConfig.PortBindings}}{{range $list}}[{{.HostIp}}]{{end}}{{end}}')
if [ -z "$BINDINGS" ]; then
  echo "A API nao tem porta em loopback. Nada foi iniciado." >&2
  exit 1
fi
if [ -n "$(printf '%s' "$BINDINGS" | sed 's/\[127\.0\.0\.1\]//g')" ]; then
  echo "A API nao esta restrita ao loopback: $BINDINGS. Nada foi iniciado." >&2
  exit 1
fi
docker start "$API" >/dev/null
# Always build: an older image under the same tag must not hide changes. Docker reuses cached
# layers, so an unchanged interface rebuilds in seconds.
$COMPOSE build ui >/dev/null
$COMPOSE up -d --no-build ui >/dev/null
for _ in $(seq 1 40); do
  API_STATE=$(docker inspect "$API" --format '{{.State.Health.Status}}')
  UI_STATE=$(docker inspect ufpi-tcc-ui-rev-3 --format '{{.State.Health.Status}}')
  if [ "$API_STATE" = healthy ] && [ "$UI_STATE" = healthy ]; then
    echo "Pronto. Interface: http://127.0.0.1:8501  API: http://127.0.0.1:8080/health"
    exit 0
  fi
  sleep 3
done
echo "Sem saude apos 2 minutos: API=$API_STATE UI=$UI_STATE" >&2
exit 1
