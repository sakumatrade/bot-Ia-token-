#!/usr/bin/env bash
# Background loop: checks for new commits every N minutes and runs
# update.sh automatically when it finds any. Meant to be started from
# broker_sakuma.sh's "Ligar/desligar atualizacao automatica" option, or
# directly: ./scripts/auto_update_loop.sh 15
#
# This lives here, as a plain shell script the user runs themselves, on
# purpose — not inside the Python backend. Nothing in backend/ is
# allowed to shell out and run git (see update.sh's own header: an API
# able to run arbitrary commands is a real security hole). A local loop
# the user starts and can kill at any time doesn't carry that risk, so
# it's a safe place to put "check periodically and update automatically."
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INTERVAL_MINUTES="${1:-15}"
LOG_FILE="$ROOT_DIR/backend/auto_update.log"

cd "$ROOT_DIR"
echo "$(date '+%Y-%m-%d %H:%M:%S'): loop de atualizacao automatica iniciado (a cada ${INTERVAL_MINUTES} min)" >> "$LOG_FILE"

while true; do
  sleep "$((INTERVAL_MINUTES * 60))"

  BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" || continue
  BEFORE="$(git rev-parse HEAD 2>/dev/null)" || continue
  git fetch origin "$BRANCH" >>"$LOG_FILE" 2>&1 || continue
  AFTER="$(git rev-parse "origin/$BRANCH" 2>/dev/null)" || continue

  if [ "$BEFORE" != "$AFTER" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S'): novidades encontradas ($BEFORE -> $AFTER), atualizando..." >>"$LOG_FILE"
    # Runs in the background: update.sh ends by exec-ing into the server
    # process, which must not block this loop from reaching its next check.
    nohup "$ROOT_DIR/scripts/update.sh" >>"$LOG_FILE" 2>&1 &
    disown
  else
    echo "$(date '+%Y-%m-%d %H:%M:%S'): sem novidades" >>"$LOG_FILE"
  fi
done
