#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  setup_local.sh — One-time local setup for Teuthology AI Analyzer
#  One-time local setup (SQLite DB under ./data/ by default).
# ─────────────────────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Setting up Teuthology AI Analyzer locally..."
echo ""

echo "📋 Checking prerequisites..."
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 required"; exit 1; }
command -v node   >/dev/null 2>&1 || { echo "❌ Node.js required (v18+)"; exit 1; }
command -v npm    >/dev/null 2>&1 || { echo "❌ npm required"; exit 1; }

PY_OK=$(python3 -c "import sys; print(sys.version_info >= (3,11))")
if [ "$PY_OK" != "True" ]; then
    echo "❌ Python 3.11+ required. Current: $(python3 --version)"
    exit 1
fi
echo "✅ Prerequisites OK"
echo ""

echo "🐍 Python backend (backend/app)..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "✅ Virtual environment created"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -U pip
pip install -q -e ".[dev]"
export PYTHONPATH="${SCRIPT_DIR}/backend:${PYTHONPATH:-}"
echo "✅ Python dependencies installed"

if [ ! -f backend/.env ]; then
    cp backend/.env.example backend/.env
    echo "✅ backend/.env created from backend/.env.example"
    echo "   Edit backend/.env for LLM API keys (CURSOR_API_KEY, OPENAI_API_KEY, …)"
else
    echo "ℹ️  backend/.env already exists"
fi
if [ ! -e .env ]; then
    ln -sf backend/.env .env
    echo "✅ .env → backend/.env (Bob Shell reads BOBSHELL_API_KEY from repo root)"
elif [ -L .env ] && [ "$(readlink .env)" = "backend/.env" ]; then
    :
else
    echo "ℹ️  .env exists at repo root (not overwritten); Bob CLI needs BOBSHELL_API_KEY there or in the shell"
fi

echo ""
echo "🗄️  Initialising database schema..."
PYTHONPATH="${SCRIPT_DIR}/backend" python -m app.db.init_db
echo "✅ Database schema ready"

deactivate
echo ""

echo "🌐 Frontend (Vite + React)..."
cd frontend
if [ ! -d node_modules ]; then
    npm install --silent
    echo "✅ npm dependencies installed"
else
    echo "ℹ️  node_modules present"
fi
if [ ! -f .env.local ]; then
    echo "VITE_API_PROXY_TARGET=http://127.0.0.1:8000" > .env.local
    echo "✅ frontend/.env.local created"
fi
cd ..
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete."
echo ""
echo "  Daily start:     ./start.sh   or   make start"
echo "  Docker stack:    docker compose up --build"
echo "  Production UI:   docker compose --profile prod up --build"
echo ""
echo "  Default LLM: Ollama — run: ollama serve && ollama pull llama3.2"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
