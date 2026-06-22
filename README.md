# Tickr

**A free, student-built Bloomberg-lite equity research terminal.**
Plain-English AI analysis over fundamentals and filings — built for people who want research-grade data without a five-figure subscription.

---

## Vision

Most serious equity research tooling sits behind paywalls that students and independent investors can't access. Tickr is a demonstration that you can build something genuinely useful — fast, clean, and research-grade — on top of public data sources.

The goal is a two-surface product:

1. **Web terminal** — a clean, fast UI for looking up company fundamentals, filings, and AI-generated plain-English analysis across markets.
2. **MCP server** (Phase 5) — the same engine exposed as a Model Context Protocol server, making Tickr's data available directly inside Claude Code and Claude Desktop as a research tool in any workflow.

The data layer is US equities first (SEC EDGAR + Yahoo Finance, no API keys needed), with India (NSE/BSE) planned for Phase 4.

---

## Positioning

| | Tickr | Bloomberg Terminal | FactSet | Yahoo Finance |
|---|---|---|---|---|
| Price | Free | ~$27k/year | ~$12k/year | Free |
| AI analysis | Yes (planned) | Limited | Limited | No |
| Programmatic / MCP access | Yes (planned) | Expensive API | Expensive API | Unofficial |
| India equities | Planned | Yes | Partial | Yes |
| Status | In development | Mature | Mature | Mature |

Tickr is not trying to match Bloomberg's breadth. It's a focused research terminal that goes beyond raw data tables by pairing normalized fundamentals with plain-English AI analysis — the workflow tool, not the data warehouse.

> **Disclaimer:** Tickr is a research and informational tool only. Nothing here is investment advice.

---

## Architecture

Tickr uses an engine-in-the-middle pattern: all business logic lives in a central FastAPI engine; the web app and MCP server are thin clients that call it over HTTP.

```
┌──────────────────────┐    ┌──────────────────┐
│  Web App (Next.js)   │    │  MCP Server      │
│  thin client         │    │  (Phase 5)       │
└──────────┬───────────┘    └────────┬─────────┘
           │         HTTP            │
           ▼                         ▼
┌──────────────────────────────────────────────┐
│  ENGINE  (FastAPI — all logic here)          │
│                                              │
│  API routes → adapters → cache → DB         │
│  edgar.py  |  yfinance.py  |  (india Phase 4)│
└──────────────────────────────────────────────┘
           │
           ▼
SEC EDGAR (edgartools) · Yahoo Finance (yfinance)
```

Key design decisions:
- **Adapter pattern** — each data source is one file implementing a common interface. Adding India = two new files, zero engine-core changes.
- **Market-aware schema** — every company carries `market`, `exchange`, and `currency` explicitly. INR and NSE/BSE slot in as new enum values in Phase 4.
- **Lazy TTL cache** — check cache → miss → fetch live → store with TTL → return. Fundamentals cache for 1 day; AI analysis for 7 days (most expensive to generate).

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full design diagram and rules.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Engine | Python 3.11, FastAPI, pydantic v2, SQLAlchemy 2, Alembic |
| Data sources | SEC EDGAR via [edgartools](https://github.com/dgunning/edgartools), [yfinance](https://github.com/ranaroussi/yfinance) |
| Database | PostgreSQL (Neon hosted) |
| Web frontend | Next.js, TypeScript, App Router |
| MCP server | Python MCP SDK (Phase 5) |

---

## Current Status

This is an active build. Here is what is real vs. planned:

### Built

- **US equity data engine** — SEC EDGAR adapter (edgartools, XBRL parsing) and yfinance adapter, both fully implemented and tested.
- **Normalized schema** — `CompanyIdentity`, `NormalizedFundamentals` (income statement, balance sheet, cash flow, ratios), `FilingReference` — market-aware and India-ready.
- **REST API** — three endpoints: `GET /companies/{ticker}`, `/fundamentals`, `/filings`. Both `edgar` and `yfinance` sources selectable per request.
- **19 integration tests** passing against live SEC EDGAR and Yahoo Finance APIs (AAPL, JPM, BRK-B). Revenue cross-source agreement within 1%.
- **PostgreSQL schema** — `cache_entries` table defined and migrated to Neon.

### Planned (phased)

| Phase | Focus | Status |
|-------|-------|--------|
| 2b | TTL cache layer — serve repeat calls from Postgres | Next |
| 3 | Next.js web UI — company pages, fundamentals tables, filings | Planned |
| 3 | AI analysis layer — LLM-powered plain-English Q&A over filings | Planned |
| 4 | India equities — NSE/BSE adapters | Planned |
| 5 | MCP server — expose engine to Claude Code / Claude Desktop | Planned |
| — | Public deployment | Planned |

---

## Running Locally

```powershell
# 1. Clone and set up Python venv
git clone https://github.com/ShrishChauhan/Tickr.git
cd Tickr
python -m venv engine\.venv
engine\.venv\Scripts\python.exe -m pip install -e "engine[dev]"

# 2. Set environment variables
copy .env.example .env
# Edit .env — add DATABASE_URL (Postgres) and SEC_IDENTITY (your email for SEC EDGAR)

# 3. Run migrations
Push-Location engine
.\.venv\Scripts\python.exe -m alembic upgrade head
Pop-Location

# 4. Start the engine
engine\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir engine --port 8001

# 5. (Optional) Start the web frontend
cd web && npm install && npm run dev
```

Health check: `GET http://localhost:8001/health`

API docs (auto-generated): `http://localhost:8001/docs`

---

## Author

Shrish Chauhan — [f20221095@pilani.bits-pilani.ac.in](mailto:f20221095@pilani.bits-pilani.ac.in)
