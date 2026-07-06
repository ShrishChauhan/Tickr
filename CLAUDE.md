# Tickr — CLAUDE.md

**Stack:** Python 3.11 / FastAPI (engine) · Next.js 14 / TypeScript (web) · PostgreSQL
**Phase:** 4a–4d complete, architecture migration Phase A complete (A1–A6, latency) — Phase B (truthfulness layer) in progress: B1 (freshness/delay labeling), B2 (provider registry), B3 (Coinbase crypto, chosen over Binance — see K1 in PROGRESS.md) done, next B4 (Finnhub US equity real-time), then Phase 5 (profiles/auth)
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

---

## Solution discipline (YAGNI)

Prefer the leanest solution that works. Before adding a dependency, an
abstraction layer, or a new file, check in this order:
1. Does this need to exist at all?
2. Can the standard library handle it?
3. Is there a native platform/framework feature for this?
4. Is there an already-installed dependency that does this?
5. Can it be a one-liner?

Only write new code / add a dependency if all five are "no". When you defer
something (a heavier abstraction, a library), leave a one-line comment noting
what was skipped and why, so it's easy to upgrade later if actually needed.

---

## Output mode

On execution turns (implementing an approved plan, mechanical edits, bug fixes):
keep prose minimal — show the diff and the verification result, skip preamble
and restating what was asked.

On planning/architecture turns: full reasoning is wanted. Do NOT suppress
thinking when deciding structure, evaluating tradeoffs, or diagnosing a
non-obvious bug — that's where careful reasoning pays off.

---

## Lessons learned (append one-liners, keep under 20 entries)

When a non-obvious gotcha is found or a concept has to be re-explained, append
a one-line bullet here. No explanations, under 15 words each. Prune oldest when
over 20 entries.

- yfinance contractSymbol returns False (bool) for GC=F — read shortName instead
- IFRS companies may lack GrossProfit line item — graceful-degrade to em-dash
- Non-US tickers: cik is None — hide CIK row, don't show empty
- URL params with =, ^, - need decodeURIComponent before use
- Ticker resolver tries bare ticker first — US hit can shadow non-US (TCS case)
- Shell/SHEL.L reports in USD despite LSE — prefer info["currency"] over suffix
- Price data TTL is 15min; fundamentals TTL is 7d — different cache key prefixes
- recharts has no Candlestick component — use ComposedChart with custom bars
- yfinance `.info` call dominates latency — skipping the 3 statement calls barely speeds fetches up
- pydantic `@computed_field` derived from a stored field round-trips fine through TTL cache
- Binance blocks all US IPs (451) since 2022, not just India — check deploy region, not origin

---

## Planned for launch hardening (Phase 6 — NOT now)

These are deferred until deploy-time. Do not add them during feature work:
- Sentry — error tracking, add when deployed (local terminal already shows traces)
- PostHog — product analytics, add when there are real users (funnel = PM signal)
- Auth (Clerk or Supabase Auth) — add when building the profile/watchlist system
- A permanent user-data store (NOT the TTL cache) — required before profiles/saved strategies

Rationale: each integration is a dependency and config surface. Add need-driven,
not checklist-driven.
