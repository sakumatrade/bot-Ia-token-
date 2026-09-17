#!/usr/bin/env bash
# One-command way to (re)start the Local API: no manual `export
# BROKER_SAKUMA_LOCAL_API__API_KEY=...` each time, and no manual "address
# already in use" cleanup — this frees the port itself before starting.
#
# The API key is generated once and saved to backend/.local_api.key (a
# *.key file, already excluded by .gitignore, never committed) so it
# stays the same across restarts without you having to remember or
# re-type it.
#
# Usage:
#   ./scripts/start_server.sh              # port 8765, key from/to .local_api.key
#   PORT=9000 ./scripts/start_server.sh    # a different port
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
KEY_FILE="$BACKEND_DIR/.local_api.key"
PORT="${PORT:-8765}"

if [ ! -d "$BACKEND_DIR/.venv" ]; then
  echo "Ambiente virtual nao encontrado em $BACKEND_DIR/.venv — rode primeiro:" >&2
  echo "  cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -e \".[dev]\"" >&2
  exit 1
fi

cd "$BACKEND_DIR"
# shellcheck disable=SC1091
source .venv/bin/activate

if [ ! -f "$KEY_FILE" ]; then
  echo "minha-chave-123" > "$KEY_FILE"
  echo "==> Chave de API criada e salva em $KEY_FILE"
fi
export BROKER_SAKUMA_LOCAL_API__API_KEY
BROKER_SAKUMA_LOCAL_API__API_KEY="$(cat "$KEY_FILE")"

if command -v lsof >/dev/null 2>&1; then
  EXISTING_PID="$(lsof -ti:"$PORT" 2>/dev/null || true)"
  if [ -n "$EXISTING_PID" ]; then
    echo "==> Porta $PORT em uso (pid $EXISTING_PID) — encerrando o processo antigo..."
    kill $EXISTING_PID 2>/dev/null || true
    sleep 1
  fi
fi

echo "==> Chave de API: $BROKER_SAKUMA_LOCAL_API__API_KEY"
echo "==> Painel: http://127.0.0.1:$PORT/dashboard"
echo "==> Ctrl+C para parar."
exec uvicorn broker_sakuma.api.app:create_app --factory --port "$PORT"
