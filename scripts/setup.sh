#!/usr/bin/env bash
# One-command first-time setup: creates the backend's virtual environment
# and installs everything, so a brand-new checkout only needs this once
# before `./scripts/broker_sakuma.sh` works. Safe to re-run — skips venv
# creation if it already exists.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 nao encontrado. Instale o Python (https://python.org/downloads) e rode este script de novo." >&2
  exit 1
fi

PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJOR="$(python3 -c 'import sys; print(sys.version_info.major)')"
PY_MINOR="$(python3 -c 'import sys; print(sys.version_info.minor)')"
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
  echo "Python $PY_VERSION encontrado, mas e preciso 3.11 ou mais novo." >&2
  echo "Instale uma versao mais nova em https://python.org/downloads/macos/ e rode este script de novo." >&2
  exit 1
fi

cd "$BACKEND_DIR"

if [ ! -d .venv ]; then
  echo "==> Criando o ambiente virtual (.venv) com Python $PY_VERSION..."
  python3 -m venv .venv
else
  echo "==> Ambiente virtual ja existe, reaproveitando."
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Atualizando o pip..."
pip install --upgrade pip --quiet

echo "==> Instalando as dependencias do backend..."
pip install -e ".[dev]" --quiet

echo "==> Rodando os testes para confirmar que esta tudo certo..."
pytest -q

echo ""
echo "==> Tudo pronto! Agora rode:"
echo "    ./scripts/broker_sakuma.sh"
