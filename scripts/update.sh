#!/usr/bin/env bash
# One command to fetch whatever has been pushed to this branch, reinstall
# the backend, and restart the server — the safe equivalent of an
# in-app "update" button.
#
# There is deliberately no such button *inside* the running app/API:
# nothing in this codebase is allowed to shell out to run a command like
# `git pull` (test_no_module_anywhere_shells_out_or_evals forbids
# importing subprocess/os anywhere, on purpose — an API that could run
# arbitrary shell commands would be a real security hole). This script
# is the safe, one-command alternative you run yourself from Terminal.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "==> Buscando atualizações (branch: $CURRENT_BRANCH)..."
git pull origin "$CURRENT_BRANCH"

if [ ! -d "$ROOT_DIR/backend/.venv" ]; then
  echo "Ambiente virtual nao encontrado em backend/.venv — rode primeiro:" >&2
  echo "  cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -e \".[dev]\"" >&2
  exit 1
fi

echo "==> Reinstalando dependências do backend..."
cd "$ROOT_DIR/backend"
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -e ".[dev]" --quiet

echo "==> Reiniciando o servidor..."
cd "$ROOT_DIR"
exec ./scripts/start_server.sh
