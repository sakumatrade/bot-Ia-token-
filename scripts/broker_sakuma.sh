#!/usr/bin/env bash
# Broker Sakuma - a single interactive menu that wraps every other script
# in this folder (update.sh, start_server.sh, activate_bot.sh) plus a few
# curl calls, so there is exactly one command to remember instead of
# several: this one. Runs the server in the background so the same
# terminal window stays usable for everything else — no more "open a new
# window/tab" step.
#
# Usage: ./scripts/broker_sakuma.sh
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEY_FILE="$ROOT_DIR/backend/.local_api.key"
PORT="${PORT:-8765}"
API_URL="http://127.0.0.1:$PORT"
LOG_FILE="$ROOT_DIR/backend/server.log"

api_key() {
  [ -f "$KEY_FILE" ] && cat "$KEY_FILE" || echo ""
}

server_up() {
  [ "$(curl -s -o /dev/null -w '%{http_code}' "$API_URL/dashboard" 2>/dev/null)" = "200" ]
}

wait_for_server() {
  for _ in 1 2 3 4 5 6 7 8; do
    server_up && return 0
    sleep 1
  done
  return 1
}

start_server_bg() {
  if server_up; then
    echo "O servidor ja esta rodando em $API_URL"
    return
  fi
  echo "Iniciando o servidor em segundo plano..."
  nohup "$ROOT_DIR/scripts/start_server.sh" >"$LOG_FILE" 2>&1 &
  disown
  if wait_for_server; then
    echo "Pronto! Chave da API: $(api_key)"
    echo "Painel: $API_URL/dashboard"
  else
    echo "Ainda nao respondeu. Ultimas linhas do log:"
    tail -n 15 "$LOG_FILE" 2>/dev/null
  fi
}

update_system() {
  echo "Buscando atualizacoes e reiniciando o servidor em segundo plano..."
  nohup "$ROOT_DIR/scripts/update.sh" >"$LOG_FILE" 2>&1 &
  disown
  if wait_for_server; then
    echo "Atualizado! Chave da API: $(api_key)"
    echo "Painel: $API_URL/dashboard"
  else
    echo "Ainda atualizando/reiniciando. Escolha a opcao 4 (status) em alguns segundos, ou veja o log:"
    tail -n 15 "$LOG_FILE" 2>/dev/null
  fi
}

require_server() {
  if ! server_up; then
    echo "O servidor nao esta rodando. Escolha a opcao 1 primeiro."
    return 1
  fi
  if [ -z "$(api_key)" ]; then
    echo "Nao encontrei a chave da API em $KEY_FILE. Inicie o servidor pela opcao 1 primeiro."
    return 1
  fi
  return 0
}

create_and_activate_bot() {
  require_server || return
  read -rp "Nome do bot (Enter para automatico): " NAME
  if [ -n "$NAME" ]; then
    BROKER_SAKUMA_API_URL="$API_URL" "$ROOT_DIR/scripts/activate_bot.sh" "$(api_key)" "$NAME"
  else
    BROKER_SAKUMA_API_URL="$API_URL" "$ROOT_DIR/scripts/activate_bot.sh" "$(api_key)"
  fi
}

show_status() {
  if server_up; then
    echo "Servidor: RODANDO em $API_URL"
  else
    echo "Servidor: PARADO"
    return
  fi
  if [ -z "$(api_key)" ]; then
    return
  fi
  echo ""
  curl -s -H "X-API-Key: $(api_key)" "$API_URL/api/bots" | python3 -c "
import json, sys
try:
    bots = json.load(sys.stdin)
except Exception:
    print('(nao consegui ler os bots)')
    sys.exit(0)
if not bots:
    print('Nenhum bot criado ainda.')
for b in bots:
    print(f\"  {b['name']:<20} estado={b['state']:<8} capital=\${b['capital_operational_usd']:.2f} operacoes={b['trades_count']}\")
"
  echo ""
  curl -s -H "X-API-Key: $(api_key)" "$API_URL/api/system/auto-trading" | python3 -c "
import json, sys
try:
    s = json.load(sys.stdin)
    estado = 'LIGADA' if s['enabled'] else 'DESLIGADA'
    print(f\"Operacao automatica: {estado} (intervalo: {s['interval_seconds']}s)\")
except Exception:
    pass
"
}

toggle_auto_trading() {
  require_server || return
  read -rp "Ligar (l) ou desligar (d) a operacao automatica? " CHOICE
  if [ "$CHOICE" = "l" ]; then
    BODY='{"enabled": true}'
  else
    BODY='{"enabled": false}'
  fi
  curl -s -X POST -H "X-API-Key: $(api_key)" -H "Content-Type: application/json" "$API_URL/api/system/auto-trading" -d "$BODY" \
    | python3 -c "import json,sys; s=json.load(sys.stdin); print('Operacao automatica agora:', 'LIGADA' if s['enabled'] else 'DESLIGADA')"
}

open_dashboard() {
  echo "Painel: $API_URL/dashboard"
  command -v open >/dev/null 2>&1 && open "$API_URL/dashboard" 2>/dev/null
}

while true; do
  echo ""
  echo "===== Broker Sakuma ====="
  echo "1) Iniciar/verificar o servidor"
  echo "2) Atualizar o sistema (buscar as ultimas novidades)"
  echo "3) Criar e ativar um novo bot (\$5 simulados)"
  echo "4) Ver status e bots"
  echo "5) Ligar/desligar a operacao automatica"
  echo "6) Abrir o painel no navegador"
  echo "0) Sair"
  read -rp "Escolha uma opcao: " OPTION
  case "$OPTION" in
    1) start_server_bg ;;
    2) update_system ;;
    3) create_and_activate_bot ;;
    4) show_status ;;
    5) toggle_auto_trading ;;
    6) open_dashboard ;;
    0) echo "Ate mais!"; exit 0 ;;
    *) echo "Opcao invalida." ;;
  esac
done
