# Tickr — Architecture

> Free-tier-only (₹0) equity research platform. This document is the design
> reference for scaling Tickr from a single-user cache app to a multi-source,
> multi-user research + strategy platform without leaving free tiers.
> Every recommendation states its free-tier limit and what happens at the limit.
>
> The canonical **core design rules** (adapter pattern, internal schema, caching
> discipline, no-logic-in-clients) are retained in §9 at the foot of this file —
> CLAUDE.md points here for them.

## 1. Current architecture (as-is)

```
┌────────────────────────────────────────────────────────────┐
│ web/  (Next.js 16.2.9 / React 19 — ALL client components)   │
│  • hand-rolled fetch() in web/lib/api.ts (no SWR/react-query)│
│  • useEffect fetching, no cache/revalidate opts              │
│  • /screener: CLIENT-SIDE fan-out, CONCURRENCY=8, up to      │
│    ~500 requests to engine per load                          │
│  • /compare: CLIENT-SIDE, sequential 2 calls/ticker, max 5   │
│  • no prefetch-on-hover, no stale-while-revalidate           │
└───────────────────────────┬────────────────────────────────┘
                            │ HTTP  /api/v1/*  (CORS: localhost:3000)
┌───────────────────────────▼────────────────────────────────┐
│ engine/  FastAPI                                             │
│  routes.py = HTTP + cache-orchestration + adapter dispatch   │
│              + normalization (business logic leaked in)      │
│  adapters/: DataAdapter → EdgarAdapter, YFinanceAdapter      │
│   • every method = run_in_executor(None, _sync_*) on default │
│     ThreadPoolExecutor (de-facto concurrency ceiling)        │
│   • fundamentals fetch = .info + 3 statement calls           │
│     (4 network round-trips per ticker); uses full .info      │
│  cache/: PostgresCacheBackend (sync SQLAlchemy in executor)  │
│   • NO in-memory tier, NO request coalescing, NO pre-warm    │
│   • NO lifespan/startup hooks                                │
└───────────────────────────┬────────────────────────────────┘
                            │ psycopg2 (sync, AUTOCOMMIT, pool 5+5)
┌───────────────────────────▼────────────────────────────────┐
│ Neon Postgres — ONE table: cache_entries                    │
│  cache_key(uniq) · data_type · ticker · source · payload    │
│  (JSON) · created_at · expires_at ; TTL enforced lazily at   │
│  read (expires_at > now); autosuspend after 5 min idle       │
└─────────────────────────────────────────────────────────────┘
```

**Confirmed TTLs** (`engine/app/cache/ttl_config.py`): PRICE 30s *(exported but
unused)*, PRICE_DATA 900s (15 min), FUNDAMENTALS 86 400s (1 day), FILING_REF 1
day, AI_ANALYSIS 604 800s (7 days), COMPANY_INFO 1 day; SEARCH 3600s (inline in
routes.py).

**Honest bottleneck list (ranked):**
1. **Screener is client-fanned-out.** The browser fires up to ~500 individual
   HTTP requests (CONCURRENCY=8) — cold sp500 takes 1–2 min. This is the #1 UX
   pain and it also violates CLAUDE.md ("no business logic in the client").
2. **Every cache hit is a Neon network round-trip** (~50–200 ms; worse on the
   5-min-idle cold start). No in-process hot layer exists.
3. **Fundamentals = 4 upstream round-trips per ticker** (`.info` + 3 statements)
   even for the screener, which only displays a handful of ratios.
4. **No request coalescing** — two simultaneous misses for the same key both hit
   upstream and both upsert.
5. **No SWR on the client** — expired data can't be shown instantly while
   refreshing; every navigation re-fetches from scratch.
6. **Single source (yfinance) = 15–20 min delay**, unlabeled — the product isn't
   truthful about freshness.
7. **routes.py mixes HTTP + orchestration + normalization** — friction for adding
   sources or batch endpoints.
8. **Single Neon DB conflates disposable cache with (future) permanent user
   data** — different durability needs, no separation.

## 2. Target architecture (to-be)

```
┌──────────────────────────────────────────────────────────────┐
│ web/  Next.js + SWR                                            │
│  • SWR client cache: stale-while-revalidate + dedup           │
│  • preload() prefetch-on-hover (search results, screener rows) │
│  • per-asset freshness/delay badge ("Real-time" | "~15m delay")│
│  • screener & compare call ONE batched engine endpoint each    │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTP (batched)
┌───────────────────────────▼──────────────────────────────────┐
│ engine/  FastAPI                                              │
│  api/       thin handlers only                                │
│  services/  cache-orchestration + fan-out (asyncio.gather +   │
│             Semaphore) + normalization  ← extracted from routes│
│  ┌──────────────────────────────────────────────────────────┐│
│  │ L1: in-process TTLCache (hot, dies on restart — fine)     ││ NEW
│  └───────────────────────────┬──────────────────────────────┘│
│  provider registry (OpenBB-style): (data_type, asset_class)   │ NEW
│    → ordered provider list, yfinance = universal fallback     │
│  adapters/: yfinance · edgar · binance · finnhub · nsepython  │ NEW×3
│             · fx-source                                        │
└───┬───────────────────┬───────────────────┬──────────────────┘
    │ L2 cache          │ user data + auth   │ historical bulk
┌───▼──────────┐  ┌─────▼──────────┐  ┌──────▼─────────────────┐
│ Neon Postgres│  │ Supabase       │  │ Cloudflare R2          │
│ cache_entries│  │ profiles,      │  │ Parquet OHLC (DuckDB   │
│ (disposable) │  │ watchlists,    │  │ queries over HTTP)     │
│ EXISTS       │  │ strategies+AUTH│  │ HISTORICAL / BACKTEST  │
│              │  │ PHASE 5        │  │ STRATEGY-CREATOR       │
└──────────────┘  └────────────────┘  └────────────────────────┘
```

The engine stays the single home of business logic (§9 rule 4). New sources are
new files in `adapters/` behind the provider registry (§9 rule 1). Neon remains
the shared L2 cache; Supabase and R2 are added **only** when their driving feature
is built (see §7 triggers).

## 3. Latency plan (P1) — layered budget

Three distinct latency sources, attacked independently.

### 3a. Source latency (yfinance fetch itself — can only be masked)
- **Pre-warming (biggest screener win).** Universes are static (~680 unique
  tickers across dow30/nifty50/nasdaq100/sp500). A daily GitHub Actions cron
  (InsightPulse pattern) calls the batch endpoint per universe, keeping the 1-day
  fundamentals cache always warm. Cost ₹0. *Limit:* GitHub Actions free = 2000
  min/month private (unlimited public); a full warm run is minutes → negligible.
- **"Lite" fundamentals for the screener.** Screener only shows a few ratios,
  which already come from `.info`. Add a lite path that fetches `.info` **only**,
  skipping the 3 statement calls → 4 round-trips → 1 per ticker. *(Confirm the 8
  screener filter fields are all `.info`-derivable during build — open question.)*
- **Request coalescing** (in-flight dedup: one upstream fetch per key even under
  concurrent misses) — **deferred**, low value at single-user scale. Trigger:
  multi-user deploy showing duplicate concurrent misses in logs.
- `fast_info` is **not** pursued — yfinance docs confirm it's no longer faster
  than the (fixed) `.info`.

### 3b. Cache-layer latency (Neon round-trip per hit)
- **Add an in-process L1 `TTLCache`** (stdlib dict-with-expiry or `cachetools`)
  in front of `PostgresCacheBackend`. Read path: L1 → L2 (Neon) → source; writes
  populate both. *Limit:* bounded by process RAM (cap maxsize, e.g. a few
  thousand entries ≈ tens of MB); **dies on restart — acceptable, it's a cache**
  (Ghostfolio explicitly falls back to in-memory for exactly this). Reads become
  microsecond-scale and Neon query volume drops (saves CU-hours).
- **Upstash Redis (shared L1) — deferred.** Free = **500 K commands/month ≈ 16.7 K/
  day**, 256 MB. A single sp500 screener load ≈ 500 reads, so ~33 loads/day would
  exhaust it — too tight, and unnecessary while there's one engine process.
  Trigger to adopt: deployed with **>1 engine instance** needing a shared cache.
  *At limit:* commands rejected → fall back to L2.
- **Neon free tier:** 0.5 GB storage, **100 CU-hours/month**, 5 GB egress; compute
  **hard-suspends** at the CU-hour limit. Cache payloads are small (~5–20 KB JSON);
  0.5 GB is far more than needed → **capacity is not the bottleneck, latency is**
  (§3b solves it). The pre-warm cron keeps the DB awake during its run — bounded
  and scheduled, so CU-hour burn stays well under 100/month.

### 3c. Frontend perceived latency
- **Batch endpoints.** New `GET /api/v1/screener/{key}/rows` returns all
  constituents' lite fundamentals in **one** response (engine fans out internally
  with `asyncio.gather` + a `Semaphore`, reading warm cache). Screener: ~500
  browser requests → 1. Same treatment for /compare.
- **Adopt SWR** (Vercel, lightweight, ~4 KB, pairs with Next). Gives
  stale-while-revalidate (show cached-but-expired instantly, refresh in
  background), automatic dedup, and `preload()` **prefetch-on-hover** for search
  results and screener rows. Replaces the hand-rolled `fetch` in `web/lib/api.ts`.
  *Open risk:* `web/AGENTS.md` flags this as a non-standard Next 16 build — smoke-
  test SWR in a throwaway route before the full migration.

### Latency budget (before → after)
| Scenario | Now | After |
|---|---|---|
| Warm company page (cache hit) | ~150–400 ms (2–3 serial Neon round-trips) | **~3 ms** (L1) + instant via SWR on repeat |
| Cold company page | 1–3 s (source), no masking | 1–3 s **masked** by skeleton + prefetch-on-hover (fetch starts on hover) |
| Screener sp500 **cold** | **1–2 min** (~500 client requests) | **~3 s** (pre-warmed + 1 batch request) |
| Screener sp500 **warm** | 500 client requests @ conc.8, each a Neon hit | **~200–500 ms** (1 batch request, L1-served) |

## 4. Data-source plan (P2) — per-asset-class matrix + phasing

Scope = **Aggressive** (user decision), fragile scrapers gated behind kill-tests,
yfinance = universal fallback via the provider registry.

| Asset class | Chosen source | Latency | Free limit | At the limit | Effort |
|---|---|---|---|---|---|
| **Crypto** | Binance public REST `/ticker/24hr` (WS later) | **Real-time** | No key; weight-based (price=2, generous) | throttle → fall back to Coinbase/Kraken → yfinance | Low–Med |
| **US equity (single quote)** | Finnhub `/quote` (WS 50-sym for live) | **Real-time** | **60 calls/min** (REST); WS 50 symbols | 429 → fall back to yfinance quote | Low–Med |
| **US equity (screener bulk)** | yfinance + cache (unchanged) | ~15 min | — | — | none |
| **India NSE/BSE** | nsepython / jugaad-data (NSE JSON) | ~near-real-time | unofficial scrape; needs headers/cookies | breakage → fall back to yfinance `.NS` | Med (**fragile**) |
| **Forex** | Free FX API (e.g. Frankfurter/exchangerate.host) | daily–intraday | varies (see kill-test) | fall back to yfinance | Med |
| **Commodities** | yfinance (no good free real-time) | ~15 min | — | labeled "delayed" | none |
| **Fundamentals** | yfinance + edgar (unchanged) | 1-day TTL | — | — | none |

**Truthfulness layer (do first):** a per-asset badge driven by which provider
served the data — "Real-time" vs "~15 min delayed". Data already carries `source`;
freshness rendering (`relativeTime` in `web/lib/format.ts`) already exists in 2
places — extend it into an explicit delay label. Target user is research-oriented
retail, so *delayed-but-honest* is acceptable everywhere real-time isn't free.

**Provider registry (OpenBB pattern):** `(data_type, asset_class) → ordered
provider list`; the engine tries providers in order and falls back on
error/missing-credential, exactly like OpenBB's priority list. This is what makes
"Aggressive" safe — every fragile source degrades to yfinance automatically.

**Phased adoption order** (fragile last, each gated):
1. Freshness/delay labeling (no new adapter).
2. Binance crypto real-time (kill-test geo first — see §8).
3. Finnhub US real-time quote (reuse the unused `PRICE_TTL_SECONDS=30`).
4. Provider registry formalization (if 2–3 got messy).
5. nsepython India — **only after** its 1-week reliability kill-test passes.
6. Free FX source — **only after** its kill-test.

## 5. Data-architecture plan (P3) — which store holds what

**Principle: separate by durability/purpose, not shard by capacity.**

| Store | Holds | Free limit | At the limit | When |
|---|---|---|---|---|
| **Neon Postgres** | `cache_entries` (disposable TTL cache) + in-process L1 in front | 0.5 GB · 100 CU-h/mo · 5 GB egress | compute suspends (hard) | **EXISTS** |
| **Supabase** | profiles, watchlists, strategies + **Auth** | 0.5 GB DB · 1 GB files · 50 K MAU · 2 active projects | project **pauses after 7 days idle** | **Phase 5** |
| **Cloudflare R2** | historical OHLC as Parquet (DuckDB queries over HTTP) | **10 GB · zero egress** · 1 M Class-A / 10 M Class-B ops/mo | ops throttle / storage cap | **Strategy creator** |

**(a) Bottleneck = latency, not capacity.** Cache payloads are tiny; 0.5 GB Neon
is ample. The pain is per-hit round-trip + cold-start — solved by the L1 (§3b).

**(b) Separate cache from user data.** When Phase 5 starts, add **Supabase** for
permanent user data because its free tier bundles **Auth** (50 K MAU) — killing
the Phase-5 auth requirement for free. Keep Neon for the disposable cache (wiping
it must never touch user data). Mitigate Supabase's 7-day idle-pause with a
GitHub Actions keep-alive cron (InsightPulse pattern); acceptable for a
user-facing product that will also get organic traffic.

**(c) "Multiple linked free DBs" (sharding) — do NOT do this.** Sharding solves
only *capacity*; it does **not** solve latency, and it *breaks* consistency
(no cross-DB joins) and adds routing/ops complexity. Tickr has no capacity
problem: TTL-purging keeps the cache small forever, and hobby-scale user data is
tiny. The *good* version of the idea is separation-by-purpose (cache→Neon,
userdata+auth→Supabase, historical→R2), which this plan already does. Trigger to
ever reconsider real sharding: a single free DB **>80 % full of non-purgeable
data** — effectively never for the cache.

**(d) Historical data for backtesting (biggest future consumer) → R2 + DuckDB.**
Sizing: 20 y daily OHLC ≈ 5 000 rows/ticker ≈ ~50 KB Parquet; **5 000 tickers ×
20 y ≈ ~1.25 GB** — blows Neon's 0.5 GB but fits R2's **10 GB free (zero egress)**
comfortably. Bulk-source from **Stooq** (decades of free daily OHLC, bulk CSV) +
`yf.download(threads=True)` for gaps; store as Parquet on R2; backtests query with
**DuckDB directly over R2 HTTP** (no DB server needed). Build only when the
strategy creator is built.

## 6. Patterns adopted from comparable products (P4)

1. **OpenBB — standardized provider interface + priority-list fallback**
   ("connect once, consume everywhere"). *How they do it:* 100+ sources behind one
   interface; user sets a provider or an ordered list, first with valid creds wins.
   *How we do it free:* Tickr already has `DataAdapter`; formalize a
   `(data_type, asset_class) → ordered provider list` registry with yfinance as
   universal fallback. This is the backbone of the Aggressive multi-source plan.
2. **Ghostfolio — Redis market-data cache + scheduled fetch, in-memory fallback.**
   *How they do it:* Redis caches quotes/FX; a Market Data Service fetches all
   tracked symbols on a schedule; without Redis it falls back to in-memory + rate-
   limits upstream. *How we do it free:* in-process L1 cache (§3b) = their
   in-memory fallback; GitHub Actions pre-warm cron (§3a) = their scheduled fetch;
   respect Finnhub's 60/min in the registry.
3. **Ghostfolio / Maybe — separate persistent DB for user data**, distinct from
   the market-data cache. *How we do it free:* Neon (cache) + Supabase (user data
   + auth), §5b.
4. **TradingView — websocket streaming datafeed, subscribe per active symbol.**
   *How we do it free:* adopt **selectively** — a Binance/Finnhub WS pushes live
   ticks only for the **currently-viewed** symbol; never build general WS fan-out.
5. **Backtesting stacks (OpenBB extensions, quant tooling) — bulk flat files over
   per-request APIs for history.** *How we do it free:* Stooq bulk CSV → Parquet on
   R2, queried by DuckDB (§5d).

## 7. Migration sequencing (one independently-verifiable deliverable per session)

Hard rule: each chunk executes+verifies in ~<30 min. **Latency-first** order
(user decision). Dependencies noted.

**Phase A — latency (no new external accounts):**
- **A1. In-process L1 TTLCache** in `cache/` in front of `PostgresCacheBackend`.
  *Dep:* none. *Verify:* hit an endpoint twice; 2nd is memory-served (log +
  latency <5 ms).
- **A2. Extract cache-orchestration + normalization from `routes.py` into
  `engine/app/services/`** (fundamentals + company paths first). *Dep:* A1.
  *Verify:* endpoints return identical payloads; routes.py handlers are thin.
- **A3. Batch screener endpoint** `GET /screener/{key}/rows` with internal
  `asyncio.gather` + `Semaphore`, using a **lite** `.info`-only fundamentals
  fetch. *Dep:* A2. *Verify:* one request returns all rows; confirm the 8 filter
  fields are `.info`-derivable.
- **A4. Frontend: screener + compare call the batch endpoints.** *Dep:* A3.
  *Verify:* Network tab shows 1 request, not ~500; cold vs warm timing.
- **A5. GitHub Actions pre-warm cron** hitting batch endpoints per universe daily.
  *Dep:* A3. *Verify:* cache populated post-run; cold sp500 now ~warm.
- **A6. Adopt SWR** in `web/lib/api.ts` + prefetch-on-hover (search, screener
  rows). *Dep:* none (but smoke-test SWR on the Next-16 build first). *Verify:*
  repeat navigation instant; hover-then-click page pre-fetched.

**Phase B — fresher data (provider registry + adapters):**
- **B1. Per-asset freshness/delay badge.** *Dep:* none. *Verify:* crypto shows
  "Real-time" after B3; others show "~15 min delayed".
- **B2. Provider registry** `(data_type, asset_class) → ordered list`, yfinance
  fallback. *Dep:* A2. *Verify:* forcing a provider error falls through to
  yfinance.
- **B3. Binance crypto real-time adapter.** *Dep:* B2 + geo kill-test (§8).
  *Verify:* crypto price matches exchange live, not 15-min delayed.
- **B4. Finnhub US real-time quote adapter** (30 s TTL). *Dep:* B2. *Verify:*
  fresher than yfinance; never exceeds 60/min for single-company use.
- **B5. nsepython India adapter** — *Dep:* B2 + **1-week reliability kill-test
  passed** (§8). *Verify:* NSE quote fresher than `.NS`; auto-fallback on break.
- **B6. Free FX source** — *Dep:* B2 + kill-test. *Verify:* FX quote served,
  fallback works.

**Deferred (documented, NOT sequenced — with trigger conditions):**
- Upstash Redis shared cache → deployed with >1 engine instance.
- Supabase user data + auth → Phase 5 (profiles/watchlists) begins.
- R2 + DuckDB historical Parquet → strategy-creator build begins.
- Request coalescing → multi-user deploy shows duplicate concurrent misses.
- DB sharding → single free DB >80 % full of non-purgeable data (≈never).

## 8. Kill-tests & open risks

| # | Recommendation | Cheap test before committing build time |
|---|---|---|
| K1 | **Binance geo** | ⚠️ Binance is geo-restricted in parts of India. Curl the public ticker from the deploy region **before** B3; if blocked, switch to Coinbase/Kraken. **Blocking risk.** |
| K2 | nsepython reliability | Run it for ~20 NSE tickers daily for **1 week**; measure breakage rate. Ship B5 only if low. |
| K3 | Finnhub real-time | Poll AAPL for a session; confirm <60/min never exceeded for single-company use and price is genuinely fresher than yfinance. |
| K4 | Free FX source | Test chosen FX API's actual update cadence + rate limit for a day; confirm it beats yfinance. |
| K5 | SWR on Next 16 | `web/AGENTS.md` flags a non-standard build — wire SWR into one throwaway route and confirm dedup/SWR/preload work before A6. |
| K6 | Lite fundamentals | Confirm all 8 screener filter fields are derivable from `.info` alone; if any need a statement call, keep it in the lite path. |
| K7 | Upstash (deferred) | 20-line script simulating a day's cache traffic (500 reads × N screener loads) vs 16.7 K/day cap before adopting. |
| K8 | Supabase keep-alive (deferred) | Confirm a 6-day GitHub Actions cron ping prevents the 7-day pause. |
| K9 | R2 + DuckDB (deferred) | 1 ticker's 20 y Stooq CSV → Parquet → DuckDB query over R2 HTTP; extrapolate size ×5 000 vs 10 GB. |

**Open questions (marked inconclusive rather than guessed):**
- **K1 (Binance geo from India)** — biggest unknown; gates B3.
- **K6 (screener filter fields)** — determines whether the lite fetch is viable;
  resolve at A3.
- **Next-16 non-standard build (K5)** — SWR compatibility unverified.
- nsepython/FX long-term maintenance cost is inherent to "Aggressive" scope —
  accepted, bounded by the registry's automatic yfinance fallback.

## 9. Core design rules (retained — CLAUDE.md points here)

These are the canonical, load-bearing rules from the original architecture doc.
Everything in §1–§8 must stay consistent with them.

### Rule 1 — Adapter pattern: the only way to add a data source
Each source implements `DataAdapter` (`engine/app/adapters/base.py`):
```python
async def get_company(ticker, market) -> CompanyIdentity
async def get_fundamentals(company, period, limit) -> List[NormalizedFundamentals]
async def get_filings(company, filing_types, limit) -> List[FilingReference]
```
The engine only ever calls this interface; raw API responses never cross the
adapter boundary. Adding a source (Binance, Finnhub, nsepython, FX) = new file(s)
in `adapters/`, registered in the provider registry (§4) — zero engine-core
changes.

### Rule 2 — Internal schema: market-aware from day one
Every security carries `market`, `exchange`, `currency` explicitly
(`engine/app/schema/company.py`) as enums; extending markets = adding enum values,
not reshaping models. All monetary values in `NormalizedFundamentals` are
denominated in the declared `currency`.

### Rule 3 — Caching: lazy, TTL-based, layered over live fetches
Flow: check cache → hit returns immediately → miss fetches live via adapter,
stores with TTL, returns. TTLs live in `engine/app/cache/ttl_config.py` (see §1
for confirmed values). This plan adds an **L1 in-process tier in front** of the
Postgres L2 (§3b) but keeps the same lazy read-through contract. AI analysis is
the most expensive artifact → cached hardest (7 days).

### Rule 4 — No business logic in clients
The web app (and future MCP server) are presentation/transport only. Any rule,
calculation, or decision that touches data belongs in the engine. §1 bottleneck 1
and §3c batch endpoints exist partly to *restore* this rule where screener/compare
fan-out leaked into the client.

## Sources (2026 free-tier research)

- Neon free tier (0.5 GB, 100 CU-h/mo, 5 GB egress, hard suspend): neon.com/pricing, neon.com/docs/introduction/plans
- Supabase free tier (0.5 GB DB, auth 50 K MAU, 7-day idle pause): supabase.com/pricing
- Upstash Redis free (500 K cmds/mo, 256 MB): upstash.com/docs/redis/overall/pricing
- Cloudflare R2 free (10 GB, zero egress, 1 M/10 M ops): developers.cloudflare.com/r2/pricing
- Finnhub (60/min REST real-time US, WS 50 symbols free): finnhub.io/docs/api/websocket-trades
- Twelve Data (800/day, 4-h delay free) / Alpha Vantage (25/day) / Polygon (no free tier): provider docs, 2026 comparisons
- Binance/Coinbase/Kraken public market-data WS/REST (free, no key): exchange API docs
- India: jugaad-data & nsepython (NSE JSON scrape): github.com/jugaad-py/jugaad-data, pypi.org/project/nsepython
- Stooq bulk historical OHLC (free, decades of daily): stooq.com/db/h
- yfinance `.info` vs `fast_info` (fast_info no longer faster); `yf.download(threads=True)` for bulk: pypi.org/project/yfinance
- OpenBB provider abstraction + priority-list fallback: openbb.co/blog/exploring-the-architecture-behind-the-openbb-platform
- Ghostfolio (Redis market-data cache + scheduled fetch, in-memory fallback, separate Postgres user DB): github.com/ghostfolio/ghostfolio, deepwiki.com/ghostfolio/ghostfolio
- SWR stale-while-revalidate + preload prefetch-on-hover: swr.vercel.app
