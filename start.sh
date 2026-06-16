#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  start.sh — Daily launch script for Teuthology AI Analyzer
#  First-time? Run ./setup_local.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Teuthology AI Analyzer — Daily Launch"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "❌ .venv not found. Run ./setup_local.sh first."
    exit 1
fi
if [ ! -d "$SCRIPT_DIR/frontend/node_modules" ]; then
    echo "❌ frontend/node_modules not found. Run ./setup_local.sh first."
    exit 1
fi

lsof -ti tcp:8000 2>/dev/null | xargs kill 2>/dev/null || true
lsof -ti tcp:3000 2>/dev/null | xargs kill 2>/dev/null || true

# shellcheck disable=SC1091
(cd "$SCRIPT_DIR" && source .venv/bin/activate && \
    PYTHONPATH="$SCRIPT_DIR/backend" uvicorn app.main:app --reload --host 0.0.0.0 --port 8000) \
    >"$SCRIPT_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "🐍 API starting (PID $BACKEND_PID)  →  backend.log"

(cd "$SCRIPT_DIR/frontend" && npm run dev) \
    >"$SCRIPT_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "🌐 Frontend starting (PID $FRONTEND_PID)  →  frontend.log"
echo ""

echo "⏳ Waiting for API on :8000 ..."
for i in $(seq 1 40); do
    if curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
        echo "✅ API ready"
        break
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "❌ API crashed. tail backend.log:"
        tail -30 "$SCRIPT_DIR/backend.log"
        exit 1
    fi
    sleep 1
    [[ $i -eq 40 ]] && echo "⚠️  API health-check timed out"
done

echo "⏳ Waiting for frontend on :3000 ..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:3000 >/dev/null 2>&1; then
        echo "✅ Frontend ready"
        break
    fi
    if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
        echo "❌ Frontend crashed. tail frontend.log:"
        tail -30 "$SCRIPT_DIR/frontend.log"
        exit 1
    fi
    sleep 1
    [[ $i -eq 60 ]] && echo "⚠️  Frontend timed out (may still be compiling)"
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Dashboard  →  http://localhost:3000"
echo "  API        →  http://localhost:8000"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Press Ctrl-C to stop both."
echo ""

trap 'echo ""; echo "Stopping…"; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0' INT TERM
wait $BACKEND_PID $FRONTEND_PID
