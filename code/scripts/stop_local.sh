#!/bin/bash
# LEGADO: serviço anterior ao protótipo do TCC II (launcher operacional; para o container de API antigo). Para o protótipo atual (A''-J v2 com a
# interface Bisco), use compose.demo.yaml e scripts/start-local.cmd, na raiz do repositório.
# Stops the UI and the API container. Images, index and conversation state are kept.
set -eu
cd "$(dirname "$0")/.."
docker compose -p ufpi-tcc-ui -f compose.operational.yaml stop ui
docker stop ufpi-tcc-local-agent_service-1 >/dev/null
echo "Parado."
