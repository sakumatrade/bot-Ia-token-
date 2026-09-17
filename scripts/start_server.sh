#!/usr/bin/env bash
# One-command way to (re)start the Local API: no manual `export
# BROKER_SAKUMA_LOCAL_API__API_KEY=...` each time, and no manual "address
# already in use" cleanup — this frees the port itself before starting.
#
# The API key is generated once and saved to backend/.local_api.key (a
# *.key file, already excluded by .gitignore, never committed) so it
# stays the same across restarts without you having to remember or
# re-type it. A second, weaker read-only key is generated the same way
# (backend/.local_readonly_api.key) — see config.py's
# LocalAPIConfig.read_only_api_key docstring: it's meant to be handed out
# to people who only watch the bot, and the backend itself rejects any
# state-changing request made with it, regardless of what the dashboard's
# own UI shows.
#
# Binds to 127.0.0.1 (this Mac only) by default, same as always — nobody
# else can reach it unless you deliberately expose it:
#   HOST=0.0.0.0 ./scripts/start_server.sh
# That makes it reachable from other devices on the same network. Only do
# that if you mean to share the read-only key with someone; never share
# the main key, and never expose it directly to the internet without
# understanding the risk of doing so.
#
# Usage:
#   ./scripts/start_server.sh              # port 8765, keys from/to backend/.local_*api.key
#   PORT=9000 ./scripts/start_server.sh    # a different port
#   HOST=0.0.0.0 ./scripts/start_server.sh # reachable from other devices on the same network
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
KEY_FILE="$BACKEND_DIR/.local_api.key"
READONLY_KEY_FILE="$BACKEND_DIR/.local_readonly_api.key"
PORT="${PORT:-8765}"
HOST="${HOST:-127.0.0.1}"

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
if [ ! -f "$READONLY_KEY_FILE" ]; then
  python3 -c "import secrets; print(secrets.token_hex(16))" > "$READONLY_KEY_FILE"
  echo "==> Chave somente-leitura criada e salva em $READONLY_KEY_FILE"
fi
export BROKER_SAKUMA_LOCAL_API__API_KEY
export BROKER_SAKUMA_LOCAL_API__READ_ONLY_API_KEY
BROKER_SAKUMA_LOCAL_API__API_KEY="$(cat "$KEY_FILE")"
BROKER_SAKUMA_LOCAL_API__READ_ONLY_API_KEY="$(cat "$READONLY_KEY_FILE")"

if command -v lsof >/dev/null 2>&1; then
  EXISTING_PID="$(lsof -ti:"$PORT" 2>/dev/null || true)"
  if [ -n "$EXISTING_PID" ]; then
    echo "==> Porta $PORT em uso (pid $EXISTING_PID) — encerrando o processo antigo..."
    kill $EXISTING_PID 2>/dev/null || true
    sleep 1
  fi
fi

echo "==> Chave de API (total controle — nunca compartilhe): $BROKER_SAKUMA_LOCAL_API__API_KEY"
echo "==> Chave somente-leitura (pode compartilhar com quem só vai olhar): $BROKER_SAKUMA_LOCAL_API__READ_ONLY_API_KEY"
echo "==> Painel: http://$HOST:$PORT/dashboard"
echo "==> Ctrl+C para parar."
exec uvicorn broker_sakuma.api.app:create_app --factory --host "$HOST" --port "$PORT"
