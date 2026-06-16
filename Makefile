##############################################################################
# Teuthology AI Analyzer — Makefile
##############################################################################

REPO     := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
BACKEND  := $(REPO)backend
FRONTEND := $(REPO)frontend
VENV     := $(REPO).venv
PY       := $(VENV)/bin/python
PIP      := $(VENV)/bin/pip
UV       := $(VENV)/bin/uvicorn

.PHONY: help setup start backend frontend dev test lint clean docker-up docker-down

help:
	@echo ""
	@echo "  Teuthology AI Analyzer"
	@echo ""
	@echo "  setup         — venv, pip install -e ., npm install, .env"
	@echo "  start / dev   — API :8000 + frontend :3000"
	@echo "  backend       — API only"
	@echo "  frontend      — Vite dev only"
	@echo "  test          — pytest"
	@echo "  docker-up     — compose: backend + frontend (+ optional postgres)"
	@echo ""

setup:
	@test -d $(VENV) || python3 -m venv $(VENV)
	$(PIP) install -q -U pip
	$(PIP) install -q -e ".[dev]"
	cd $(FRONTEND) && npm install --silent
	@test -f $(BACKEND)/.env || cp $(BACKEND)/.env.example $(BACKEND)/.env
	@echo "✓ Setup complete. Run: make start"

backend:
	cd $(REPO) && PYTHONPATH=backend $(UV) app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd $(FRONTEND) && npm run dev

start:
	@echo "▶ API :8000 + frontend :3000"
	@(cd $(REPO) && PYTHONPATH=backend $(UV) app.main:app --reload --host 0.0.0.0 --port 8000 &) ; \
	 (cd $(FRONTEND) && npm run dev &) ; \
	 wait

dev: start

test:
	cd $(REPO) && PYTHONPATH=backend $(PY) -m pytest backend/tests/ -v

lint:
	cd $(FRONTEND) && npx tsc -b --noEmit

clean:
	rm -rf $(FRONTEND)/dist
	find $(REPO) -path ./.venv -prune -o -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Cleaned"

docker-up:
	docker compose up --build

docker-down:
	docker compose down
