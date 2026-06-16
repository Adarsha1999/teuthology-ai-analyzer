# Teuthology AI Analyzer

Analyze [Pulpito](https://pulpito.ceph.com) teuthology runs with AI-powered failure reports. Fetches failed job logs, builds a digest, and calls the LLM configured in **`backend/.env`** (Ollama by default; OpenAI, Gemini, Cursor, Bob as optional providers) for structured failure analysis.

**UI:** FastAPI backend + React frontend (port **3000** in dev; API on **8000**).

## Project structure

```
teuthology-ai/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI route handlers
│   │   ├── core/             # Settings and LLM provider catalog
│   │   ├── db/               # SQLAlchemy models, session, migrations
│   │   ├── providers/        # LLM provider implementations (Strategy + Factory)
│   │   ├── services/         # Business logic (analysis, connection, session)
│   │   └── models/           # Pydantic schemas
│   ├── alembic/              # Database migrations (PostgreSQL)
│   ├── tests/
│   ├── .env.example          # Copy to .env for all configuration
│   ├── requirements.txt      # Unpinned dependencies
│   └── requirements.lock     # Pinned dependencies (used in Docker)
├── frontend/                 # React + Vite UI
├── docker-compose.yml
├── Makefile
├── setup_local.sh
├── start.sh
├── ARCHITECTURE.md
└── DEPLOY.md
```

See **ARCHITECTURE.md** and **DEPLOY.md** for layout and deployment.

## Prerequisites

- Python 3.11+
- Node.js 18+ (for the React frontend)
- **Ollama (default):** [Ollama](https://ollama.com) running locally with models pulled (e.g. `ollama pull llama3.2`)
- **PostgreSQL (production):** PostgreSQL 15+ for production; SQLite used for local dev/test
- **Optional providers:** OpenAI, Gemini, Cursor, IBM Bob — API keys in `backend/.env`

## Setup

**Quick (recommended):**

```bash
./setup_local.sh
./start.sh
```

**Manual:**

```bash
make setup
make start
```

## Run (development)

Open **http://localhost:3000** (frontend) — API on **http://localhost:8000**

Or run services separately: `make backend` / `make frontend`

## Docker

```bash
cp backend/.env.example backend/.env
docker compose up --build      # PostgreSQL + backend + frontend
```

See **DEPLOY.md** for full details.

## Usage

1. Pick a model from the **top-bar dropdown** (connects automatically)
2. **Dashboard** → paste Pulpito run URL → **Analyze run**
3. Analysis runs in the background — poll for results automatically

Use **LLM settings** for base URL (Ollama), API keys (cloud providers), and timeout.

**Teuth Assistant** (header button) is a chatbot grounded in the [upstream Teuthology documentation](https://docs.ceph.com/projects/teuthology/en/latest/README.html); it uses whichever model is connected.

## Production (single server)

```bash
cd frontend && npm run build && cd ..
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Serves the built UI from `frontend/dist/` on the same port as the API.

## Configuration

All settings live in **`backend/.env`** (copy from `backend/.env.example`):

```bash
cp backend/.env.example backend/.env
```

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL (default) or SQLite for dev |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | Connection pool settings (PostgreSQL) |
| `API_KEY` | API authentication (empty = disabled) |
| `LLM_DEFAULT_PROVIDER` | `ollama` (default), `openai`, `gemini`, `cursor`, `bob` |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | Local Ollama |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | OpenAI (optional) |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Gemini (optional) |
| `CURSOR_API_KEY`, `CURSOR_MODEL` | Cursor SDK (optional) |
| `BOBSHELL_API_KEY`, `IBM_BOB_*` | IBM Bob Shell (optional) |
| `PULPITO_BASE`, `TEUTH_ARCHIVE_BASE` | Log sources |

Built-in provider catalog is in `backend/app/core/llm_config.py`; env vars override URLs, models, and keys.

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health (+ Ollama status) |
| GET | `/api/ready` | Readiness probe |
| GET | `/api/live` | Liveness probe |
| GET | `/api/config` | LLM providers |
| GET | `/api/connection` | Connected model? |
| POST | `/api/connect` | Connect LLM (session cookie) |
| POST | `/api/disconnect` | Disconnect |
| POST | `/api/analyze` | Submit analysis (returns 202 + task_id) |
| POST | `/api/analyze-local` | Submit local archive analysis (202 + task_id) |
| GET | `/api/analyze/status/{task_id}` | Poll analysis result |
| GET | `/api/history` | Recent runs |
| POST | `/api/assistant/chat` | Teuth Assistant chat |

## Tests

```bash
make test
# or: PYTHONPATH=backend pytest backend/tests/ -v
```

## License

This project is licensed under the [Apache License 2.0](LICENSE).
