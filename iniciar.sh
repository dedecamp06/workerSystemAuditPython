#!/usr/bin/env bash
# Inicializa o sistema de Auditoria Automatizada de Atendimentos no Linux/Ubuntu.
# Uso: ./iniciar.sh
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo ">> Criando ambiente virtual em .venv ..."
    python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

echo ">> Instalando/conferindo dependencias ..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if ! flask --app app listar-usuarios 2>/dev/null | grep -q "|"; then
    echo
    echo ">> Nenhum usuario cadastrado. Crie o administrador com:"
    echo "   source .venv/bin/activate && flask --app app criar-admin"
    echo
fi

echo ">> Servidor em http://127.0.0.1:5000  (Ctrl+C para encerrar)"
exec python app.py
