# Teuthology AI — Deployment Guide

Root-level `docker-compose.yml`, `Makefile`, `setup_local.sh`, `start.sh`,
and per-component Dockerfiles for local and containerized runs.

## Repository layout

| Path | Role |
|------|------|
| `backend/app/` | FastAPI app (routers, providers, services, DB) |
| `backend/alembic/` | Database migrations (PostgreSQL) |
| `backend/tests/` | pytest suite |
| `backend/.env` | Configuration (copy from `backend/.env.example`) |
| `backend/requirements.lock` | Pinned dependencies (used in Docker) |
| `frontend/` | React + Vite UI |
| `backend/Dockerfile` | API image (uses `requirements.lock`) |
| `frontend/Dockerfile` | Vite dev server |
| `ARCHITECTURE.md` | Request flow and modules |

## Run modes

### 1. Native local (primary)

```bash
./setup_local.sh    # once
./start.sh          # daily — :3000 UI, :8000 API
# or: make start
```

API runs as `PYTHONPATH=backend uvicorn app.main:app`.
Uses SQLite by default for local dev (`DATABASE_URL=sqlite:///./data/teuthology.db`).

### 2. Docker Compose (full stack)

```bash
cp backend/.env.example backend/.env   # add LLM keys
docker compose up --build
```

| Service | Port | Role |
|---------|------|------|
| `postgres` | 5432 | PostgreSQL 15 with healthcheck |
| `backend` | 8000 | FastAPI with hot reload (depends on postgres) |
| `frontend` | 3000 | Vite dev, proxies `/api` → `backend:8000` |

Optional Ollama profile:

```bash
docker compose --profile ollama up --build
```

### 3. Bare production (no Docker)

```bash
cd frontend && npm run build && cd ..
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Database

| Mode | DB | Migrations |
|------|----|------------|
| **Production** | PostgreSQL (default `DATABASE_URL`) | Alembic (`alembic upgrade head`) |
| **Dev/test** | SQLite (override `DATABASE_URL`) | `create_all()` fallback |

Connection pooling is configured via `DB_POOL_SIZE` (default 5), `DB_MAX_OVERFLOW` (10), `DB_POOL_TIMEOUT` (30s) — applies to PostgreSQL only.

## Environment variables

All variables are read from **`backend/.env`**. See `backend/.env.example`.

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL (default) or SQLite for dev |
| `DB_POOL_SIZE` | Connection pool size (PostgreSQL, default 5) |
| `API_KEY` | API authentication key (empty = auth disabled) |
| `CORS_ORIGINS` | Comma-separated browser origins |
| `LLM_DEFAULT_PROVIDER` | Default provider id (`ollama`) |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | Primary Ollama config |
| `{PROVIDER}_API_KEY`, `{PROVIDER}_MODEL` | Per-provider overrides |

Generate an API key: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

Do not commit `backend/.env` to git; use orchestrator secrets in production.

## Health endpoints

| Path | Use |
|------|-----|
| `GET /api/health` | App + Ollama reachability |
| `GET /api/ready` | Readiness probe |
| `GET /api/live` | Liveness probe |

## Makefile targets

| Target | Action |
|--------|--------|
| `make setup` | venv, `pip install -e .`, `npm install`, `backend/.env` |
| `make start` | API + frontend dev servers |
| `make backend` | API only |
| `make test` | `pytest` with `PYTHONPATH=backend` |
| `make docker-up` | `docker compose up --build` |
