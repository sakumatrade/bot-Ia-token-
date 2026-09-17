#!/usr/bin/env bash
# One-command terminal option to create/activate a bot (spec sections 7,
# 8, 10): if no Mother Bot exists yet, creates one; always spawns a new
# Son under it and activates it, which funds it with the fixed $5
# simulated stake (the $5 rule). Requires the Local API to already be
# running (see README.md "Running the Local API").
#
# Every dollar here is a plain number in this backend's own database —
# there is no wallet, private key, or blockchain call anywhere in this
# flow (see docs/ARCHITECTURE.md#security).
#
# Usage:
#   ./scripts/activate_bot.sh SUA_CHAVE_DE_API [nome-do-son] [capital-inicial-da-mother]
#
# Example:
#   ./scripts/activate_bot.sh minha-chave-123 "Son 001" 1000
set -euo pipefail

API_URL="${BROKER_SAKUMA_API_URL:-http://127.0.0.1:8765}"
API_KEY="${1:-}"
SON_NAME="${2:-}"
MOTHER_INITIAL_CAPITAL="${3:-1000}"

if [ -z "$API_KEY" ]; then
  echo "Uso: ./scripts/activate_bot.sh SUA_CHAVE_DE_API [nome-do-son] [capital-inicial-da-mother]" >&2
  echo "Exemplo: ./scripts/activate_bot.sh minha-chave-123 \"Son 001\" 1000" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 nao encontrado — instale o Python (veja README.md) antes de rodar este script." >&2
  exit 1
fi

json_get() {
  # $1 = json text, $2 = key
  python3 -c "import json,sys; d=json.loads(sys.argv[1]); v=d.get(sys.argv[2]); print(v if v is not None else '')" "$1" "$2"
}

request() {
  # $1 = method, $2 = path, $3 = json body (optional)
  local method="$1" path="$2" body="${3:-}"
  if [ -n "$body" ]; then
    curl -s -w '\n%{http_code}' -X "$method" "$API_URL$path" \
      -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" -d "$body"
  else
    curl -s -w '\n%{http_code}' -X "$method" "$API_URL$path" -H "X-API-Key: $API_KEY"
  fi
}

fail_if_error() {
  # $1 = http_code, $2 = response body, $3 = step description
  local code="$1" body="$2" step="$3"
  if ! [[ "$code" =~ ^[0-9]+$ ]]; then
    echo "Nao consegui conectar em $API_URL — o servidor esta rodando?" >&2
    echo "Passo que falhou: $step" >&2
    exit 1
  fi
  if [ "$code" -ge 400 ]; then
    echo "Erro em '$step' (HTTP $code):" >&2
    echo "$body" >&2
    exit 1
  fi
}

echo "==> Verificando se a Dominus Core ja existe..."
response="$(request GET /api/bots)"
http_code="$(echo "$response" | tail -n1)"
body="$(echo "$response" | sed '$d')"
fail_if_error "$http_code" "$body" "listar bots (confira se o servidor esta rodando e a API_KEY esta correta)"

MOTHER_ID="$(python3 -c "
import json, sys
bots = json.loads(sys.argv[1])
mothers = [b for b in bots if b.get('generation') == 0]
print(mothers[0]['id'] if mothers else '')
" "$body")"

if [ -z "$MOTHER_ID" ]; then
  echo "==> Nenhuma Dominus Core encontrada. Criando uma com \$$MOTHER_INITIAL_CAPITAL simulados..."
  response="$(request POST /api/bots/mother "{\"name\": \"Dominus Core\", \"initial_capital_usd\": $MOTHER_INITIAL_CAPITAL}")"
  http_code="$(echo "$response" | tail -n1)"
  body="$(echo "$response" | sed '$d')"
  fail_if_error "$http_code" "$body" "criar Dominus Core"
  MOTHER_ID="$(json_get "$body" id)"
  echo "    Dominus Core criada: id=$MOTHER_ID"
else
  echo "    Dominus Core ja existe: id=$MOTHER_ID"
fi

echo "==> Criando um novo Son..."
if [ -n "$SON_NAME" ]; then
  son_body="{\"parent_id\": \"$MOTHER_ID\", \"name\": \"$SON_NAME\"}"
else
  son_body="{\"parent_id\": \"$MOTHER_ID\"}"
fi
response="$(request POST /api/bots/sons "$son_body")"
http_code="$(echo "$response" | tail -n1)"
body="$(echo "$response" | sed '$d')"
fail_if_error "$http_code" "$body" "criar Son"
SON_ID="$(json_get "$body" id)"
SON_NAME_ACTUAL="$(json_get "$body" name)"
echo "    Son criado: id=$SON_ID nome=$SON_NAME_ACTUAL"

echo "==> Ativando o Son (financiando com os \$5 simulados da regra do \$5)..."
response="$(request POST "/api/bots/$SON_ID/activate")"
http_code="$(echo "$response" | tail -n1)"
body="$(echo "$response" | sed '$d')"
fail_if_error "$http_code" "$body" "ativar Son"

echo ""
echo "==> Pronto! Bot ativado (dinheiro simulado, nao real):"
python3 -c "
import json, sys
d = json.loads(sys.argv[1])
bot = d['bot']
print(f\"    nome: {bot['name']}\")
print(f\"    id: {bot['id']}\")
print(f\"    estado: {bot['state']}\")
print(f\"    capital operacional simulado: \${bot['capital_operational_usd']:.2f}\")
" "$body"
echo ""
echo "Veja em $API_URL/dashboard ou rode:"
echo "  curl -s -H \"X-API-Key: $API_KEY\" $API_URL/api/bots"
