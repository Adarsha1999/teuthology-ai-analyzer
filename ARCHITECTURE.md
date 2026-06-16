# Architecture

## Overview

```
teuthology-ai/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI route handlers
│   │   ├── core/             # AppSettings + LLM provider catalog
│   │   ├── db/               # SQLAlchemy models, session, init
│   │   ├── providers/        # LLM provider package (base, factory, per-provider)
│   │   ├── services/         # Business logic (analysis, connection, session)
│   │   └── models/           # Pydantic request/response schemas
│   ├── alembic/              # Database migrations (PostgreSQL)
│   ├── tests/
│   └── .env                  # Configuration (copy from .env.example)
├── frontend/                 # React + Vite UI
├── docker-compose.yml
├── Makefile
├── setup_local.sh
└── start.sh
```

## Request flow

1. **Frontend** calls `/api/*` (Vite proxy in dev, same-origin in prod).
2. **API key middleware** checks `X-API-Key` header (skipped if `API_KEY` is empty).
3. **CORS** middleware allows configured origins.
4. **Routers** validate input, resolve browser session cookie (`teuth_session`) + DB row.
5. **Services** run analysis, LLM calls, history persistence.

## LLM providers (Strategy + Factory pattern)

```
POST /api/analyze → 202 + task_id
  → ThreadPoolExecutor → AnalysisService
    → llm_client.chat_llm(conn, messages)
      → ProviderFactory.get_provider(spec.kind)
        → LLMProvider.chat(conn, messages)
```

### Provider package (`app/providers/`)

| File | Role |
|------|------|
| `base.py` | `LLMProvider` ABC — `chat()`, `health_check()` |
| `factory.py` | `ProviderFactory` — lazy registration, singleton cache |
| `ollama_provider.py` | Ollama `/api/chat` + model discovery |
| `openai_provider.py` | OpenAI `/chat/completions` |
| `gemini_provider.py` | Gemini `generateContent` REST API |
| `cursor_provider.py` | Cursor SDK `Agent.prompt()` |
| `bob_cli_provider.py` | IBM Bob Shell subprocess |

Ollama is the primary provider. Others are optional cloud/CLI alternatives.

## Database

- **Production:** PostgreSQL with connection pooling (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`)
- **Dev/test:** SQLite (set `DATABASE_URL=sqlite:///./data/teuthology.db`)
- **Migrations:** Alembic for PostgreSQL; `create_all()` fallback for SQLite

### Tables

| Table | Purpose |
|-------|---------|
| `app_sessions` | Browser session → LLM connection binding |
| `run_history` | Recent analyzed runs per session |
| `analysis_cache` | Cached analysis results per session + run |

## Background analysis

`POST /api/analyze` and `/api/analyze-local` return `202 + task_id`.
Analysis runs in a 4-thread pool. Frontend polls `GET /api/analyze/status/{task_id}`.

## Configuration

All settings come from **`backend/.env`**:

| Variable group | Examples |
|----------------|----------|
| App / DB | `DATABASE_URL`, `DB_POOL_SIZE`, `LOG_LEVEL`, `CORS_ORIGINS` |
| Auth | `API_KEY` (empty = disabled) |
| Pulpito | `PULPITO_BASE`, `TEUTH_ARCHIVE_BASE` |
| LLM | `LLM_DEFAULT_PROVIDER`, `OLLAMA_*`, `OPENAI_*`, `GEMINI_*`, `CURSOR_*`, `IBM_BOB_*` |

Provider catalog (labels, model lists, default URLs) is defined in code (`app/core/llm_config.py`); env vars override per provider.

## Run locally

```bash
cp backend/.env.example backend/.env
make setup && make start
```
