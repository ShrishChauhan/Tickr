# Tickr — CLAUDE.md

**Stack:** Python 3.11 / FastAPI (engine) · Next.js 14 / TypeScript (web, but installed `next` is actually 16.2.9 — see Session 23 in PROGRESS.md, this line is stale) · PostgreSQL
**Phase:** 4a–4d complete, architecture migration Phase A complete (A1–A6, latency) — Phase B (truthfulness layer) complete: B1 (freshness/delay labeling), B2 (provider registry), B3 (Coinbase crypto, chosen over Binance — see K1 in PROGRESS.md), B4 (Finnhub US equity real-time; backend done, no UI consumer yet — see Session 15 in PROGRESS.md) done, B5 (nsepython India) deferred indefinitely — NSE/Akamai returns a hard 403 bot-block, not intermittent breakage, see Session 16 — India equities stay on yfinance `.NS`/`.BO`, B6 (free FX source) evaluated and concluded no free source beats yfinance's existing minute-level forex data — Frankfurter/exchangerate-api are both daily-only, see Session 17 — Phase 5 (profiles/auth/watchlists) in progress: P5.1 (auth foundation) and P5.2 (profiles table/RLS, full signup, username login) done and fully verified against live Supabase, see Session 20 in PROGRESS.md — P5.3 (watchlists: items/tags/junction table with RLS, add-to-watchlist with auto-tagging, `/watchlist` list+filter view) built, migration + manual Supabase/browser verification still pending, see Session 21 in PROGRESS.md — P5.4 Part A (dashboard: live price/change%/sparkline per watchlist item + sort controls) built, equity sparklines now backed by real OHLC data via a cache-TTL split (live Finnhub quote at 30s TTL decoupled from yfinance historical bars at 900s TTL, merged into one response — see Session 24), browser verification pending user login — P5.4-B (on-demand "explain this" AI handrail, watchlist-only, constrained against fabricating causal price-move explanations) done and verified live, see Session 25 — Phase 6.1 (screener depth: saved screens — save/list/load/delete a screener universe+filter config, RLS-protected, direct-Supabase pattern mirroring watchlists) done and verified live, see Session 26 — Phase 6.2 (comparison sets — save/list/load/delete a `/compare` ticker set, jsonb tickers column, same RLS/panel shape as 6.1) done and verified live, see Session 27 — Phase 6.3 (options calculator) complete — all 3 sessions done and verified live: A: Black-Scholes math + tests (Session 28), B: engine wiring (adapter, orchestration service, schema, 3 `/options/*` endpoints; freshness-vs-atomicity question resolved by disclosure — per-input `as_of` timestamps plus per-contract `last_trade_date` rather than forcing a false atomic snapshot — Session 29), C: frontend (`/options` route — ticker typeahead, cascading expiration/type/strike selection, IV override, Greeks + explanations + freshness line; also fixed a live risk-free-rate cache bug where a pre-`fetched_at` cache row crashed `/calculate` — Session 30); US equities/ETFs only per scope, no persistence/saved-calculation feature built; Phase 7 (thin-slice backtester) in progress — P7.1 (historical-data pipeline) done: yfinance substituted for Stooq (Stooq now hard-blocked by a site-wide JS anti-bot challenge plus a paywalled bulk-zip subdomain — same class of block as B5, not worked around), 567 unique universe tickers backfilled to 20y daily OHLC as local Parquet (117 MB), DuckDB-over-local-Parquet querying proven end-to-end, see Session 31 in PROGRESS.md; R2 upload + DuckDB-over-HTTP follow-up done — 567 Parquet files uploaded to R2, DuckDB-over-HTTP query (modern `CREATE SECRET TYPE r2` auth) verified to return identical results to the local probe, `historical_data.py` still reads local disk (mechanism proven, production not cut over), see Session 33 in PROGRESS.md — P7.2 (MA-crossover backtest mechanism) done: `services/ma_crossover.py` (pure math, hardcoded-default 50/200-day golden/death cross), `services/historical_data.py` (first service-layer DuckDB wrapper), `services/backtest.py` (orchestrator) — methodology made explicit rather than silently baked in: signal on bar T's Adj Close fills at T+1's Adj Close (no synthetic Adjusted-Open), 10bps/side transaction cost, fractional-share all-in/all-out sizing, open positions marked-to-market not force-closed, max drawdown via running-max not naive global-min/max; 19 tests against a hand-computed-and-independently-verified synthetic series plus real-AAPL demo script (2395.64% return, 8 trades matching known market history), 66/66 repo-wide, see Session 32 in PROGRESS.md; Phase 8 (no-code composer) started — slice 1 (Session 34) done: shared bar-timing/cost/sizing/drawdown execution loop extracted into `services/backtest_core.py`, generalized rule vocabulary (`services/rule_engine.py`: `Indicator` SMA/PRICE, `Rule`, `Strategy`, NaN-safe `CROSSES_ABOVE`/`CROSSES_BELOW` edge detection) proven equivalent to the existing MA-crossover on both the hand-verified synthetic series and real AAPL data, 78/78 repo-wide, `ma_crossover.py` now a thin wrapper with zero breaking changes to existing imports — no engine endpoint or Pydantic schema yet, deliberately deferred until the composer UI needs one; slice 2 (Session 35) done: RSI added as third indicator (`services/indicators.py`, new home for `sma`/`rsi`, extracted out of `ma_crossover.py`) — Wilder's RSI convention chosen over Cutler's (data-length-dependency tradeoff doesn't apply here; confirmed live against StockCharts/Wikipedia/QuantInsti/TC2000), warmup boundary is one bar later than an equivalent-window SMA (differences start at index 1, not 0), hand-verified 12-bar synthetic reference cross-checked via isolated calculation, mean-reversion Strategy (RSI(14) crosses below 30 / above 70) proven finite and plausible on real AAPL data (16 trades, 128.5% return, 81.25% win rate over 20y), 85/85 repo-wide; slice 3 (engine endpoint) done: `POST /backtest/{ticker}` + `schema/backtest.py` (`IndicatorSchema`/`RuleSchema`/`StrategySchema`/`BacktestRequest`/`BacktestResponse`), curl-verified end-to-end against the exact known-good AAPL numbers from slices 1–2 — landed in commit `1ff6367` but never got its own PROGRESS.md session entry, a still-open documentation gap (flagged, not backfilled, in Session 36); slice 4 (composer frontend) complete — full rule-based backtest composer (Sessions 34–37) done and verified live at `/backtest`: build any entry/exit rule (SMA or RSI, either side, either crossing direction, against a value or another indicator) from a blank page through to results (equity curve, summary stats, trade table, methodology disclosure); both the trend-following (SMA(50/200): 2395.64%/8 trades) and mean-reversion (RSI(14) 30/70: 128.5%/16 trades/81.25% win rate) paths reproduce their known-good numbers exactly via real browser walkthroughs, not just backend calls; edge cases (no-local-data 404, zero-trade win_rate rendering as "N/A" not "0%", disabled-until-genuinely-valid submit gating) all verified live — see Session 37 in PROGRESS.md; still open for Phase 8 overall: universe-level backtesting (survivorship bias needs its own treatment), the overfitting-risk pedagogical handrail, further indicators (MACD, Bollinger), no saved-strategies persistence, no rule-combination (AND/OR) logic; two commits (slice 3's engine endpoint `1ff6367`, composer Session 2's wiring `2a61e01`) still lack their own PROGRESS.md session entries, flagged repeatedly (Sessions 36, 37) and deliberately not backfilled; note `ROADMAP.md`/`UPCOMING_PHASES.md`/`HANDOFF.md` are referenced elsewhere in this file and in PROGRESS.md but don't actually exist in the repo (found in Session 31) — all phase/sequencing content actually lives in ARCHITECTURE.md §4–§8; also still open: add screener results to watchlist (one-click add from a screener row) pending from 6.1, Phase 6.2's deferred radar-chart cap question, and small flagged loose end (not blocking): 2 pre-existing `react-hooks/set-state-in-effect` violations in `compare/page.tsx`'s typeahead debounce, left in place, own session/own manual test per Session 27, and the same pre-existing pattern now also present in `backtest/page.tsx` (Session 36) for the same reason; Phase 9.1 (FRED risk-free rate) complete — options calculator now sources `r` from FRED's `DTB3` series (verified live to track yfinance `^IRX` within ~1bp; `DGS3MO` was checked and rejected, ~15bp off on a coupon-vs-discount basis mismatch), falling back to the existing `^IRX` path on any FRED failure (blank key, network error, empty observation window); new `r_source` field on `GreeksInputs` discloses which provider served the rate, `r_as_of` is FRED's own (honestly lagged, ~1 business day + weekends) observation date when FRED serves it; 98/98 tests pass, live browser-verified via Playwright — see Session 38 in PROGRESS.md; Phase 9.2 (Loader-registry refactor) Chunks 1-3 complete — provider_registry.py's proven quote resilience-chain pattern generalized to a (data_type, asset_class) registry per ARCHITECTURE.md's already-declared shape: Chunk 1 added a `Loader` protocol + `LoaderLicense` enum and generalized the registry key to tuples with zero behavior change to quote chains; Chunk 2 migrated the risk-free-rate chain in while explicitly preserving its re-raise-on-total-failure contract (not homogenized into the quote chain's swallow-to-None style — a total outage must fail loudly, not silently price options at a fabricated rate); Chunk 3 added a Parquet fallback tail for equity OHLC, resolving Parquet's Adj Close to match yfinance's dividend-adjusted convention and preserving the OHLC chain's ([], None, None) total-failure contract — a deliberately different asymmetry from Chunk 2's; three chunks were coded in one working tree before any commit, which initially produced a non-importable first commit — caught via git show and fixed by reconstructing genuine incremental diffs, each final commit verified independently importable via an isolated worktree before pushing; 119/119 tests pass, live end-to-end verified for both success and failure paths on both new chains — see Session 39 in PROGRESS.md; Chunk 4 (DataAdapter license tags) next
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
- Cached dict payloads: use .get() with a miss fallback, not [key] — old rows lack new fields
- yfinance OHLC is always split-adjusted even with auto_adjust=False — only dividends toggle

---

## Planned for launch hardening (Phase 6 — NOT now)

These are deferred until deploy-time. Do not add them during feature work:
- Sentry — error tracking, add when deployed (local terminal already shows traces)
- PostHog — product analytics, add when there are real users (funnel = PM signal)
- Auth (Clerk or Supabase Auth) — add when building the profile/watchlist system
- A permanent user-data store (NOT the TTL cache) — required before profiles/saved strategies

Rationale: each integration is a dependency and config surface. Add need-driven,
not checklist-driven.
