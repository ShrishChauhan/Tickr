# Tickr — CLAUDE.md

**Stack:** Python 3.11 / FastAPI (engine) · Next.js 14 / TypeScript (web) · PostgreSQL
**Phase:** 1 (data adapters) complete — Phase 2a (DB setup + migrations) in progress
**Session log:** PROGRESS.md · **Design rules:** ARCHITECTURE.md

---

## Directory map

| Path | Purpose |
|------|---------|
| `engine/` | FastAPI engine — all business logic lives here |
| `engine/app/schema/` | Internal normalized data models (source of truth) |
| `engine/app/adapters/` | One file per data source; implement `DataAdapter` |
| `engine/app/cache/` | TTL caching layer over live fetches |
| `engine/app/analysis/` | AI analysis interface + provider |
| `engine/app/db/` | SQLAlchemy models + Alembic migrations |
| `engine/app/api/` | HTTP route handlers (thin — no logic here) |
| `web/` | Next.js frontend (thin client — no business logic) |
| `docs/` | Extended reference docs linked from this file |

---

## Running

```powershell
# Engine (from repo root)
engine\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir engine

# Web (from repo root)
cd web && npm run dev
```

Health check: `GET http://localhost:8000/health`

---

## Key conventions

1. **No business logic outside `engine/`.** The web app and (future) MCP server are thin clients.
2. **Adapter pattern.** Adding a data source = new file in `adapters/`, implement `DataAdapter`. Zero engine-core changes.
3. **Schema-only internal flow.** Adapters translate raw API responses into `engine/app/schema/` types. Nothing else passes between layers.
4. **Lazy TTL cache.** Check cache → miss → fetch live → serve + store. TTL constants in `cache/ttl_config.py`.
5. **Secrets in `.env` only.** Never committed. Use `.env.example` as the template.

---

## Environment setup

```powershell
# Python engine
python -m venv engine\.venv
engine\.venv\Scripts\python.exe -m pip install -e "engine[dev]"

# Alembic (run after DATABASE_URL is set in .env)
engine\.venv\Scripts\python.exe -m alembic upgrade head
```

PostgreSQL not installed locally — set `DATABASE_URL` in `.env` to point at a local or hosted instance before running migrations. See PROGRESS.md Session 0 for details.
