# Tickr — CLAUDE.md

**Stack:** Python 3.11 / FastAPI (engine) · Next.js 14 / TypeScript (web, but installed `next` is actually 16.2.9 — see Session 23 in PROGRESS.md, this line is stale) · PostgreSQL
**Phase:** 4a–4d complete, architecture migration Phase A complete (A1–A6, latency) — Phase B (truthfulness layer) complete: B1 (freshness/delay labeling), B2 (provider registry), B3 (Coinbase crypto, chosen over Binance — see K1 in PROGRESS.md), B4 (Finnhub US equity real-time; backend done, no UI consumer yet — see Session 15 in PROGRESS.md) done, B5 (nsepython India) deferred indefinitely — NSE/Akamai returns a hard 403 bot-block, not intermittent breakage, see Session 16 — India equities stay on yfinance `.NS`/`.BO`, B6 (free FX source) evaluated and concluded no free source beats yfinance's existing minute-level forex data — Frankfurter/exchangerate-api are both daily-only, see Session 17 — Phase 5 (profiles/auth/watchlists) in progress: P5.1 (auth foundation) and P5.2 (profiles table/RLS, full signup, username login) done and fully verified against live Supabase, see Session 20 in PROGRESS.md — P5.3 (watchlists: items/tags/junction table with RLS, add-to-watchlist with auto-tagging, `/watchlist` list+filter view) built, migration + manual Supabase/browser verification still pending, see Session 21 in PROGRESS.md — P5.4 Part A (dashboard: live price/change%/sparkline per watchlist item + sort controls) built, equity sparklines now backed by real OHLC data via a cache-TTL split (live Finnhub quote at 30s TTL decoupled from yfinance historical bars at 900s TTL, merged into one response — see Session 24), browser verification pending user login — P5.4-B (on-demand "explain this" AI handrail, watchlist-only, constrained against fabricating causal price-move explanations) done and verified live, see Session 25 — Phase 6.1 (screener depth: saved screens — save/list/load/delete a screener universe+filter config, RLS-protected, direct-Supabase pattern mirroring watchlists) done and verified live, see Session 26 — Phase 6.2 (comparison sets — save/list/load/delete a `/compare` ticker set, jsonb tickers column, same RLS/panel shape as 6.1) done and verified live, see Session 27 — Phase 6.3 (options calculator) investigation complete, plan approved, see Session 28: yfinance options chains confirmed usable (US equities/ETFs only — zero expirations for commodities, crypto, non-US equities), spot-vs-futures modeling question resolved (moot in scope, stays open for a future commodity/Black-76 path), implementation starting as a 3-session arc — A: Black-Scholes math + tests (done, see Session 28), B: engine wiring, C: frontend; next: add screener results to watchlist (one-click add from a screener row) is still pending from 6.1, or continue the 6.3 arc with Session B; small flagged loose end (not blocking): 2 pre-existing `react-hooks/set-state-in-effect` violations in `compare/page.tsx`'s typeahead debounce, left in place, own session/own manual test per Session 27
**Session log:** PROGRESS.md · **Design rules:** ARCHITECTURE.md

---

## Commit conventions (strict)

- NEVER add `Co-Authored-By: Claude` or any AI attribution trailer to any commit.
- NEVER add a `Claude-Session:` link or any Anthropic/Claude reference to a commit message.
- All commits are authored solely as the user (Shrish Chauhan). No exceptions.
- This applies even if a commit tool/CLI defaults to adding such trailers automatically —
  strip them before finalizing the commit.
- This rule was violated once already (see PROGRESS.md) — treat it as non-negotiable.

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

User-data CRUD (watchlists, profiles, saved_screens) goes through direct Supabase access from Next.js with RLS enforcement, NOT through the FastAPI engine — the engine is for stateless/computational data only (screener, company data, price feeds). Supersedes any earlier statement that no business logic lives outside `engine/`.

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
- EquityPage never fetches price/quote data — only PriceOnlyPage renders real-time badges
- Layered cache L1 is in-process — deleting a key from another script won't clear a running server's L1
- nsepython hits Akamai 403 even on the NSE homepage — fingerprint block, not geo/rate-limit
- Free FX APIs (Frankfurter, exchangerate-api) update once/day — yfinance forex is already minute-level
- New Supabase tables/functions need manual Data API exposure — auto-expose is off by design (Settings → Data API)
- CompanyIdentity (/companies/{ticker}) has no sector field — only /search results do
- Finnhub adapter never returns OHLC bars — registry's first-success-wins skips yfinance's fallback
- Real-time price TTL (30s) is too short to piggyback a slow OHLC fetch onto — needs its own cache
- yfinance `dividendYield` is percent-shaped (0.34 = 0.34%), not a decimal — compute q = dividendRate / price instead

---

## Planned for launch hardening (Phase 6 — NOT now)

These are deferred until deploy-time. Do not add them during feature work:
- Sentry — error tracking, add when deployed (local terminal already shows traces)
- PostHog — product analytics, add when there are real users (funnel = PM signal)
- Auth (Clerk or Supabase Auth) — add when building the profile/watchlist system
- A permanent user-data store (NOT the TTL cache) — required before profiles/saved strategies

Rationale: each integration is a dependency and config surface. Add need-driven,
not checklist-driven.
