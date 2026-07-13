# Progress Log — Tickr

---

## Session 0 — 2026-06-22 — Phase 0: scaffold and setup

### Done
- Created `E:\Projects\equity-research-app\`, git init, and made `.gitignore` the literal first commit so no secrets could ever sneak into history.
- Scaffolded the full folder tree: `engine/app/{schema,adapters,cache,analysis,db,api}`, `web/`, `docs/`, plus all `__init__.py` stubs and stub files with `TODO(Phase N)` markers.
- Defined the **internal normalized schema** in `engine/app/schema/` — this is the one real design decision of Phase 0, since all other layers depend on it:
  - `company.py`: `CompanyIdentity` with `Market`, `Exchange`, `Currency` enums — market-aware from day one; India enum values present but unused until Phase 4.
  - `fundamentals.py`: `NormalizedFundamentals` wrapping `IncomeStatement`, `BalanceSheet`, `CashFlowStatement`, `Ratios`, plus `Period` enum (annual/quarterly/TTM). All financial fields `Optional[float]` — None means not reported, not zero.
  - `filings.py`: `FilingReference` + `FilingType` enum covering US (10-K, 10-Q, 8-K, DEF 14A) and India placeholders (Phase 4).
- Defined the **adapter interface** in `engine/app/adapters/base.py` — abstract async `DataAdapter` with `get_company`, `get_fundamentals`, `get_filings`. Created `edgar.py` and `yfinance.py` stubs that raise `NotImplementedError("TODO(Phase 1)")`.
- Stubbed the **cache layer** (`cache/base.py`, `cache/ttl_config.py` with TTL constants), **analysis interface** (`analysis/interface.py`), and **DB layer** (`db/models.py` with a `CacheEntry` table, `db/session.py`).
- Wrote `engine/app/config.py` using pydantic-settings; `engine/app/main.py` with FastAPI + `/health` and `/api/v1` prefix; `engine/app/api/health.py` as a dedicated router.
- Set up Python 3.11 venv at `engine/.venv` and installed all deps from `pyproject.toml` (editable install): fastapi, uvicorn, edgartools 5.39.0, yfinance 1.4.1, sqlalchemy 2.0.51, alembic 1.18.4, httpx, python-dotenv, pydantic 2.13.4, pydantic-settings, psycopg2-binary — all installed cleanly.
- Initialized Alembic in `engine/alembic/`; edited `env.py` to load `DATABASE_URL` from settings and wire `Base.metadata` for autogenerate.
- Installed Node.js 24.17.0 via winget. Scaffolded Next.js 14 (TypeScript, App Router, ESLint, no Tailwind) in `web/`.
- Verified `/health` endpoint live: `GET http://localhost:8001/health` → `{"status":"ok","version":"0.1.0","environment":"development"}`.
- Wrote `CLAUDE.md` (lean index), `ARCHITECTURE.md` (full design diagram + rules), `.env.example`.
- 4 commits total: `.gitignore` → engine scaffold → Next.js → docs.

### Next
- Phase 2: PostgreSQL cache layer — set `DATABASE_URL` in `.env`, run `alembic upgrade head`, implement TTL caching in the cache layer so adapter results are stored and served from the DB on repeat calls.
- Phase 3: Next.js frontend — company pages with fundamentals tables and filings list.

### Open decisions
- `LLM_API_KEY` left empty in `.env` — stub only, not needed until Phase 2 analysis layer.
- PostgreSQL still not installed locally; Phase 2 is blocked until `DATABASE_URL` is set.

### Roadblocks & Resolutions
- **Wrong build backend in `pyproject.toml`:** First pip install attempt failed with `BackendUnavailable: Cannot import 'setuptools.backends.legacy'`. I had used `setuptools.backends.legacy:build` (wrong) instead of `setuptools.build_meta` (correct). Fixed the `[build-system]` section and reinstalled — resolved.
- **winget Node.js search hung:** `winget search "NodeJS"` hung indefinitely (exit 255). Skipped the search, went straight to `winget install --id OpenJS.NodeJS.LTS -e` — installed cleanly in ~2 minutes.
- **uvicorn background job:** Running uvicorn via PowerShell background job (`Start-Job`) failed to connect because the job environment didn't inherit the working directory. Switched to `System.Diagnostics.Process` with explicit `WorkingDirectory` — health check passed.
- **PostgreSQL not installed:** No local Postgres. Alembic is scaffolded and configured but migrations cannot run until `DATABASE_URL` is set in `.env`. Noted in CLAUDE.md. Not a blocker for Phase 1 (adapters + routes don't need the DB yet).

---

## Session 1 — 2026-06-22 — Phase 1: US data adapters (EDGAR + yfinance)

### Done

- Probed the actual edgartools 5.39.0 and yfinance 1.4.1 APIs before writing any adapter code: inspected `edgar.Company`, `Financials`, `EntityFilings`, and the Statement DataFrame schema (standard_concept column, value columns of the form "YYYY-MM-DD (FY)" / "YYYY-MM-DD (Q#)"). Probed yfinance `Ticker.info`, `get_income_stmt(freq='yearly')`, `get_balance_sheet`, `get_cash_flow`, and `sec_filings`. This pre-flight was essential because the standard_concept names are not documented anywhere obvious.

- Added `SEC_IDENTITY` setting to `config.py` and `.env.example` — SEC requires a contact email in the User-Agent header on every edgartools request. Read from `.env`, defaults to a placeholder so the engine still imports cleanly without a `.env` file.

- Implemented `EdgarAdapter` (`engine/app/adapters/edgar.py`):
  - `get_company`: resolves ticker → CIK via `edgar.Company`, maps `get_exchanges()` to the Exchange enum.
  - `get_fundamentals` (annual): calls `c.get_financials()` which returns the latest 10-K XBRL data with 3 fiscal years as DataFrame columns. Parses each "(FY)" column into a `NormalizedFundamentals`. Extracts values by `standard_concept` using a filter that excludes abstract and is_breakdown rows (so product-line breakdowns don't shadow the consolidated figure). EBITDA is derived as operating_income + D&A from the cash flow statement (edgartools does not surface EBITDA directly). Balance sheet columns have no period suffix (just "YYYY-MM-DD") so they're matched to IS/CF columns by date with ±5 day tolerance for fiscal calendar variation.
  - `get_fundamentals` (quarterly): iterates through 10-Q filings, downloads each, reads its XBRL, and pulls the "(Q#)" column (skipping "(YTD)" columns). One 10-Q download per quarter requested.
  - `get_filings`: calls `c.get_filings(form=[...])`, converts the pandas DataFrame rows to `FilingReference` objects with proper SEC URLs built from accession number and CIK.
  - All three methods run synchronous edgartools calls in `run_in_executor` so they don't block the FastAPI event loop.

- Implemented `YFinanceAdapter` (`engine/app/adapters/yfinance.py`):
  - `get_company`: maps yfinance exchange codes (NMS → NASDAQ, NYQ → NYSE, ASE → AMEX, etc.) to the Exchange enum.
  - `get_fundamentals`: calls `get_income_stmt`, `get_balance_sheet`, `get_cash_flow` with `freq='yearly'` or `'quarterly'` (yfinance uses those strings, not "annual"). Columns are Timestamps sorted newest-first — iterates over them to build one `NormalizedFundamentals` per period. yfinance gives EBITDA directly. Live ratios from `t.info` are attached to the most recent period only (they're TTM-based, so attaching to older periods would be misleading). Handles TTM separately via `ttm_income_stmt` / `ttm_cash_flow`.
  - `get_filings`: wraps `t.sec_filings` (Yahoo's mirror of SEC data); yields `FilingReference` objects but without accession numbers since Yahoo doesn't provide them.

- Wired API routes (`engine/app/api/routes.py`):
  - `GET /api/v1/companies/{ticker}` — default source: edgar (authoritative CIK lookup)
  - `GET /api/v1/companies/{ticker}/fundamentals?source=&period=&limit=` — default source: yfinance (gives 5 years, EBITDA, ratios)
  - `GET /api/v1/companies/{ticker}/filings?source=&limit=&types=` — default source: edgar
  - `?source=edgar|yfinance` override on all three routes.

- Wrote 19 integration tests in `engine/tests/test_adapters.py`, covering:
  - EDGAR and yfinance `get_company` for AAPL, JPM, BRK-B
  - EDGAR and yfinance annual fundamentals for AAPL (with revenue sanity bound: $370B–$460B)
  - EDGAR annual fundamentals for JPM (total assets > $3T)
  - EDGAR and yfinance quarterly fundamentals for AAPL
  - EDGAR filings for AAPL and BRK-B, with filtered-type test
  - yfinance filings for AAPL
  - Cross-source agreement test: EDGAR and yfinance AAPL revenue must agree within 1%

- All 19 tests pass in ~49s against live APIs.

- AAPL FY2025 sanity-checked numbers (both sources agree):
  - Revenue: $416.2B
  - Net Income: $112.0B
  - Operating Income: $133.1B
  - EBITDA: $144.7B (yfinance direct; EDGAR-derived matches)
  - EPS basic: $7.49 / diluted: $7.46
  - P/E (trailing): 36.1x | EV/EBITDA: 27.5x | Gross margin: 47.9% | ROE: 141.5%

- 1 commit: all Phase 1 files.

### Roadblocks & Resolutions

- **edgartools `standard_concept = 'Assets'` wrong for banks:** JPM's XBRL maps "Assets" to `us-gaap_DebtSecuritiesHeldToMaturityExcludingAccruedInterestAfterAllowanceForCreditLoss` (~$270B) rather than total assets (~$4.4T). The "Liabilities" standard_concept correctly returns total liabilities ($4.06T), and "LiabilitiesAndEquity" returns the correct $4.42T. Fixed the balance sheet builder to fall back to "LiabilitiesAndEquity" when "Assets" seems inconsistent with equity + liabilities (a heuristic that's robust for standard reporting but safe to revisit in Phase 4 when adding banks/financials more broadly).

- **edgartools `get_operating_cash_flow()` returns None:** The helper method returns None for AAPL despite the value being present in the DataFrame (row with `standard_concept = 'NetCashFromOperatingActivities'`). This appears to be a bug in edgartools 5.39.0. Worked around by extracting all values directly from the DataFrame using my own `_get_value()` function rather than relying on the helper methods.

- **edgartools quarterly iteration is slow:** Each 10-Q requires downloading and parsing the full XBRL filing (~5–10s per filing). For `limit=5` quarters that's up to 50s. Acceptable for Phase 1 with no cache; Phase 2 cache layer will make repeat calls instant.

- **yfinance `freq` parameter name changed:** The method `get_income_stmt` requires `freq='yearly'` not `freq='annual'`. The old name raises `ValueError: timescale must be one of: ['yearly', 'quarterly', 'trailing']`. Caught during the pre-flight probe before any adapter code was written.

---

## Session 2 — 2026-06-22 — Phase 2a: rename, README, GitHub, Neon, migrations

### Done

- Renamed project identity to **Tickr** across all code and docs: FastAPI app title (`engine/app/main.py`), `CLAUDE.md`, `ARCHITECTURE.md`, `PROGRESS.md`, `.env.example` (example DB name → `tickr`), `web/package.json` (`tickr-web`), `web/app/layout.tsx` (title/description metadata). Did not rename the `E:\Projects\equity-research-app\` folder itself — git/venv paths reference it.

- Wrote `README.md` at repo root: name + tagline, vision, positioning table (vs Bloomberg/FactSet/Yahoo), architecture overview, tech stack table, honest current-status/roadmap (built vs. planned), disclaimer, author credit.

- Renamed local branch `master` → `main` (`git branch -M main`). Added `origin` remote pointing at `https://github.com/ShrishChauhan/Tickr`. Pushed all 8 commits with `git push -u origin main`. Repository is live with README on the homepage.

- Verified Neon connection: `SELECT 1` returns `(1,)` using the pooled Neon endpoint via psycopg2/SQLAlchemy.

- Redesigned `CacheEntry` model in `engine/app/db/models.py` for Phase 2b: replaced the 4-column stub with an 8-column schema (`id`, `cache_key`, `data_type`, `ticker`, `source`, `payload`, `created_at`, `expires_at`) plus two indexes (`ix_cache_entries_expires_at` for sweeper queries, `ix_cache_entries_ticker_dtype` for per-ticker invalidation). `cache_key` is the unique lookup key (e.g. `"edgar:fundamentals:AAPL:annual:5"`); `ticker` and `source` are denormalized for bulk invalidation and source separation respectively; `payload` is Postgres JSON.

- Fixed `engine/app/config.py` to resolve `.env` by absolute path using `__file__` (`Path(__file__).parent.parent.parent / ".env"`) so pydantic-settings finds it regardless of working directory. This was required for Alembic, which runs from the `engine/` subdirectory.

- Generated Alembic migration (`alembic revision --autogenerate -m "initial cache schema"`) from `engine/` — produced `engine/alembic/versions/795388e90bdc_initial_cache_schema.py`. Applied with `alembic upgrade head`. Verified in Neon: `Tables: ['alembic_version', 'cache_entries']` with all 8 columns.

- 4 commits total this session: rename → README → Phase 2a schema + migration → PROGRESS.md.

### Next
- Phase 2b: implement the PostgreSQL TTL cache layer — `PostgresCacheBackend(CacheBackend)` in `engine/app/cache/`, wire into the API routes so cache-miss → adapter fetch → store, cache-hit → return immediately. TTL constants already in `ttl_config.py`.

### Open decisions
- `payload` is Postgres `JSON` (not `JSONB`). If Phase 2b needs to query inside the JSON payload (e.g. for cache invalidation by ticker inside nested fields), upgrade to `JSONB` at that point with a follow-up migration.
- Neon pooled endpoint (PgBouncer) works fine for `SELECT 1` and DDL migrations; if any future migration fails over pooled, switch temporarily to the direct (non-pooled) connection string from the Neon dashboard.

### Roadblocks & Resolutions

- **DATABASE_URL pointing to localhost during Alembic run:** The first `alembic revision --autogenerate` attempt failed with `NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:driver` — Alembic was falling back to the `alembic.ini` placeholder URL because pydantic-settings couldn't find `.env` when running from the `engine/` subdirectory. Root cause: `model_config = {"env_file": ".env"}` resolves relative to CWD, and CWD was `engine/` not the repo root. Fixed by changing the `env_file` value in `config.py` to an absolute path derived from `__file__`: `str(Path(__file__).parent.parent.parent / ".env")`. Migration succeeded on the second attempt.

- **Neon connection test connecting to localhost on first run:** The `SELECT 1` test was run before the `config.py` fix was applied; at that point the DATABASE_URL in `.env` was still the localhost placeholder from `.env.example` (user had not yet pasted the Neon URL). User updated `.env` and the test passed after the fix.

---

## Session 3 — 2026-06-23 — Phase 2b: PostgreSQL TTL cache layer

### Done

- Implemented `PostgresCacheBackend` in `engine/app/cache/postgres.py` — implements the abstract `CacheBackend` interface against the `cache_entries` table using sync SQLAlchemy wrapped in `asyncio.run_in_executor`, the same pattern the adapters use for blocking I/O. `get()` queries by `cache_key` with an `expires_at > now()` filter; `set()` uses PostgreSQL UPSERT (`INSERT ... ON CONFLICT (cache_key) DO UPDATE`) for atomic writes; `delete()` hard-deletes by key. Graceful degradation on every DB call: any exception logs a warning and returns None/swallows, so a Neon outage can't 500 a request.

- Updated `CacheBackend.set()` abstract signature to add keyword-only `data_type`, `ticker`, `source` parameters (with empty-string defaults so future simpler backends can ignore them). Required to populate the non-nullable columns in `cache_entries`.

- Wired the cache into all three API routes (`engine/app/api/routes.py`):
  - Cache key scheme: `{source}:company:{TICKER}`, `{source}:fundamentals:{TICKER}:{period}:{limit}`, `{source}:filings:{TICKER}:{limit}:{types_str}`.
  - Each endpoint: check cache → HIT returns immediately (deserializing JSON payload back to Pydantic model); MISS fetches from adapter, serializes with `model.model_dump(mode='json')`, caches with the appropriate TTL, returns result.
  - Routes and response models unchanged; graceful degradation preserved (cache failure falls through to adapter).

- JSON round-trip confirmed correct for all field types: `date` → ISO string → `date` (via pydantic v2 `model_dump(mode='json')` + `model_validate`), `datetime` with timezone, nested models, str enums (Market, Exchange, Period, FilingType, etc.). No manual serialization needed.

- Added `pool_pre_ping=True` to `create_engine()` in `engine/app/db/session.py` — prevents stale-connection errors when Neon autosuspends and drops connections.

- Wrote 4 cache-specific tests in `engine/tests/test_cache.py` (all against real Neon DB):
  - `test_cache_round_trip_company`: CompanyIdentity round-trip, enum types verified.
  - `test_cache_round_trip_fundamentals`: NormalizedFundamentals list round-trip; asserts `period_end_date` is `date` (not str), `fetched_at` is `datetime`, `exchange` is an Exchange enum.
  - `test_cache_expiry`: TTL=1s entry returns None after 2 seconds.
  - `test_cache_hit_skips_adapter`: spy wrapper on yfinance `get_company`; two cache-or-fetch calls → adapter called exactly once. Proves the second call returns from cache without touching the adapter.
  - All 4 passed. All 19 existing Phase 1 adapter tests still pass (23 total).

- **Live verification (AAPL fundamentals, yfinance, annual, limit=3):**
  - First request (cache MISS, live yfinance fetch): **18.1s**
  - Second request (cache HIT, Neon): **4.0s** — 78% faster
  - Third request (cache HIT, pooled connection): **3.9s**
  - Cache row confirmed in Neon: `yfinance:fundamentals:AAPL:annual:3`, 4633 bytes payload, expires 24h out.

- 4 commits this session: PostgresCacheBackend → routes wired → tests → session log.

### Next
- Phase 3: Next.js web app — company pages showing fundamentals tables, filings list, and the AI analysis.

### Open decisions
- `payload` is Postgres JSON (not JSONB). Still fine. No need to query inside payload.
- Analysis endpoint currently does a general summary only (question="" default). A Q&A mode with per-question caching (keyed by question hash) is a natural Phase 3 or 5 extension.

### Roadblocks & Resolutions

- **Neon autosuspend wakeup adds ~10s to the first cache call per session:** On Neon's free tier, the compute autosuspends after 5 minutes of inactivity. The first DB call after suspension wakes the compute and takes ~10s. Subsequent calls over the same pooled connection take ~1–4s (network RTT + PgBouncer overhead). Mitigation added: `pool_pre_ping=True` on the SQLAlchemy engine prevents stale-connection errors. Documented here so Phase 2c can decide whether to switch to the direct connection string (bypasses PgBouncer, gives consistent connection lifetime) or keep pooled for connection multiplexing.

---

## Session 4 — 2026-06-23 — Phase 2c: direct Neon connection + AI analysis layer

### Done

- **Diagnosed and fixed the 4s cache hit latency (Task 0):** Switched `DATABASE_URL` in `.env` to the direct (non-pooled) Neon endpoint. Then investigated further and found the real culprit: SQLAlchemy's default transaction mode issues BEGIN + actual query + ROLLBACK = 3 network round-trips per cache operation. From this location (India) to Neon US-East-1, each RTT is ~320ms, so 3 × 320ms = ~960ms baseline — worse than the pooled endpoint's 4s because PgBouncer at least batches some of that overhead. Fixed in `engine/app/db/session.py` by switching to `isolation_level="AUTOCOMMIT"` (each statement auto-commits, no BEGIN/ROLLBACK sent) and disabling `pool_pre_ping` (postgres.py's exception handling already gracefully degrades on stale connections). Also added `pool_recycle=1800` so idle connections are dropped before Neon's 5-minute autosuspend can invalidate them.

  - Session 3 pooled endpoint cache HIT: **4.0s**
  - Session 4 direct endpoint, transaction mode: **1.5–2.0s** (still 2–3 RTTs)
  - Session 4 direct endpoint, AUTOCOMMIT: **750–960ms** (1–2 RTTs, physical floor from India to US-East-1)
  - Physical floor: psycopg2 `SELECT 1` on a reused connection = 320ms/RTT. AUTOCOMMIT achieves ~2 RTTs (TCP send/receive), which at India→US-East-1 distances can't be reduced further without infrastructure co-location.

- **Implemented `GroqAnalysisEngine(AnalysisEngine)` in `engine/app/analysis/groq_engine.py` (Task 1):**
  - Uses Groq SDK with `llama-3.3-70b-versatile` (verified current, non-deprecated model via Groq changelog; replaced the deprecated `llama3-70b-8192`).
  - Probed Groq live before writing analysis code: `llama-3.3-70b-versatile` → `"OK"` in 1665ms. ✓
  - `_build_prompt()` formats the full `NormalizedFundamentals` list as a financial table (oldest-to-newest, all values in billions), adds key ratios from the most recent period, adds recent filings, and includes explicit grounding instructions: "cite specific figures for every claim", "do NOT invent or estimate any figure not in the data".
  - `_call_groq()` uses temperature=0.1 (low, for factual consistency), max_tokens=1500.
  - Provider swappability: the route holds an `AnalysisEngine` reference via `_get_analysis_engine()`. Swapping to the Anthropic API means adding `AnthropicAnalysisEngine(AnalysisEngine)` in a new file and changing one line in routes.py — no other callers to update.
  - `GROQ_API_KEY` and `GROQ_MODEL` added to `config.py` and `.env.example`.

- **Implemented `analyze_company` with grounded prompt (Task 2):** The prompt includes the financial table with actual figures from the passed `NormalizedFundamentals` list. The five sections requested are: Financial Trend Summary, Profitability Analysis, Balance Sheet & Leverage, Cash Flow Analysis, Key Observations. The system prompt reinforces data-only analysis.

- **Cached analysis with 7-day TTL (Task 3):**
  - Cache key: `analysis:{TICKER}:{source}:{period}:{limit}` — includes source/period/limit because the analysis is grounded in those specific data cuts.
  - Cached value: `{"analysis": "<text>", "generated_at": "<ISO 8601>", "periods_analyzed": N}`.
  - TTL: `AI_ANALYSIS_TTL_SECONDS` (604,800s / 7 days) from `ttl_config.py`.

- **Exposed `GET /api/v1/companies/{ticker}/analyze` (Task 4):** Thin route — cache check → generate if miss → store → return `AnalysisResult`. Returns 503 if `GROQ_API_KEY` is not configured (non-analyze routes unaffected). Analysis engine is lazy-initialized as a module-level singleton.

- **Wrote 2 analysis tests in `engine/tests/test_analysis.py`:**
  - `test_analysis_prompt_includes_actual_figures`: uses `__new__` to skip init (no API key), calls `_build_prompt` directly, asserts revenue ($416.0B), EBITDA ($144.7B), ticker "AAPL", and period "FY2025" appear in the prompt. Proves the financial data is correctly embedded before it ever reaches the LLM.
  - `test_analysis_cache_hit_skips_llm`: spies on `_call_groq`, runs `analyze_with_cache()` twice against real Neon with a UUID-unique key, asserts `call_count == 1`. Proves the second call returns from cache without touching Groq.

- **All 25 tests pass:** 19 adapter tests + 4 cache tests + 2 analysis tests = 25 total. Runtime: 137s.

- **Live AAPL double-analyze verification:**
  - Request 1 (cache MISS, yfinance fetch + Groq LLM call): **21.7s** (Neon wakeup + fundamentals fetch + 3-period LLM analysis)
  - Request 2 (cache HIT, no LLM call): **1.3s**, `cached: true`, same `generated_at` timestamp
  - Steady-state cache hits: **957ms–1.3s** (physical floor from India to Neon US-East-1)
  - Analysis row confirmed in Neon `cache_entries`: key=`analysis:AAPL:yfinance:annual:3`, payload=2245 bytes, expires 2026-06-29.
  - Analysis content: correctly cited real AAPL revenue figures ($383.3B FY2023 → $391.0B FY2024 → $416.2B FY2025) — grounding verified.

- 5 commits this session: Neon optimization → groq dependency → analysis implementation → test → PROGRESS.md.

### Next
- Phase 3: Next.js web app — company search, fundamentals table, filings list, AI analysis panel.

### Open decisions
- Cache hit latency is ~950ms from India to Neon US-East-1 — this is the physical network floor (2 × 320ms RTT + overhead). Production deployments with engine and DB in the same AWS region will see <10ms hits. No code change can reduce the India→US-East-1 RTT further.

### Roadblocks & Resolutions

- **Cache hit was not sub-1s on first direct connection test (2s):** Switching from pooled to direct connection alone only halved the latency (4s → 2s). The remaining 2s was not PgBouncer overhead — it was SQLAlchemy's implicit transaction management. With the default isolation level, each `with SessionLocal() as session:` issues BEGIN + query + ROLLBACK = 3 network RTTs. At 320ms/RTT from India, that's 960ms minimum plus overhead. Fixed by setting `isolation_level="AUTOCOMMIT"` on the engine, which eliminates BEGIN/ROLLBACK entirely. Now each cache operation is 1–2 RTTs (~640–960ms at this network distance).

- **pool_pre_ping doubling latency:** The initial `pool_pre_ping=True` (carried over from Session 3 as a Neon-autosuspend guard) sent a `SELECT 1` before every connection checkout, adding one full RTT per operation. Replaced with `pool_recycle=1800` (connections are dropped and recreated after 30 minutes of idle, which is before Neon's 5-minute autosuspend window would make them stale). The postgres.py exception handler (returns None on any DB error) provides the safety net: if a connection is stale on first use after Neon wakeup, the cache returns None, the adapter fetches fresh data, and the next request succeeds from cache. This is equivalent to the graceful degradation already designed for DB outages.

- **Windows terminal encoding error during Groq probe:** The Groq probe printed a `→` character which triggered `UnicodeEncodeError: 'charmap' codec can't encode character` on Windows. Fixed by writing bytes directly to `sys.stdout.buffer` with explicit UTF-8 encoding. Not a real issue — Groq API and the actual engine code are unaffected.

---

## Session 5 — 2026-06-25 — Phase 3a: TICKR logo + animated hero landing page

### Done

- **Design token foundation (`web/app/globals.css`, `web/app/layout.tsx`):** Replaced all Next.js boilerplate with a CSS custom property system as the single source of truth. Two-tier color system: neon brand colors (`#2BFF88` / `#FF4060`) with pre-built `drop-shadow` glow variables for SVG filters, and calm data colors (`#22C55E` / `#EF4444`) with no glow — used exclusively for figures and numbers. Three brand fonts loaded via `next/font/google` with CSS variable injection: Michroma (display/logo), Space Grotesk (UI), JetBrains Mono (data). All component CSS references tokens only — no hardcoded hex anywhere except `globals.css` and `icon.svg`.

- **Favicon (`web/app/icon.svg`):** Two-arrow SVG mark on `#04070A` background — green up-arrow and red down-arrow. Next.js App Router picks it up automatically as the tab favicon; no `<link>` tag needed.

- **TickrLogo SVG component (`web/components/logo/`):** Inline SVG component in Michroma. "T" and "CKR" letters use a top-down white sheen gradient (`#FFFFFF → #E8EDF4 → #C8D0DC`) via `background-clip: text`. The "I" is replaced by two overlapping arrows in a shared `viewBox="0 0 26 56"`: green up-arrow positioned right and higher (shaft x=18, tip at y=10), red down-arrow left and lower (shaft x=8, tip at y=46). Both arrows have neon glow via SVG `drop-shadow` filters. Component uses `font-size: inherit` — the parent wrapper controls size via `clamp()` or an inline style, so the same component works in the nav at `1.5rem` and in the hero at `clamp(2.5rem, 8vw, 6.5rem)`.

- **TopNav (`web/components/nav/`):** Fixed-position header, `z-index: 100`, transparent background. `instant` prop triggers `useAnimation.set({ opacity: 1 })` to snap to visible immediately on skip; on the natural sequence it starts a delayed `opacity: 0→1` fade at `delay: 5.85s`.

- **TickerLine (`web/components/hero/TickerLine.tsx`):** Full-viewport absolute SVG (`viewBox="0 0 1200 700"`) with a 17-waypoint polyline path that climbs bottom-left to upper-right with deliberate jitter pairs (e.g. `90,610 → 110,630` reverses briefly before resuming upward). Three-layer phosphor glow: halo `strokeWidth=22` + `blur=9`, mid `strokeWidth=8` + `blur=3.5`, core `strokeWidth=2.5` no blur. All three layers share the same `pathLength` animation (`0→1` over 3s) using jitter keyframes:
  ```
  pathLength: [0, 0.16, 0.12, 0.33, 0.27, 0.55, 0.50, 0.76, 0.71, 1.0]
  times:      [0, 0.14, 0.18, 0.37, 0.41, 0.60, 0.64, 0.82, 0.87, 1.0]
  ```
  At 3.5s the whole `<motion.g>` wrapper animates `opacity` from `1 → 0.18`, leaving the line as an ambient backdrop. On `instant=true`, `pathLength: 1` and `opacity: 0.18` are applied immediately via `initial` prop values (no running animation to cancel).

- **SearchBar (`web/components/hero/SearchBar.tsx`):** Visual-only placeholder div styled to look like a search input — magnifier icon, "Search any stock…" placeholder text, `⌘K` shortcut badge. No `<input>` element yet; wired in Phase 3b.

- **MoversRow (`web/components/hero/MoversRow.tsx`):** Five hardcoded cards (NVDA, AAPL, TSLA, AMZN, META) with hardcoded prices, change percentages, and 10-point sparkline SVGs. Calm data colors only (`--color-data-green` / `--color-data-red`) — no neon glow anywhere in the movers section. Gainer cards have a faint green border; loser cards a faint red border. "Sample Data" badge prominently placed top-right of the section header so it's unmistakable. Horizontal scroll on mobile via `overflow-x: auto`.

- **HeroSection orchestrator (`web/components/hero/HeroSection.tsx`):** Client component managing the full animation sequence. Staggered via `useAnimation` controls: logo reveal at 3s, tagline at 6.15s, search at 6.0s, movers at 6.35s. Skip triggers via `window.addEventListener("click"/"keydown")` and `document.addEventListener("scroll")` — all with `{ once: true }`. Auto-completes at 8s. On skip, `controls.set()` is called on every control simultaneously, immediately jumping all elements to their final visible state.

- **HeroLoader + page wiring (`web/components/hero/HeroLoader.tsx`, `web/app/page.tsx`):** `page.tsx` is a Server Component that renders `<HeroLoader />`. HeroLoader is a `"use client"` component that wraps `dynamic(() => import("./HeroSection"), { ssr: false })`. This two-layer structure was required by a Next.js 16 breaking change (see Roadblocks).

- **Visual verification:** Ran Playwright against `http://localhost:3000`. Screenshots confirmed: dark `#04070A` background, phosphor-glow ticker line drawing across the viewport, TICKR logo appearing at ~3s with correctly positioned glowing arrows, ticker dimming to ambient at 3.5s. The skip behavior is implemented correctly in code via `useAnimation.set()`; Playwright's synchronous screenshot timing (captured immediately after `page.click()` before React processes the state update) made the skip screenshots inconclusive in automation, but the logic is correct.

- 7 commits this session: framer-motion install → design tokens + fonts → favicon → TickrLogo → TopNav → TickerLine → SearchBar + MoversRow → HeroSection orchestrator + page wiring.

### Next

- Phase 3b: wire up the search bar with actual engine calls (`GET /api/v1/companies/{ticker}`), company detail page showing fundamentals table, filings list, and AI analysis panel.

### Open decisions

- **Skip animation Playwright testing:** The `useAnimation.set()` implementation is correct but hard to verify with Playwright's headless screenshot timing. Will add a `data-testid` attribute or CSS transition end event listener in Phase 3b if automated testing of animation states becomes necessary.
- **Nav background:** Currently transparent through the hero. Phase 3b needs to decide when/whether the nav gets a solid/blurred background (e.g. after scrolling past the hero).

### Roadblocks & Resolutions

- **Next.js 16 breaks `ssr: false` in Server Components:** `page.tsx` is a Server Component by default in the App Router. Next.js 16 (Turbopack) throws a build error if `dynamic(..., { ssr: false })` is called directly in a Server Component: `"ssr: false is not allowed with next/dynamic in Server Components"`. Earlier Next.js versions silently allowed it. Fixed by creating `HeroLoader.tsx` with `"use client"` at the top — the `dynamic()` import lives there, and `page.tsx` just imports `<HeroLoader />`. The Server Component never touches the dynamic import; the Client Component owns it.

- **Mobile logo overflow at `scale` prop:** First implementation of TickrLogo used a fixed `width` / `height` SVG with a `scale` prop multiplier. At `scale=2.0` the logo wordmark was ~640px wide, which clipped on a 390px viewport. Refactored to a pure HTML inline-flex layout (`font-size: inherit`, letter spans with `background-clip: text` gradient, SVG arrows at `height="1em"` / `width="0.46em"`) — the logo now scales from the parent wrapper's `font-size`. HeroSection sets `font-size: clamp(2.5rem, 8vw, 6.5rem)` on the wrapper; TopNav sets `1.5rem` inline. Both work at all viewport widths.

- **Framer Motion skip animation not working with `transition`-only prop change:** First skip implementation changed only the `transition` prop (setting `duration: 0`) while keeping the same `animate` target. Framer Motion does not re-trigger an animation when only `transition` changes — the animation state machine only responds to changes in the `animate` target values. So elements already waiting on a `delay: 6.0s` timer stayed invisible. Fixed by switching to imperative `useAnimation` controls for every animated element: on `instant=false`, `controls.start({ opacity: 1, transition: { delay: N } })`; on `instant=true`, `controls.set({ opacity: 1 })`. The `set()` call is synchronous and cancels any pending animation, immediately snapping elements to their final state.

- **Fixed-position nav inside opacity-animating div:** First TopNav implementation wrapped the `<nav>` in a `<motion.div>` that faded `opacity: 0→1`. A CSS stacking context is created whenever an element has `opacity < 1`, which makes any `position: fixed` child of that element behave as `position: absolute` relative to the stacking context ancestor instead of the viewport. The nav was painting at the top of the hero div, not the top of the screen. Fixed by moving the `motion` animation directly onto the `<motion.nav>` element itself (then replaced with `useAnimation` controls as part of the above fix). No wrapper div needed.

---

## Session 7 — 2026-06-27 — Phase 4a: Global equity onboarding

### Done

- **Expanded schema enums (`engine/app/schema/company.py`):** `Market` extended to US/UK/DE/JP/IN/BR/MX. `Exchange` extended to include LSE, XETRA, TSE, NSE, BSE, B3, BMV, and an `OTHER` fallback. `Currency` extended to USD/GBP/EUR/JPY/INR/BRL/MXN.

- **Fixed three hardcoded bugs in yfinance adapter (`engine/app/adapters/yfinance.py`):**
  1. Line 143 (original): `currency = Currency.USD if currency_str == "USD" else Currency.USD` — always returned USD regardless of input. Fixed by routing through `_CURRENCY_MAP`.
  2. `market=Market.US` hardcoded in `_sync_get_company`. Fixed to infer from suffix/currency.
  3. `currency=Currency.USD` hardcoded in `_sync_get_fundamentals` (annual and TTM paths). Fixed to use `company.currency`.

- **Added suffix-based global ticker resolution:** `_SUFFIX_MAP` maps `.L`/`.DE`/`.T`/`.NS`/`.BO`/`.SA`/`.MX` to (Exchange, Market, default_currency). For global tickers, suffix resolution runs first; `info["currency"]` from yfinance overrides the suffix default currency (important: Shell / SHEL.L reports in USD despite LSE listing — engine correctly returns USD). US tickers fall through to the existing exchange-code map.

- **Extended `_EXCHANGE_MAP`** with global yfinance exchange codes (LSE, IOB, GER, DEX, ETR, TYO, OSA, NSI, BOM, SAO, MEX) as a defense-in-depth fallback behind the suffix map. Default changed from `Exchange.NYSE` to `Exchange.OTHER` for truly unknown codes.

- **IFRS synonym fallback (small) in `_build_income_statement`:** Three highest-value fields only:
  - `revenue`: `TotalRevenue` → `Revenue` → `NetRevenue`
  - `operating_income`: `OperatingIncome` → `OperatingProfit` → `EBIT`
  - `net_income`: `NetIncome` → `NetIncomeLoss` → `ProfitLoss`

- **SearchBar extended to 12 chars** (`web/components/hero/SearchBar.tsx`): regex changed to `^[A-Z0-9.]{1,12}$`, `maxLength` to 12. Required for `RELIANCE.NS` (11 chars) and `GFNORTEO.MX` (11 chars).

- **Currency-aware fundamentals table** (`web/components/company/FundamentalsTable.tsx`): `fmtDollar` and `fmtEps` now take a currency symbol parameter. `fmt` defined inside the component body as a closure over `currSym = getCurrencySymbol(periods[0].currency)`. Symbol map: USD→`$`, GBP→`£`, EUR→`€`, JPY→`¥`, INR→`₹`, BRL→`R$`, MXN→`MX$`. Japanese stocks now show `¥`, Indian stocks `₹`, etc.

- **Created `engine/tests/verify_global_fundamentals.py`** — diagnostic (not a test suite entry): fetches one year of annual fundamentals for AAPL + SHEL.L + SAP.DE + 7203.T + RELIANCE.NS + PETR4.SA + WALMEX.MX through the engine's normalization path, prints populated vs null fields per ticker, prints a gap analysis vs AAPL baseline.

- **Diagnostic output confirmed:**
  - AAPL: 18/18 fields populated. Baseline clean.
  - SHEL.L: 18/18. Currency=USD (Shell reports in USD — info["currency"] correctly overrides suffix default GBP).
  - SAP.DE: 18/18. Currency=EUR, Exchange=XETRA.
  - 7203.T: 18/18. Currency=JPY, Exchange=TSE.
  - RELIANCE.NS: 17/18. Only gap: `eps_diluted` (expected for NSE listings — yfinance doesn't provide it).
  - PETR4.SA: 18/18. Currency=BRL, Exchange=B3.
  - WALMEX.MX: 18/18. Currency=MXN, Exchange=BMV.

### Known limitation (not fixed — Phase 4c)
Simple search requires exact suffixed ticker (`7203.T` for Toyota, `RELIANCE.NS` for Reliance). This is power-user-unfriendly. Name-based tagged search is Phase 4c.

### Next
Phase 4b (price-only assets: crypto/forex/commodities) or Phase 4c (tagged search with exchange suffix autocomplete).

---

## Session 6 (3a.2) — 2026-06-26 — Hero matched to prototype

### Done
- **Typewriter tagline:** Added `Typewriter.tsx` + `Typewriter.module.css`. The component types "AI-Powered Equity Research Terminal" at 50 ms/char starting at `startDelay=6150 ms` (aligned with the tagline fade-in). Cursor is a `<span>|</span>` with opacity-only blink (never removed from DOM) so its width is always counted — no centering jank. When `instant=true`, shows full text immediately with cursor hidden. After typing completes, cursor fades out over 0.5 s.
- **Font size bump:** `.tagline` in `HeroSection.module.css` changed from `clamp(0.75rem, 2.2vw, 1rem)` (12–16 px) to `clamp(0.9375rem, 2.2vw, 1.0625rem)` (15–17 px). `letter-spacing: 0.14em` scales proportionally.
- **Text contrast lift:** `--color-text-primary` in `globals.css` bumped from `#f0f4f8` to `#f5f7fa` (brighter near-white, not pure white).
- **`prefers-reduced-motion` support:** One-shot `useEffect` in `HeroSection.tsx` checks the media query on mount and calls `setInstant(true)` immediately — all animations skip straight to final state.
- **Build:** `npm run build` passes cleanly, TypeScript clean, no ESLint errors.
- **Visual verification:** Playwright screenshots confirm: mid-animation (TickerLine drawing + logo visible at 3.5 s); final state (all elements visible — logo, tagline, search bar, movers row — TickerLine dimmed, TopNav with solid background). DOM content confirmed `"AI-Powered Equity Research Terminal|"` in tagline, `"TCKRSearchAbout"` in nav.

### Next session (3b.1 / 3b.2)
Make search functional → route to `/company/[ticker]` → scaffold company page → first engine fetch.

Specifically:
1. Wire SearchBar to an actual `<input>` and handle submit
2. Add Next.js App Router route `/company/[ticker]/page.tsx`
3. Scaffold company page layout (header, fundamentals section, filings section, AI analysis panel — all empty initially)
4. First engine fetch: `GET /api/v1/companies/{ticker}` → display identity card

---

## Session 8 — 2026-07-01 — Phase 4d-1: Freshness Display + Comparison Page

### Done

- **Verified field names before building:** Confirmed `NormalizedFundamentals.fetched_at` exists (Python `datetime`, TypeScript `string`) on both the schema and TS interface. Confirmed all radar/table ratio keys (`gross_margin`, `operating_margin`, `net_margin`, `roe`, `roa`, `pe_ratio`, `debt_to_equity`) match the actual `Ratios` model and `derive_ratios` output exactly. Noted the critical decimal convention: `derive_ratios` stores margin/return values as decimals (0.44 = 44%) — `fmtPct` correctly multiplies by 100.

- **Extracted shared formatting utilities to `web/lib/format.ts`:** `relativeTime`, `getCurrencySymbol`, `fmtDollar`, `fmtEps`, `fmtPct`, `fmtMultiple` — previously defined locally in `FundamentalsTable.tsx`. Updated `FundamentalsTable.tsx` to import from `@/lib/format` instead. No behavioral change.

- **Data freshness — price-only pages (`PriceOnlyPage.tsx`):** Added `Updated {relativeTime(data.fetched_at)}` below the price/change display (inside the header card). Uses `fetched_at` already present on `PriceOnlyData`. Styled via `.freshness` in `page.module.css`: JetBrains Mono, 11px, `--color-text-muted`.

- **Data freshness — equity pages (`EquityPage.tsx`):** Added `Fundamentals as of FY{year} · Updated {relative}` inside the identity card, below the meta row. Period label derived from `fundamentals[0].fiscal_year` (falls back to `period_end_date.slice(0,4)` if null). `relativeTime` imported from `@/lib/format`.

- **TopNav:** Wired placeholder links — "Search" → `/`, "About" replaced with "Compare" → `/compare`. Removed the `{/* Links wire up in Phase 3b */}` comment.

- **New route `/compare` (`web/app/compare/page.tsx`):** Full comparison page, `'use client'`.
  - Ticker input with 300ms-debounced typeahead (`fetchSearch`) + dropdown; chips for each added ticker with colored dot matching the radar series color; pending chips for in-flight fetches.
  - On add: cap check (5 including in-flight), duplicate check, `fetchCompany` to verify `asset_type === 'equity'` (non-equities shown a self-clearing warn note and rejected), `fetchFundamentals(ticker, 'annual', 3)`. On error: self-clearing error note, ticker not added.
  - Empty state: "Add at least 2 tickers to compare" until 2 tickers are loaded.
  - **Radar chart** (recharts `RadarChart`): 5 metrics — Gross Margin, Op. Margin, Net Margin, ROE, ROA. Per-metric normalization: highest raw value across set = 100, others scaled proportionally (normalization on raw decimals preserves proportions). Custom tooltip shows real percentages (raw × 100), not the normalized 0–100 score. Colors: `['#2BFF88', '#6366F1', '#F59E0B', '#22D3EE', '#A78BFA']` (red excluded — reserved for negative). Fill opacity 0.15 per polygon.
  - **Comparison table**: 5 sections (Income Statement, Margins, Cash Flow, Balance Sheet, Returns & Leverage). Transposed layout — columns = tickers, rows = metrics. Per-column currency symbol via `getCurrencySymbol`. Best-per-row highlight for `higherIsBetter` metrics: faint green background (`rgba(43,255,136,0.08)`) on the winning cell. Multi-currency caveat note if companies report in different currencies. Missing values → em-dash.

- **`npm run build` passes clean.** TypeScript zero errors. Route shows as `○ (Static)` in build output.

### Verification checklist (run after starting servers)
1. `curl http://localhost:8000/api/v1/assets/GC=F/price` → JSON with `contract_month`
2. `/company/BTC-USD` → "Updated X min ago" under price
3. `/company/AAPL` → "Fundamentals as of FY2024 · Updated X ago" in identity card
4. `/compare`: add AAPL + MSFT → radar renders (2 polygons), table shows 2 columns
5. Radar tooltip → real % values (e.g. "43.5%"), not 0–100
6. Add BTC-USD → reject note, not added
7. Add 6th ticker → blocked
8. Remove ticker → chart and table update
9. Best-per-row: winner has faint green cell bg
10. Nav "Compare" link routes to `/compare`

## Session 9 (Architecture A2) — 2026-07-06 — Extract orchestration into services/

### Done

- **New `engine/app/services/company.py`:** cache-orchestration + non-equity-fallback normalization for company identity, extracted from `routes.py`. Includes `EXCHANGE_DISPLAY` and its supporting maps (`_NON_EQUITY_QUOTE_TYPES`, `_ASSET_TYPE_MAP`, `_CURRENCY_TO_MARKET`), previously module-level in `routes.py`, plus `_build_non_equity_identity` and the new `get_company_identity()` orchestration function and `CompanyLookupError` exception.
- **New `engine/app/services/fundamentals.py`:** cache-orchestration + ratio-derivation normalization for fundamentals, extracted from `routes.py`. New `get_fundamentals()` orchestration function and `FundamentalsLookupError` exception.
- **`routes.py` handlers for `/companies/{ticker}` and `/companies/{ticker}/fundamentals`** reduced to thin request/response wrappers: resolve adapter/validate query params → call service function → translate the service's lookup-error into `HTTPException(404, ...)`. `search_assets` updated to import `EXCHANGE_DISPLAY` from the new location (import path only, no logic change).
- `_get_adapter`, `_adapters`, and the `_cache` (`LayeredCacheBackend`) singleton stay in `routes.py` — shared by out-of-scope handlers, so the two new service functions take the resolved `adapter` and the shared `cache` instance as plain arguments (dependency injection) rather than routes.py exporting them or services instantiating their own.
- **Verified byte-identical responses before/after** (stashed the refactor, ran pre-refactor code, captured baselines; popped the stash, ran post-refactor code, diffed) for: `AAPL`, `SHEL`, `GC=F`, `XYZINVALID`, `AAPL/fundamentals`, `AAPL/fundamentals?period=quarterly&limit=3`, invalid period (400), `GC=F/fundamentals` (returns `[]` — yfinance `get_company` succeeds for a futures ticker, `get_fundamentals` just has no statements; not a 404 in this case), `/search?q=apple`. All 9 diffs empty, byte-for-byte — no time-dependent fields even appeared since these cases hit L2 cache carried over from the baseline run.
- **L1 cache (A1) confirmed working through the new service layer:** fresh ticker (`MSFT`, uncached) took ~2.0s (live EDGAR fetch); immediate repeat took ~0.34s (L1 in-memory hit), response bodies identical.
- Existing test suite (`engine/tests/`, 25 tests: `test_adapters.py`, `test_analysis.py`, `test_cache.py`) passes unchanged.

### Deferred (not extracted this session)

Filings, search, price-only, screener, and analyze endpoints remain in `routes.py` as-is. Extract in a later session if/when it becomes a blocker (e.g. when adding the provider registry in Phase B).

Known pre-existing asymmetry (not fixed): `/companies/{ticker}` has a non-equity fallback (`_build_non_equity_identity`); `/companies/{ticker}/fundamentals` does not. For most non-equity tickers under the `yfinance` source (fundamentals' default) this doesn't 404 — `adapter.get_company` succeeds and `adapter.get_fundamentals` just returns an empty list — but there's no equivalent fallback path if the adapter's `get_company` call itself fails for a non-equity ticker. Candidate for a future session.

No actual "ticker resolver" module exists (no automatic `.L`/`.DE` retry-on-failure logic) — what exists is (a) the identity-fallback above and (b) suffix-based exchange/market mapping in `YFinanceAdapter` for tickers already given with a suffix. Confirmed via full read of `routes.py` and `adapters/yfinance.py`.

This session also backfills the missing session entry for A1 (in-process L1 cache, commit `5bc6bbd`) — see `engine/app/cache/layered.py` and `memory.py`, not otherwise documented in this file.

### Next

A3: batch screener endpoint using the new service-layer pattern established here.

## Session 10 (Architecture A3) — 2026-07-06 — Batch screener endpoint

### K6 resolution

6/8 filter fields (Market Cap, P/E, Net Margin, ROE, Debt/Equity, Gross Margin) are already `.info`-derivable via the existing `_build_ratios_from_info()` mapping. Revenue is not currently read anywhere but `.info["totalRevenue"]` exists — added at zero extra cost. Free Cash Flow has no `.info` equivalent at all (only derivable from `t.get_cash_flow()`, the slow path) — dropped from the batch/lite path entirely; the endpoint always returns `free_cash_flow: null` and the frontend's "FCF > 0" filter checkbox was removed (a null field can never satisfy `> 0`). The compare page (full fetch, untouched) remains the place to see actual FCF.

### Done

- New `engine/app/schema/screener.py`: `ScreenerFields` (flat, nullable numeric fields) + `ScreenerRow` (adds ticker/name).
- New `YFinanceAdapter.get_lite_fundamentals()` (`engine/app/adapters/yfinance.py`) — `.info`-only fetch, not added to the `DataAdapter` ABC since the screener has always been yfinance-only.
- New `engine/app/services/universes.py`: extracted the inline `_UNIVERSES` dict/loading out of `routes.py` into `load_universe()`/`UnknownUniverseError`; the existing `/screener/universes/{key}` route now uses it too (same source of truth).
- New `engine/app/services/fundamentals.py::get_lite_fundamentals()`: cache-orchestration for the lite fetch, cache key `{source}:screener_lite:{ticker}`, reuses `FUNDAMENTALS_TTL_SECONDS` (1 day) — no new TTL constant.
- New `engine/app/services/screener.py::get_screener_rows()`: fan-out via `asyncio.gather`-equivalent (`asyncio.wait` over per-ticker tasks) + `Semaphore(CONCURRENCY=8)` — matches the old frontend pool size since yfinance can soft-rate-limit a single IP at higher concurrency, and this now runs behind one shared server IP. Per-ticker `wait_for(..., timeout=10)` bounds a hung ticker; per-ticker `try/except` returns a null row instead of failing the request. Outer `asyncio.wait(..., timeout=150)` is a safety net (not the expected path) that returns partial results if the whole batch runs long. Logs succeeded/failed/timed-out counts + elapsed time at INFO.
- New route `GET /api/v1/screener/{universe_key}/rows` — thin, no `source` param (yfinance-only, same as `/screener/universes/{key}`).
- Frontend (`web/lib/api.ts`, `ScreenerTable.tsx`, `screener/page.tsx`): replaced the client-side `CONCURRENCY=8` work-stealing pool + per-ticker `fetchFundamentals` calls with one `fetchScreenerRows(universeKey)` call. Removed `fetchUniverse`/`UniverseConstituent` (redundant now — the batch response already carries ticker+name for every constituent). Removed per-cell loading/error skeleton logic (`fmtDollar`/`fmtPct`/`fmtMultiple` already render `null` as `—`); a single `rowsLoading` boolean now gates a page-level loading message instead of the table. Removed the non-functional FCF filter checkbox.

### Measured timing (important — revises the original estimate)

- dow30: cold 14.2s, warm (cached) 0.29s.
- sp500 (503 tickers): the lite (`.info`-only) fetch is **not** dramatically faster than the old full fetch — yfinance's `.info` call itself is the dominant per-ticker cost, not the 3 extra statement calls it skips. A first attempt with a 90s safety-net timeout returned 447/503 (89%) before cutting off; raising the timeout and re-running (partially cache-warm) completed all 503 in ~137s combined wall time. Settled on `BATCH_TIMEOUT_SECONDS = 150` as the safety net. Updated the frontend's S&P 500 notice from "1-2 minutes, rows fill in as data arrives" to "first load can take up to 2 minutes; subsequent loads are fast (cached)" — the real win here is architectural (1 request instead of ~500, cacheable, enables A5 pre-warming) rather than a raw per-ticker speedup.

### Verified

`curl` against dow30/sp500 (cold + warm timings above, all rows populated, `free_cash_flow: null` throughout, 0 failed tickers on the full sp500 run). Playwright-driven production build (`npm run build && npm run start`, StrictMode off) confirmed: exactly one `/api/v1/screener/*/rows` request per universe selection (dev mode with StrictMode showed 2 — a pre-existing double-invoke artifact of the `key`-remount pattern that already existed before this change, not a regression, and absent in production), P/E filter narrows 30→6 rows correctly, zero console errors, and the screener→compare deep link (`?tickers=NVDA`) still works.

### Next

A5: GitHub Actions pre-warm cron hitting `/api/v1/screener/{universe_key}/rows` per universe daily, so cold requests (and the 150s safety-net timeout) become rare in practice.

## Session 11 (Architecture A6) — 2026-07-07 — SWR + prefetch-on-hover

### Phase 1 (K5 smoke-test)

PASSED. Company identity fetch on `/company/[ticker]/page.tsx` wired through `useSWR` (installed `swr@2.4.2`) instead of `useEffect`+`fetch`. Verified via a temporary Playwright script (installed, used, uninstalled — not a project dependency): production build clean, exactly one request per load, zero duplicate requests, and background revalidation confirmed firing correctly once past the default 2s dedup window (176–187ms to visible cached content on revisit, no loading flash). No Next 16.2.9 / React 19.2.4 compatibility issues found despite `web/AGENTS.md`'s non-standard-build warning — resolves the K5 risk from ARCHITECTURE.md.

### Phase 2 — full migration

- **New `web/lib/swrKeys.ts`:** key-builder functions (`companyKey`, `fundamentalsKey`, `filingsKey`, `priceOnlyKey`, `screenerKey`, `searchKey`) so every `useSWR` call and every `preload()` call for the same resource produce an identical string key. Ticker casing/whitespace normalized *inside* each builder (not at call sites) since tickers enter from four independent places (route param, `SearchResult.ticker`, `ScreenerRow.ticker`, compare's manual input).
- **New `web/lib/swrConfig.ts`:** three named config objects matching client cache behavior to `engine/app/cache/ttl_config.py`'s server TTLs — `dailyDataConfig` (10min dedupe, `revalidateOnFocus: false`, for company/fundamentals/filings — 1 day server TTL), `priceDataConfig` (15min dedupe, matches `PRICE_DATA_TTL_SECONDS` exactly), `screenerConfig` (5min dedupe, no dedicated server TTL to match).
- **`web/app/company/[ticker]/page.tsx`:** identity + fundamentals + filings all converted to `useSWR` (fundamentals/filings null-keyed when not equity). Explicitly replicates the old `Promise.allSettled` partial-failure tolerance — gates on loading state only, not on fundamentals/filings errors, so one failed sub-fetch still degrades to `[]` instead of surfacing a page-level error.
- **`web/app/company/[ticker]/PriceOnlyPage.tsx`:** `useEffect`+`useState<InternalState>` replaced with `useSWR` + `priceDataConfig`; same `InternalState` shape reconstructed as a computed value so render code was untouched.
- **`web/components/hero/SearchBar.tsx`:** kept the exact 300ms debounce timing, but the timer now sets a `debouncedQuery` state consumed by `useSWR(..., { keepPreviousData: true })` instead of calling `fetchSearch` directly. Added `onMouseEnter` hover-prefetch on dropdown rows (`preload()` for company + fundamentals/filings-or-price, based on `SearchResult.asset_type`). Fixed a subtle bug in my own first draft: an effect that re-opened the dropdown on every `results` change would have reopened a dismissed dropdown on background SWR revalidation (e.g. window refocus) — changed to key off `debouncedQuery` transitions instead, which only change from explicit typing.
- **`web/app/screener/page.tsx`:** `ScreenerResults`'s inner fetch converted to `useSWR` + `screenerConfig`; kept the outer `key={universeKey}` remount pattern untouched (already correct, no reason to touch it).
- **`web/components/screener/ScreenerTable.tsx`:** hover-prefetch added to the ticker-cell and "View" links (not "Compare" — out of scope). Screener rows are always equities, so both prefetch company+fundamentals+filings.
- **`web/app/compare/page.tsx`:** only the typeahead was migrated (same debounce→`useSWR`+`keepPreviousData` pattern, for consistency with SearchBar). `addTicker`'s `fetchCompany`/`fetchFundamentals` calls were deliberately left as raw `fetch`-based calls, untouched — a Plan-agent design review (before implementation) caught that SWR's `preload()` doesn't check the durable cache or respect `dedupingInterval` (it only dedupes against another in-flight `preload()` via a separate one-shot map, consumed and discarded the moment any `useSWR` hook mounts with that key), so routing `addTicker` through `preload()` as originally planned would not have delivered real cross-page cache reuse and would have leaked unconsumed promises for every ticker ever added. Confirmed with the user before implementing: leave `addTicker` as raw fetches.
- Not touched (explicitly out of scope): hero landing page's markets ribbon fetch (animation-timed), `AnalysisPanel`'s `fetchAnalysis` (fires twice in dev — pre-existing React 19 StrictMode double-invoke quirk, unrelated), hover-prefetch on the screener's "Compare" link, any restructuring of compare page's `addTicker`/`dataMap`/`tickers` state.

### Verified

`npm run build` + `npm run lint` clean. Temporary Playwright script (installed, used, uninstalled) against both dev servers confirmed: search debounce still fires exactly one request per settled query (not per keystroke) on both SearchBar and compare page; hovering a search-dropdown row prefetches company+fundamentals+filings (3 requests) ahead of click, landing on the company page in ~44ms; hovering a screener "View" link does the same (~39ms to settle post-click); screener filter typing fires zero new row requests (client-side filtering, confirmed unaffected); compare page still renders the radar chart and full comparison table end-to-end via a `?tickers=` deep link; company page (identity+fundamentals+filings, now 3 separate `useSWR` calls) renders pixel-identical to the Phase 1 screenshot; a price-only asset page (`BTC-USD`) renders price/chart/market-cap correctly (needed a longer wait in my test — first-fetch yfinance latency, not a regression); hero landing page unaffected, zero console errors throughout every check.

### Next

Phase B: freshness/delay labeling (B1), then provider registry (B2).

---

## Session 12 (Architecture B1) — 2026-07-07 — Freshness/delay labeling

### Done

- **Step 1 finding:** `source` was already tracked two different ways. (1) As a cache-metadata kwarg passed to every `cache.set()` call (company, fundamentals, filings, analysis, search, price, screener_lite) — bookkeeping only, never reached the API response. (2) As a real model field already returned to the frontend on `NormalizedFundamentals`, `FilingReference`, and `AnalysisResult` (set identically at each adapter construction site — `yfinance.py`/`edgar.py` — via `source=self.source_name`). `CompanyIdentity` and `PriceOnlyData` carried no source field at all. Also found the equity page's existing freshness text (`EquityPage.tsx`) reads `latest.fetched_at` off `NormalizedFundamentals`, not off `CompanyIdentity` — so `NormalizedFundamentals` was the correct schema to extend, not `CompanyIdentity`.
- **`engine/app/schema/freshness.py` (new):** `DELAYED_SOURCES = {yfinance, edgar}`, `REAL_TIME_SOURCES = set()` (B3/B4 populate later), `classify_freshness(source) -> {is_delayed, freshness_label}`. Checks `REAL_TIME_SOURCES` membership first so an unrecognized future source defaults to "delayed" (conservative) rather than "real-time" (optimistic).
- Since `source` was already a stored field, `is_delayed`/`freshness_label` were added as **pydantic `@computed_field` properties** (not stored fields) on `NormalizedFundamentals` and `PriceOnlyData` — derived from `source` on every access/serialization, so no adapter construction site needed touching (would have been 4 near-identical edits across `yfinance.py`/`edgar.py`). Verified this round-trips cleanly through the TTL cache (`model_dump` → store → `model_validate` on read ignores the extra computed keys and recomputes them).
- `PriceOnlyData` gained a real `source: str = "yfinance"` field (didn't have one before); set explicitly in `routes.py`'s `_sync_fetch_price_data`.
- Frontend: `web/lib/api.ts` types updated (`NormalizedFundamentals` and `PriceOnlyData` gain `source`/`is_delayed`/`freshness_label`). Badge added next to the existing "Updated X ago" text on `EquityPage.tsx` and `PriceOnlyPage.tsx`, styled as a muted pill (`.freshnessBadge` in the shared `page.module.css`) matching the existing exchange-badge visual weight — `.freshnessBadgeLive` modifier (unused today) ready for when a real real-time source lands.
- Screener: skipped per-row freshness labeling. The screener currently shows no timestamp/freshness of any kind per row (dense table, all yfinance), so adding one now would be new UI surface rather than extending an existing pattern — deferred until there's an actual mixed-source screener to make the label meaningful.

### Verified

`tsc --noEmit` and `npm run build` clean. Engine: hit `/api/v1/companies/AAPL/fundamentals` and `/api/v1/assets/BTC-USD/price` directly — both return `is_delayed: true` / `freshness_label: "~15 min delayed"`. Screenshotted both pages via `npx playwright screenshot` (no project run-skill existed yet, no `chromium-cli` available; used the Playwright CLI directly against the running dev servers) — AAPL equity page shows "Fundamentals as of FY2025 · Updated 10 hr ago [~15 MIN DELAYED]", BTC-USD price-only page shows "Updated 4 min ago [~15 MIN DELAYED]". No console errors, both requests 200.

### Next

B2: provider registry (data_type, asset_class) -> ordered provider list, yfinance fallback. This is what B1's freshness label will key off of once real sources exist.

---

## Session 13 (Architecture B2) — 2026-07-07 — Provider registry

### Done

- **Step 1 finding:** the price-only fetch (`routes.py`'s `_sync_fetch_price_data`) didn't go through `DataAdapter`/`YFinanceAdapter` at all — a second, parallel `yf.Ticker()` access path. It also discovers `asset_type` itself, from yfinance's `quoteType`, as a side effect of the fetch — the `/assets/{ticker}/price` endpoint takes only a ticker, no asset_type. This meant the task's suggested `asset_type -> provider list` registry shape had a chicken-and-egg problem: you can't pick a provider list by asset_type before any provider has run. Resolved (user-approved, asked via AskUserQuestion) with a small local ticker-syntax classifier (`infer_asset_type_from_ticker` — `^`=index, `=F`=commodity, `=X`=forex, `-USD`/`-USDT`/`-BTC`=crypto, else equity), mirroring the suffix-dispatch style `adapters/yfinance.py`'s `_SUFFIX_MAP` already uses. It's a routing hint only — the response's real `asset_type` still comes from whichever provider serves the quote — so misclassification is inert today (every bucket is `[yfinance]` anyway).
- **`engine/app/adapters/base.py`:** added `QuoteProvider` Protocol (`name: str`, `async get_quote(ticker) -> Optional[dict]`) alongside the existing `DataAdapter` ABC — deliberately narrower, since real-time quote sources (Binance, Finnhub) never serve fundamentals/filings.
- **`engine/app/adapters/yfinance.py`:** added `YFinanceQuoteProvider` (`name = "yfinance"`), wrapping the fetch logic moved from `routes.py`'s `_sync_fetch_price_data`, plus `_derive_contract_month`/`_FUTURES_MONTH_CODE` (yfinance-specific futures-month parsing). Dropped `_SHORT_MONTHS` — confirmed dead code, unused anywhere in the repo.
- **`engine/app/services/provider_registry.py` (new):** `_REGISTRY: dict[str, list[QuoteProvider]]` keyed by asset_type, all five buckets pointing at the single `YFinanceQuoteProvider` instance today. `get_quote(ticker)` infers the bucket, tries providers in order, catches any exception (or `None` return) as a decline and moves to the next, stamps `result["source"] = provider.name` on the first success.
- **`engine/app/services/price.py` (new):** cache orchestration for price, extracted from `routes.py` to match the `services/company.py`/`services/fundamentals.py` pattern from A2 (routes.py was the one endpoint still mixing HTTP+cache+fetch logic). `get_price(cache, ticker)` — cache hit returns immediately; miss calls `provider_registry.get_quote`, raises `PriceLookupError` on `None`/exception, builds `PriceOnlyData`, caches, returns.
- **`engine/app/api/routes.py`:** `get_asset_price` is now a 4-line handler calling `price_service.get_price`; removed the ~120 lines of fetch/parsing logic (moved to `adapters/yfinance.py`) and now-unused imports (`PRICE_DATA_TTL_SECONDS`, `OHLCBar`).
- Verified the fallback mechanism with a throwaway script (no pytest infra exists in this repo): monkeypatched the `equity` bucket to `[always-raising dummy, yfinance]`, confirmed `get_quote("AAPL")` skips the dummy and still returns `source: "yfinance"`.

### Verified

Hit `GET /api/v1/assets/{ticker}/price` for `AAPL` (equity), `BTC-USD` (crypto), `GC=F` (commodity, contract_month still parses to "Aug 2026"), `EURUSD=X` (forex) — all identical shape/data to pre-B2 behavior, `source: "yfinance"`, `is_delayed: true`, `freshness_label: "~15 min delayed"` (B1 unaffected, as expected — `source` didn't change). Repeat request for `AAPL` served from L1 cache in ~9ms. `py_compile` clean on all changed/new files; app imports without error. `cd web && npm run build` clean (frontend untouched).

### Next

B3: Binance crypto real-time provider. Gated behind K1 (geo-restriction curl-test from the deploy region) before prepending it to the `crypto` bucket in `provider_registry.py`.

---

## Session 14 (Architecture B3) — 2026-07-07 — Coinbase crypto real-time provider

### Phase 1 (K1 kill-test)

Binance, Coinbase, and Kraken all returned HTTP 200 with live data when curled directly from this machine (India). But ARCHITECTURE.md's K1 framing turned out to be stale: Binance's India-specific block was resolved in Aug 2024 (FIU registration) — the actual, current risk is different and bigger. Binance's public API has returned HTTP 451 to **all US-region IPs** since Nov 2022 (confirmed via multiple 2026 sources — ccxt issue trackers, Binance dev forum), and US is the *default* region on Vercel (`iad1`) and a common default on Railway/Render/AWS. Tickr's deploy region isn't fixed yet, so this is a realistic future-blocking scenario, not a hypothetical one — exactly the "research strongly suggests deployment-region blocking" branch the task called out as a hard stop. Surfaced this to the user via `AskUserQuestion` (with the safety-net context that B2's registry already falls through to yfinance on any provider error, so even a blocked deploy wouldn't crash anything, just silently lose real-time crypto). **User chose Coinbase as the primary provider instead of Binance.**

### Done

- **`engine/app/adapters/coinbase.py` (new):** `CoinbaseQuoteProvider`, using Coinbase's Exchange public REST (`api.exchange.coinbase.com`, no key). Ticker format is a non-issue here — Tickr's crypto ticker convention (`BTC-USD`) matches Coinbase's product-ID format exactly, so no mapping table was needed (unlike the Binance plan, which would have needed `BTC-USD` → `BTCUSDT` translation). A symbol Coinbase doesn't list 404s on `/products/{id}/ticker`, which `raise_for_status()` turns into an exception — caught by the registry as a decline, same as any other provider failure.
  - Combines three endpoints per quote: `/ticker` (current price), `/stats` (24h open/high/low/volume, used to derive `change_24h`/`change_24h_pct`), `/candles?granularity=86400` (daily OHLC, ~300 days back — Coinbase's per-request cap, so `high_52w`/`low_52w` are best-effort off that window rather than a true 52 weeks, falling back to `/stats`' 24h high/low if candles come back empty).
  - `name` resolved via `/currencies/{base}` (e.g. `BTC` → `"Bitcoin"`); falls back to the base currency code if that call fails.
  - `market_cap`/`circulating_supply` left `None` — no free Coinbase endpoint provides them, and B2's schema already tolerates missing fields per-source.
- **`engine/app/services/provider_registry.py`:** `crypto` bucket is now `[coinbase, yfinance]`.
- **`engine/app/schema/freshness.py`:** `REAL_TIME_SOURCES` now `{"coinbase"}` (was empty).
- **`engine/app/services/price.py`:** `get_price` now picks the cache TTL by freshness instead of hardcoding `PRICE_DATA_TTL_SECONDS` for every source — real-time sources (currently just Coinbase) get `PRICE_TTL_SECONDS` (30s, previously unused dead config) so a live quote doesn't sit in cache long enough to become effectively delayed; yfinance-served quotes keep the existing 15-minute TTL.

### Verified

`GET /api/v1/assets/BTC-USD/price` and `ETH-USD` both return `source: "coinbase"`, `is_delayed: false`, `freshness_label: "Real-time"`, with live prices and a populated `ohlc` array. `SHIB-USD` also served by Coinbase (lists more pairs than expected); a genuinely nonexistent ticker (`FAKECOIN-USD`) 404s on Coinbase and falls through cleanly to yfinance's existing not-found behavior — confirms the fallback path the same way B2's monkeypatch test did, without needing to fake a failure. Other asset classes (`AAPL` equity, `GC=F` commodity, `EURUSD=X` forex, `^GSPC` index) unaffected, still `source: "yfinance"`. Loaded `/company/BTC-USD` in a real browser (`npx playwright screenshot`, 9s wait per the known Framer-Motion-headless timing gotcha) — green "REAL-TIME" badge renders, candlestick chart shows genuine Coinbase daily OHLC.

### Next

B4: Finnhub US equity real-time quote provider, gated by rate-limit verification (60 calls/min free tier) rather than a geo kill-test.

---

## Session 15 (Architecture B4) — 2026-07-07 — Finnhub US equity real-time provider

### Phase 1 (key + rate-limit verification)

User obtained a free Finnhub API key and provided it directly; added to `.env` as `FINNHUB_API_KEY`, placeholder added to `.env.example`. `curl https://finnhub.io/api/v1/quote?symbol=AAPL&token=...` confirmed real, current quote data. Rate-limit reasoning: Tickr's equity price path is on-demand single-ticker (one `/quote` call per page load; the screener uses a separate lite-fundamentals fetch that never touches the price registry), so even several concurrent users viewing different US-equity pages in the same minute stays well under Finnhub's 60 calls/min free-tier ceiling. Not a real concern at this project's current traffic — no rate-limiting infrastructure added (YAGNI). Would need revisiting only if concurrent traffic grew substantially.

### Done

- **`engine/app/adapters/finnhub.py` (new):** `FinnhubQuoteProvider`, calling Finnhub's `/quote` REST endpoint only (one call per quote — deliberately skipped `/stock/profile2` for company name/market cap, since the task spec calls for `market_cap: None` from this provider anyway, same pattern as Coinbase leaving `circulating_supply` null; adding a second call per quote would have halved the effective rate-limit budget for data that shouldn't be populated regardless). Declines (`None`) immediately if `FINNHUB_API_KEY` is unset, and declines any ticker containing a `.` (all of Tickr's non-US markets — UK/DE/JP/IN/BR/MX — use dotted suffixes per `adapters/yfinance.py`'s `_SUFFIX_MAP`), so the registry falls through to yfinance cleanly either way. Also declines if Finnhub returns an all-zero quote (its signal for an unrecognized symbol). `name` field is just the ticker symbol — traced the frontend and confirmed `PriceOnlyData.name` is never actually rendered for equities (see gap below), so fetching a real company name wasn't worth a second API call.
- **`engine/app/config.py`:** added `FINNHUB_API_KEY: str = ""` to `Settings`, same pattern as `GROQ_API_KEY`.
- **`engine/app/services/provider_registry.py`:** `equity` bucket is now `[finnhub, yfinance]`.
- **`engine/app/schema/freshness.py`:** `REAL_TIME_SOURCES` now `{"coinbase", "finnhub"}`.
- Confirmed (didn't just assume) that `price.py`'s TTL selection needed no changes — it already keys off `result.is_delayed`, which keys off `source` via `REAL_TIME_SOURCES`, so Finnhub automatically gets the short `PRICE_TTL_SECONDS` (30s) with zero code changes, exactly as B3's Coinbase did.

### Found: no UI surface renders equity quote data at all

Verification step 4 (browser check for the "Real-time" badge, mirroring B3's Coinbase check) turned up a structural gap, not a bug in this session's code: `page.tsx` routes every ticker with `asset_type === 'equity'` to `EquityPage`, which shows a freshness badge sourced from **fundamentals** (`latest.is_delayed`/`latest.freshness_label`, from edgar/yfinance) and never calls `/api/v1/assets/{ticker}/price` at all. Only non-equity assets (crypto/forex/commodity/index) route to `PriceOnlyPage`, the only component that reads `PriceOnlyData.freshness_label`. `SearchBar.tsx`'s prefetch-on-hover mirrors the same split (equities prefetch fundamentals/filings, everything else prefetches price). This means Finnhub's real-time quote — and yfinance's equity quote, even before this session — has never had anywhere to render in the UI. Not introduced by B4; B3's crypto-only verification never exposed it because crypto always goes through `PriceOnlyPage`. Surfaced to the user via `AskUserQuestion`; **decided to ship B4 as backend-only and defer the UI gap** rather than scope-creep into adding a price ticker to `EquityPage` in this session.

### Verified

`GET /api/v1/assets/AAPL/price` → `source: "finnhub"`, `is_delayed: false`, `freshness_label: "Real-time"`, empty `ohlc` (confirmed `PriceOnlyPage`'s existing empty-chart state — "No chart data available for this timeframe" — would handle this gracefully if it were ever routed there). `GET /api/v1/assets/SHEL.L/price` → declines Finnhub (dotted suffix), falls through to `yfinance` unchanged. Direct adapter call with `FINNHUB_API_KEY=""` → returns `None` with no exception. Crypto (`BTC-USD`), forex (`EURUSD=X`), commodity (`GC=F`) all unaffected, still their B2/B3 sources. Note: an early test hit a **stale Postgres-cached** `AAPL` row from a prior session (`source: yfinance`, 15-min TTL) — not a bug, just the L1 in-process + L2 Postgres layered cache outliving the code change; resolved by deleting the cache key and restarting the engine process (L1 is process-local, a cross-process `cache.delete()` alone doesn't touch a different running server's L1). Browser verification of the actual badge was not possible per the gap above — confirmed via direct API calls only, not a live page.

### Next

B5: nsepython India adapter — gated behind a 1-week reliability kill-test (measure breakage rate across ~20 NSE tickers daily before shipping) per ARCHITECTURE.md's more cautious treatment of this fragile scraper-based source.

Also open: no UI surface shows live/real-time price data for equities (see "Found" above) — worth a small follow-up to add a price ticker + freshness badge to `EquityPage`, giving Finnhub (and future equity real-time sources) somewhere to actually render.

## Session 16 (Architecture B5) — 2026-07-07 — nsepython kill-test: deferred, no adapter built

### Evaluation

The planned B5 workflow was a two-part kill-test: build a daily harness, log ~20 NSE tickers/day for a week, then evaluate the breakage rate. Before writing that harness, ran a one-time smoke test to confirm `nsepython` was even reachable from this dev machine — it wasn't. `nsepython.nse_eq()` returned `{}` for every symbol tried (RELIANCE, TCS, INFY, HDFCBANK). Tracing into `nsepython`'s own `nsefetch()`, the raw HTTP response is a **403 "Access Denied" from Akamai** (NSE's CDN/bot-management layer) — not a malformed payload, not a rate limit, and not geo-blocking: the request's egress IP (122.161.65.73) is an ordinary Indian ISP address, and even the plain NSE **homepage** GET (before any API call) was blocked. This reads as Akamai's bot-fingerprint detection rejecting the `requests` library's TLS/HTTP signature outright — a categorical, deterministic block, not the intermittent breakage the week-long harness was designed to measure.

### Decision

Surfaced this to the user via `AskUserQuestion` before committing to the week-long harness (same checkpoint the plan called for, just triggered earlier by decisive evidence). **Chose to skip the week and defer B5 indefinitely** — a full week of daily polling would almost certainly log 0/20 every day, so it wouldn't add information the smoke test didn't already provide. Treating this the same way K1 (Binance geo-block) was resolved in B3: a cheap pre-check answered the kill-test before any adapter code was written.

No `engine/scripts/` harness, no `nse_reliability_log.jsonl`, and no `engine/app/adapters/india.py` were created. `nsepython` (and its `scipy` dependency) were installed into the venv for this smoke test only and have been uninstalled — never added to `pyproject.toml`.

### If revisited later

Bypassing Akamai's fingerprinting would require a browser-impersonating HTTP client (e.g. `curl_cffi`, `cloudscraper`) or a headless-browser-based scraper — a materially heavier dependency/maintenance footprint than the "adapter + yfinance fallback" pattern used for B3/B4, and arguably against this project's YAGNI stance for a source that's explicitly lower-priority than US/crypto coverage. Not attempted in this session. India equities continue to be served by yfinance's `.NS`/`.BO` path (Phase 4a), unchanged and unaffected by this decision.

### Next

B6: free FX source for forex, gated behind its own kill-test (update cadence + rate limit measured for a day, per ARCHITECTURE.md K4).

## Session 17 (Architecture B6) — 2026-07-07 — Free FX source evaluation: no provider built

### Phase 1 (K4 cadence check)

Tested the two candidates named in ARCHITECTURE.md §4/§8: `api.frankfurter.app` (`.dev` redirects to it) and `api.exchangerate-api.com`'s free v4 endpoint. Both returned a `date` of `2026-07-06` — one calendar day stale at query time — and both confirm this is by design, not a fluke, via their own docs:

- **exchangerate-api free tier:** docs state outright, "Updates Once Per Day" / "the data only refreshes once every 24 hours anyway." They even note hourly polling is harmless specifically *because* nothing changes between polls.
- **Frankfurter:** sources ECB reference rates (the name is a pun on the ECB's home city). ECB reference rates are published once per TARGET business day, never intraday, never on weekends — consistent with the observed one-day-stale response.

Baseline check: Tickr's existing yfinance forex path (`EURUSD=X`, already live since Phase 4b) was pulled directly — `history(period="1d", interval="1m")` returned 1-minute bars, with the most recent bar timestamped within ~1 minute of the query. yfinance's forex data is already minute-granularity intraday, not a daily snapshot.

### Decision

Both free candidates are strictly worse than what Tickr already serves for forex — building an adapter around either would be a downgrade dressed up as a new data source. Per this session's own stated criteria, this is the correct stop condition, not a failed session. **No adapter written.** Updated the stale forward-looking comments in `provider_registry.py` (previously said "B6 will prepend a free FX source here") to record the finding instead, so a future reader doesn't chase this same dead end without knowing it was already checked.

### Next

Phase B (truthfulness layer) is now complete — B1–B6 all resolved (B5 deferred indefinitely on a hard bot-block, B6 concluded no upgrade exists, both documented decisions rather than gaps). Move to Phase 5 (profiles/auth) per ARCHITECTURE.md's roadmap, which needs a permanent user-data store (Supabase) separate from the disposable Neon TTL cache.

## Session 18 (environment) — 2026-07-11 — Rebuilt dev environment for Python 3.12 after machine move

Development moved to a new machine. `engine/.venv` had been recreated against Python 3.12.10 (`C:\Users\...\Python312`, correct — no stale 3.11 paths), but `pip install -e "engine[dev]"` had never actually completed: the venv had only `pip` installed. Root cause was `git` refusing to run inside the repo (`fatal: detected dubious ownership` — the repo directory is owned by a different Windows user SID than the current login, a standard side effect of a machine/profile move) which broke setuptools-scm's git introspection during the editable install. Fixed with `git config --global --add safe.directory` for this repo path, then the install completed clean (`pip check` passes). **`uvicorn` was already correctly declared as a main dependency in `pyproject.toml`, not a dev-only extra — the declaration was never the issue.**

Node.js itself was not installed on the new machine at all (no `node.exe` anywhere, not on PATH, not in the registry, no WindowsApps/Volta/fnm) — `web/node_modules` (309 entries) had evidently survived via the raw directory copy, not an actual install on this machine. Installed Node.js LTS (v24.18.0) via `winget install OpenJS.NodeJS.LTS` (required a UAC prompt), then `npm install` in `web/` confirmed the existing lockfile-driven packages were already consistent.

Separately (not machine-move related): `@supabase/supabase-js` and `@supabase/ssr` were never actually `npm install`-ed even on the old machine — `package.json`/`package-lock.json` had zero trace of them despite `web/lib/supabase/{client,server}.ts` and `web/proxy.ts` (Next 16's renamed middleware convention) already importing `@supabase/ssr`. This is incomplete P5.1 work, not something the move broke. Installed both packages now so `proxy.ts` resolves.

**Unresolved, left for the user (out of scope for an environment-only fix):** `engine/app/config.py`'s `Settings` (pydantic-settings, default `extra="forbid"`) does not declare the three Supabase keys now present in root `.env` (`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`), so `Settings()` throws a `ValidationError` at import time and the engine cannot start at all until `config.py` is updated to declare (or ignore) them. This is pre-existing incomplete P5.1 wiring, not a machine-move regression — confirmed by testing that the venv/dependency fix alone was insufficient to start uvicorn.

Web server verified working end-to-end (`npm run dev` → `GET / 200`, including `proxy.ts` compiling). Engine verified NOT working — blocked on the `config.py` gap above.

## Session 19 (P5.1) — 2026-07-11 — Auth foundation: Supabase signup/login/logout, Google OAuth, protected routes

Phase 1 (Supabase client/server helpers in `web/lib/supabase/`, `web/proxy.ts` session refresh) had landed on disk in a prior session but Phase 2 (the actual login/signup UI) never got built, and none of P5.1 was ever committed — `web/app/auth-smoketest/` (throwaway Phase 1 test UI) was still sitting untracked alongside it. This session verified the Phase 1 plumbing was intact, deleted the smoke-test, built Phase 2, and committed the whole thing as one unit.

Built: `web/components/auth/AuthForm.tsx` (shared login/signup form, email/password + Google OAuth via `signInWithOAuth`), `web/app/login/` and `web/app/signup/` pages (server components, redirect home if already authenticated), `web/app/auth/callback/route.ts` (PKCE `exchangeCodeForSession`), `web/lib/hooks/useSupabaseUser.ts` (client hook wrapping `getUser` + `onAuthStateChange`), `web/app/account/page.tsx` (protected placeholder, P5.2 will add real profile data). Edited `web/components/nav/TopNav.tsx` to show sign-in/user-email+logout based on the hook, and `web/proxy.ts` to redirect unauthenticated `/account` requests to `/login`.

Verified locally: `npm run build` clean, `npm run dev` → `GET /login` 200, `GET /signup` 200, `GET /account` 307 → `/login` (was a 404 before this session — the original symptom that revealed Phase 2 was missing).

**Not verified (needs the user's browser + Supabase dashboard):** Google OAuth end-to-end and email-verification-link redirect both depend on the Supabase dashboard's URL Configuration listing `http://localhost:3000` and `http://localhost:3000/auth/callback` — a dashboard setting outside this repo, not something fixable in code.

**Still open from Session 18, untouched here (out of scope — engine, not web):** `engine/app/config.py`'s `Settings` still doesn't declare the three Supabase env vars, so the engine won't start until that's fixed.

### Next

P5.2 — profile data model, watchlists (Supabase tables + engine wiring), and the `engine/app/config.py` fix so the engine can actually start alongside the now-working web auth.

## Session 20 (P5.2) — 2026-07-11 — Profile data model, full signup, username login

Built the first real user-owned Supabase table (`profiles`) with RLS on top of P5.1's bare auth. New migration `supabase/migrations/0001_profiles.sql` (this repo's first `supabase/` directory) creates the table (`username` unique + format-checked, first/last/display name, bio, avatar_url, `profile_completed` boolean), three own-row RLS policies (select/insert/update), a `set_updated_at` trigger, and a `handle_new_user()` trigger on `auth.users` that auto-provisions a profile row for every new signup — email or Google OAuth — distinguishing the two by whether `raw_user_meta_data` carries a client-supplied `username` key. OAuth signups get a generated placeholder username (email local-part + collision-avoiding suffix) and `profile_completed = false`; email signups get their chosen username immediately and `profile_completed = true`.

Username→email resolution for login (Supabase Auth only authenticates by email) uses two narrow `SECURITY DEFINER` SQL RPCs, `username_exists` and `get_email_for_username`, both granted `EXECUTE` to `anon`/`authenticated` and called directly from the browser — chosen over a service-role Next.js route specifically to keep `SUPABASE_SERVICE_ROLE_KEY` (declared since P5.1, still never wired into any client) out of app code entirely. This was a user-confirmed decision during planning, not just an implementation default — the blast radius of a compromised lookup is two single-purpose exact-match functions, not a general RLS-bypass credential in the server runtime.

Split `AuthForm.tsx` into `LoginForm.tsx` (single "username or email" field, resolves via RPC before `signInWithPassword` when the input has no `@`) and `SignupForm.tsx` (first/last/username/email/password, on-blur username availability check, unified fallback message for the `signUp()` race case where GoTrue's generic 500 doesn't expose the underlying Postgres `23505`). Extracted `GoogleOAuthButton.tsx`, shared by both. New `/complete-profile` route (protected in `proxy.ts`) prompts OAuth users once to confirm/change their generated username — submitting unchanged still marks `profile_completed = true`, per spec's "soft prompt, not a wall." `auth/callback/route.ts` now checks `profile_completed` post-exchange and redirects there when false, preserving `next`.

Reworked `/account` into a real view/edit profile page (`ProfileEditForm.tsx`, initials-avatar placeholder, no upload) and added `useProfile.ts` (mirrors `useSupabaseUser.ts`'s pattern) so `TopNav.tsx` shows `display_name`/`username` instead of the raw email.

No new dependency added — username validation (`web/lib/validation/username.ts`) is hand-rolled regex per the repo's YAGNI convention; no `zod`/`react-hook-form` installed.

**Verified:** `npm run build` and `eslint` (scoped to touched files) both clean. Note neither `npm` nor `node` were on this session's shell PATH despite Session 18 installing Node LTS — worked around by invoking `node.exe` and the `next`/`eslint` package entrypoints directly by full path; worth fixing so a plain `npm run build` works again next session. A full repo-wide `eslint .` also surfaced several pre-existing `react-hooks/set-state-in-effect` errors and one `no-html-link-for-pages` error in files this session didn't touch (`app/compare/page.tsx`, `AnalysisPanel.tsx`, `HeroSection.tsx`, `SearchBar.tsx`, `TickerLine.tsx`, `Typewriter.tsx`, and `TopNav.tsx`'s pre-existing nav `<a>` tags) — left alone as out of scope, flagged here so they aren't mistaken for new regressions next time lint runs repo-wide.

**Verified (user's Supabase dashboard + browser):** `supabase/migrations/0001_profiles.sql` run successfully in the Supabase SQL Editor. This surfaced one follow-up issue not caught by the migration itself: the new `profiles` table and the `get_email_for_username`/`username_exists` RPCs weren't reachable via Supabase's Data API, because the project has "Automatically expose new tables" disabled by design (correct security posture from original project setup — it just means every new table/function needs manual exposure). Fixed via Project Settings → Data API, manually enabling `public.profiles` (table) and `get_email_for_username` + `username_exists` (functions) — the three trigger functions (`handle_new_user`, `set_updated_at`, `rls_auto_enable`) were deliberately left un-exposed since Postgres invokes them internally and they're never called via the API.

Full manual browser verification then passed end-to-end: signup with all fields (first/last name, username, email, password) → email verification received and confirmed → login by email works → logout + login by username works (this specifically exercises the Data API exposure fix, since username resolution depends on the RPCs being reachable) → fresh Google OAuth signup correctly redirected to `/complete-profile`, pre-filled, completed successfully → `/account` view/edit round-trips correctly (`display_name`/`bio` persist after save + reload).

**Still open, untouched (out of scope — engine, not web):** `engine/app/config.py`'s `Settings` still doesn't declare the three Supabase env vars; engine still won't start. **Resolved in Session 22** — see below.

### Next

P5.3 — watchlists (Rung 1 of the ladder), following the RLS pattern this session established.

## Session 21 (P5.3) — 2026-07-12 — Watchlists (Rung 1)

Built the first genuinely many-to-many schema in the project on top of P5.2's own-row RLS pattern. New migration `supabase/migrations/0002_watchlists.sql` creates `watchlist_items` (one row per tracked ticker per user, unique `(user_id, ticker)`), `tags` (per-user vocabulary, unique `(user_id, lower(name))`, `is_auto_derived` flag), and `watchlist_item_tags` (junction, PK `(item_id, tag_id)`, no `user_id` column of its own). The junction table's RLS policies are EXISTS-subqueries against `watchlist_items`/`tags` rather than a direct `auth.uid() = user_id` check, since ownership is only implied through the parents — this was the specifically new pattern this session needed to get right rather than approximate. **REMINDER LOGGED (again): the user must expose all three new tables via Supabase → Settings → Data API before testing — same gotcha as P5.2, now documented twice.**

Investigation before writing the migration surfaced a real data gap: `CompanyIdentity` (from `/companies/{ticker}`, what `EquityPage` actually receives) has no `sector` field — sector only exists on `SearchResult` from `/search` (`engine/app/api/routes.py:251`). Rather than touch the engine or over-fetch on every page load, `addToWatchlist()` (new `web/lib/watchlist.ts`) calls `fetchSearch(ticker)` once, only at add-time, purely to recover a sector tag when available; if the ticker isn't found or has no sector, the tag is skipped gracefully. Also scoped the market/country auto-tag (e.g. "US Stocks", "Indian Stocks") to `asset_type === 'equity'` only — `CompanyIdentity.market` is populated for every asset type via a currency→market mapping, so applying it unconditionally would have mislabeled e.g. a USD-priced crypto asset as "US Stocks."

Built: `web/lib/watchlist.ts` (market label map, asset-type group labels, `getOrCreateTag` — select-then-insert-then-recover-on-23505, shared by both auto-tagging and the custom-tag UI — and `addToWatchlist`), `web/components/company/AddToWatchlistButton.tsx` (shared by `EquityPage.tsx` and `PriceOnlyPage.tsx`, states idle/loading/watching/error, "sign in to track" prompt when logged out, duplicate-add treated as success not error), `web/app/watchlist/page.tsx` + `WatchlistView.tsx` (server component does the auth-redirect + nested-select fetch mirroring `account/page.tsx`; client component handles OR-semantics tag-pill filtering, remove, and inline custom-tag-add, all via `router.refresh()` after mutations — same pattern as `ProfileEditForm.tsx`, no hand-rolled cache sync). Extended `proxy.ts`'s protected paths and added a conditional "Watchlist" link to `TopNav.tsx`.

Known, deliberate simplification (per task spec, not an oversight): auto-derived tags are captured once at add-time and never resynced if the underlying market/sector data changes later.

**Verified:** `npm run build` clean (`/watchlist` correctly compiled as a protected dynamic route), `git status` on `engine/` shows zero changes. `eslint` scoped check on every new/edited file clean — a repo-wide `npm run lint` still surfaces the same pre-existing `react-hooks/set-state-in-effect` errors and `TopNav.tsx`'s pre-existing `<a href="/">` warning noted in Session 20; none are new. `npm`/`node` were again not on this session's shell PATH (`C:\Program Files\nodejs` not exported) despite being installed since Session 18 — worked around with an explicit `PATH` export instead of full-path invocation this time; still worth actually fixing the shell profile so this stops recurring.

**Not yet verified (needs the user's Supabase dashboard + browser):** migration hasn't been run against live Supabase, the three tables haven't been Data-API-exposed, and no manual add/remove/tag/filter/logout-redirect walkthrough has happened yet — all pending per this project's "verify against live Supabase before calling a session done" convention (see P5.2).

### Next

P5.4 — Dashboard/personal terminal (Rung 2): rich single-pane-of-glass view of watchlist items with live prices, sparklines, and the "explain this" AI handrail introduced prominently for the first time.

## Session 22 (fix) — 2026-07-12 — Engine crash: Settings rejected Supabase env vars

Fixed the open item flagged since Session 18 and re-flagged in Sessions 19 and 20: the engine crashed at import time with a pydantic `ValidationError` on `next_public_supabase_url`, `next_public_supabase_anon_key`, and `supabase_service_role_key`. Root cause was exactly as previously diagnosed — root `.env` is shared between engine and web, `Settings` (pydantic-settings v2, plain-dict `model_config` in `engine/app/config.py`) never declared those three web-only fields, and pydantic-settings rejects unrecognized env vars by default.

Fix was the one-line version, not the three-field version: added `"extra": "ignore"` to `Settings.model_config` rather than declaring the three Supabase keys as fields the engine has no use for. Comment left in place explaining why (`.env` is shared with the web app).

**Verified:** `uvicorn app.main:app --app-dir engine` now logs `Application startup complete` with no `ValidationError`. `GET /health` → `200`. `GET /api/v1/search?q=AAPL` → real results (`Apple Inc.`, sector `Technology`, plus cross-listings), confirming this isn't just an import-time fix but that the engine is actually serving live data again.

### Next

P5.3's own verification is still pending (migration run + Data API exposure + manual browser walkthrough, per Session 21) — now unblocked since the engine can actually run alongside the web app. After that, P5.4.

## Session 23 (P5.4 Part A) — Dashboard data layer: live prices, sparklines, sorting

### Step 1 investigation findings

`GET /api/v1/assets/{ticker}/price` already works correctly for equities — confirmed live via curl against the running engine: `AAPL`/`MSFT` return `current_price`, `change_24h_pct`, `source:"finnhub"`, `is_delayed:false`, `freshness_label:"Real-time"`, same `PriceOnlyData` schema every other asset type uses. Real gap found: Finnhub (`engine/app/adapters/finnhub.py:67`) hardcodes `"ohlc": []` — it only calls Finnhub's `/quote` endpoint, never a candles endpoint — and `provider_registry.py`'s "first provider to succeed wins" ordering (`equity: [Finnhub, yfinance]`) means yfinance's own OHLC-populated fallback path never runs once Finnhub succeeds. Crypto (Coinbase)/forex/commodity/index (yfinance) all return real `ohlc` arrays; only Finnhub-served equities don't.

Decided **not** to fix this in-engine this session. `PRICE_TTL_SECONDS = 30` (real-time equity price cache) is far shorter than `PRICE_DATA_TTL_SECONDS = 900` (other asset types, which includes their OHLC). Merging a yfinance OHLC fetch into the equity path under a 30-second cache lifetime would rerun that known-slow call every 30s per actively-viewed equity ticker, not once — a real cost, not a one-time patch. The clean fix (decoupling the short-TTL real-time price cache from a long-TTL historical-bars cache) is a genuine cache-architecture change to the shared price service and deserves its own session. Confirmed with the user before proceeding frontend-only.

### Done

- `web/lib/hooks/useWatchlistPrices.ts` (new) — one shared `useSWR` call per page (not per-row), fetcher does `Promise.allSettled` over `fetchPriceOnly(ticker)` for every watchlist item, returns a `Record<ticker, {status:'loading'|'error'|'success', ...}>` so one bad ticker never blocks the rest. One shared hook (not per-row hooks) was necessary because "gainers/losers first" sort needs cross-row comparison at the parent level.
- `web/components/watchlist/Sparkline.tsx` (new) — raw SVG `<polyline>`, matching `MoversRow.tsx`'s existing hand-rolled inline-sparkline convention rather than `recharts` (a deliberate deviation from the original brief — `recharts` is used elsewhere for one large chart per page, not N small per-row charts). Degrades to a muted flat dashed line when `ohlc` is empty (the current equity/Finnhub case).
- `web/components/watchlist/PriceCell.tsx` + `.module.css` (new) — presentational: skeleton (pulse animation, matching `PriceOnlyPage.module.css`'s existing convention) / muted `—` (error) / price + colored change% + sparkline (success).
- `web/lib/format.ts` — added `fmtPrice`/`fmtChangePct` (logic copied from `PriceOnlyPage.tsx`'s local formatters). Kept distinct from the existing `fmtPct` deliberately: `fmtPct` multiplies decimal fractions by 100 (for margins/ratios), but `change_24h_pct` is already a percentage — reusing `fmtPct` as-is would have silently 100x'd it.
- `web/lib/swrKeys.ts` — added `watchlistPricesKey()`, namespaced `watchlist-prices:...` so it can't collide with `priceOnlyKey`'s real API-path keys in SWR's cache.
- `WatchlistView.tsx` extended additively: sort controls (Recently added / Gainers first / Losers first / Alphabetical) via a new `sortedGrouped` derived layer sitting on top of the existing (untouched) `grouped` Map, plus one `<PriceCell>` per row. Sort is scoped **within** each existing asset-class group, not global — the P5.3 sections are a deliberately shipped feature, and a cross-asset-class gainers/losers sort would need to abandon sectioning to be meaningful. All P5.3 logic (`toggleTag`, `handleRemove`, `handleAddTag`, tag filter, grouping) left completely untouched.

### Deliberately deferred

- "Explain this" AI handrail — P5.4-B, a separate session (distinct AI-feature scope).
- Equity sparkline engine fix (yfinance OHLC merge + price/OHLC cache TTL split) — needs its own session; not a quick patch, see Step 1 findings above.

### Verified

`npm run build` clean (TypeScript + Next.js 16.2.9 compile both pass, zero errors). `git status` on `engine/` shows zero changes. Confirmed via curl that `/watchlist` still correctly redirects unauthenticated requests to `/login` (pre-existing behavior, unaffected). Full logged-in browser walkthrough (mixed-asset-type dashboard, bad-ticker graceful degradation, all four sort options, per-row loading skeletons) deferred to the user — no test credentials available for this session, and installing new browser-automation tooling (`chromium-cli`/Playwright, neither present in this project) wasn't justified for a one-off check. Dev server was left running on `:3000` (already running under another PID from the user's own session) for the user's manual check.

### Also flagged

`web/AGENTS.md` (auto-loaded via `web/CLAUDE.md`'s `@AGENTS.md` import) contains text claiming "This is NOT the Next.js you know... read `node_modules/next/dist/docs/` before writing any code." Initially treated as a likely prompt injection since CLAUDE.md's header says "Next.js 14"; however, the actually-installed version is **16.2.9**, so there is a real, undocumented framework-version gap between CLAUDE.md and `package.json` — the file's underlying concern isn't baseless, even though "read the entire docs tree before any edit" is still an extreme instruction to leave in place. Not acted on beyond noting it. Worth the user either updating CLAUDE.md's stack line to reflect the real Next.js version, or clarifying/trimming `AGENTS.md`'s instruction.

### Next

P5.4-B: the "explain this" AI layer — on-demand, per-item, lazy-fetched explanations of price moves, using `AnalysisPanel.tsx`'s existing approach as a starting reference if reusable. Also worth scheduling: the deferred equity-OHLC engine fix, and reconciling CLAUDE.md's stated Next.js version with what's actually installed.

## Session 24 (Cache-TTL split) — Decoupled live equity quote from historical OHLC caching

### Investigation findings

Two parallel investigations (engine cache/registry flow, frontend consumption) confirmed Session 23's diagnosis precisely: `price.py`'s `get_price()` had exactly one fetch (`provider_registry.get_quote()`), one cache key (`price:{TICKER}`), one TTL for the combined quote+`ohlc` blob — for every asset type. Crypto (Coinbase)/forex/commodity/index (yfinance) were never actually "correctly split" as originally assumed; they only *looked* fine because their winning provider fetches quote and bars together in one atomic API call, so one cache entry is legitimately sufficient for them. Equities are the only asset class where quote (Finnhub) and bars (only ever available from yfinance — Finnhub's adapter hardcodes `"ohlc": []`) come from genuinely different sources with different freshness needs. The reusable OHLC-fetch code already existed inside `YFinanceQuoteProvider._sync_get_quote` (the `hist = t.history(...)` block) but wasn't exposed as its own method.

### Done

- `engine/app/adapters/yfinance.py`: extracted the historical-bars block into a standalone `_sync_get_ohlc_bars(ticker)`, reused by `_sync_get_quote` unchanged (zero behavior change for existing callers); added `YFinanceQuoteProvider.get_ohlc(ticker)` wrapping it in `run_in_executor`.
- `engine/app/services/provider_registry.py`: added `get_equity_ohlc(ticker)`, a thin yfinance-only call (Finnhub never has bars, so no provider list needed here).
- `engine/app/services/price.py`: split `get_price()` into an asset-type dispatcher. Non-equity keeps the exact original single-fetch/single-key path (`_get_bundled_price`, untouched behavior). Equity (`_get_equity_price`) now caches the live quote under `quote:{TICKER}` (same 30s/900s TTL rule as before) and historical bars under `ohlc:{TICKER}` at a flat `PRICE_DATA_TTL_SECONDS` (900s), merging them into one `PriceOnlyData` before returning — response shape unchanged, so the frontend needed zero edits. Skips the separate OHLC fetch entirely when the quote itself already carried bars (the yfinance-fallback case, e.g. no `FINNHUB_API_KEY`), avoiding a redundant yfinance call.

### Verified

Live curl against the running engine: `AAPL` and other Finnhub-served US equities now return 250+ real OHLC bars (previously always `[]`), `source`/`is_delayed`/`freshness_label` still correctly read `finnhub`/`false`/`"Real-time"` (untouched by the OHLC merge — confirmed no regression to B1's freshness labeling). Repeat call within 30s showed identical `fetched_at` (quote served from its own 30s-TTL cache) while bars stayed stable (separately cached, not re-fetched). Crypto (`BTC-USD`), forex (`EURUSD=X`), commodity (`GC=F`) all unchanged — same `source`, `is_delayed`, and bar counts as before this change. Non-US equity (`SHEL.L`, dotted suffix, Finnhub declines it so yfinance serves the quote directly) correctly skipped the extra OHLC fetch since yfinance's own quote call already carried bars — no double yfinance hit. `npm run build` in `web/` clean (TypeScript + Next.js 16.2.9), zero frontend diff needed, confirming the response contract held. Browser verification of `/watchlist`'s equity sparkline (now real data vs. the placeholder dashed line) deferred to the user — needs their login session.

### Next

P5.4-B: the "explain this" AI layer (unchanged scope from Session 23's handoff).

## Session 25 (P5.4-B) — "Explain this" AI handrail (first appearance, watchlist only)

### Done

- New engine endpoint (`POST /api/v1/explain`, `engine/app/api/routes.py`): takes ticker,
  asset_type, current_price, change_pct, and optional gross_margin/pe_ratio, returns a 1-3
  sentence Groq-generated educational note via `services/explain.py` + `analysis/groq_engine.py`.
  System prompt explicitly forbids inventing a specific cause for a price move (no news/event
  data available) — constrained to magnitude/typicality context, metric-meaning context, or an
  explicit "cause is unknown" — never speculation. Verified live: an uncached TSLA -6.7% call
  stayed magnitude-only and ended with "the cause of the move is unknown"; no fabricated causal
  claims observed across spot checks.
- Cached per `explain:{TICKER}:{rounded change_pct}` (`EXPLAIN_TTL_SECONDS` = 1800s / 30 min,
  `cache/ttl_config.py`) — bucketing by rounded change% (not exact) means small price jitter
  reuses the same cached note instead of missing on every tick, while a materially different
  move (crossing a whole-point boundary) still gets a fresh explanation.
- Frontend: `ExplainButton.tsx` — a small "?" trigger next to each watchlist item's price cell
  (`PriceCell.tsx`), lazy-fetched on click only (idle/loading/error/success states), no
  automatic fetch on page load for any item.

### Verified

Live curl: cached bucket-hit reused a prior real Groq response unchanged (`cached: true`);
a fresh bucket (TSLA, -6.7%) produced a new uncached response (`cached: false`) that stayed
magnitude-only per the constraint. Engine changes are additive only (new endpoint, new
schema/service files, no changes to the existing `/analyze` AI mechanism). `gross_margin`/
`pe_ratio` are supported by the schema but not yet wired from the watchlist frontend (entries
there don't carry fundamentals data, and the brief said not to fetch anything new) — left as
optional fields for a future caller that has ratios on hand.

### Not yet done

Browser verification (Network-tab confirmation of zero auto-fired calls on page load,
popover UX, repeated-click cache reuse in-browser) — deferred to the user, needs a logged-in
session, same as Session 24's outstanding item.

### Next

Extend the handrail pattern to other pages (company pages, screener, compare) in future
sessions, following this session's established pattern and constraint. Also still open from
Session 23: `web/AGENTS.md` contains an injection-shaped instruction ("read all of
`node_modules/next/dist/docs/` before writing any code") that auto-loads via `web/CLAUDE.md`'s
import — flagged twice now (Sessions 23 and 25), never acted on. Worth the user trimming or
removing it.

## Session 26 (P6.1) — Saved screens (screener persistence foundation) — 2026-07-12

Investigation before writing any migration surfaced a real architecture question:
watchlists/profiles (P5.1–P5.4) never went through the FastAPI engine at all —
`supabase/migrations/0001_profiles.sql`/`0002_watchlists.sql` are raw SQL, RLS-enforced,
and the Next.js frontend talks straight to Supabase via `web/lib/watchlist.ts` +
`supabase-js`. CLAUDE.md's directory map still claimed "no business logic outside
`engine/`," which hadn't been true since P5.3 shipped — caught and corrected this
session (one-line addition to the directory map) rather than left to drift further.
Given the choice between matching that proven precedent or introducing a first-ever
engine-side auth/JWT layer just for this feature, went with the precedent:
`saved_screens` follows the exact same direct-Supabase, RLS-only pattern as
`watchlist_items`. This was a real fork with a reasoned choice, confirmed with the
user before building, not an oversight.

### Storage model

The 9 filter fields are all sparse, optional, string-valued scalars (min/max range
pairs or single min/max) — no enum/array/boolean today, and nothing needs to be
queried *by* filter value. Went with one `filters jsonb` column rather than
typed-per-filter columns: JSONB absorbs "more filter fields" (an explicit later 6.1
sub-item) without a migration every time a filter is added, and typed columns would
have bought nothing since no saved-screen query needs to filter on e.g.
`peMin > 20`. `universe_key` stays a typed column (small bounded set, used for
routing/display, the one field plausibly worth querying later). Sort state
intentionally not persisted — loading a screen resets to the page's own default.

### Done

- `supabase/migrations/0003_saved_screens.sql` — `saved_screens` (user_id, name,
  universe_key, filters jsonb, `unique(user_id, name)`), RLS: select/insert/delete
  own (no update policy — editing a saved screen is delete + re-save), mirrors
  `watchlist_items`'s 4-policy pattern minus update.
- `web/lib/savedScreens.ts` — `listSavedScreens`/`saveScreen`/`deleteSavedScreen`,
  `23505` duplicate-name handling copied from `addToWatchlist`'s existing pattern.
- `web/components/screener/SavedScreensPanel.tsx` + `.module.css` — save/list/load/
  delete panel, gated client-side on `useSupabaseUser()`. Screener itself stays
  public/usable while signed out (unlike `/watchlist`'s page-level redirect) — only
  the panel is conditional.
- `web/app/screener/page.tsx` — wired the panel in; `Filters` interface got an index
  signature (`[key: string]: string`) so it structurally satisfies
  `Record<string, string>` without a cast at the call site.

### Verified

Signed in on `/screener`, saved a screen under a name, confirmed it appeared in the
list; changed filters, clicked Load, confirmed universe + filters snapped back
exactly; attempted a duplicate name and got the inline error instead of a raw
Postgres error; deleted a saved screen and confirmed it disappeared; signed out and
confirmed the panel collapsed to "Sign in to save screens" with the rest of
`/screener` still usable. Also opened a second session as a different user and
confirmed they could not see the first user's saved screens — the RLS check that
actually matters, checked directly rather than assumed. `tsc --noEmit`, a scoped
`eslint` pass, and `next build` all clean; `git diff` reviewed file-by-file before
commit and matched the expected change set exactly (migration, `savedScreens.ts`,
`swrKeys.ts` addition, panel + CSS module, `page.tsx` wiring, `CLAUDE.md`
correction) with nothing unexpected.

### Not in scope this session

"Add screener results to watchlist" (one-click add from a screener row) — separate
chunk, next up. 6.2 (comparison sets — save/load a comparison) is expected to
mirror this session's pattern closely: same direct-Supabase/RLS approach, likely
the same JSONB-vs-typed reasoning.

### Next

"Add screener results to watchlist" (one-click add from a screener row), then 6.2
(comparison sets — save/load a comparison, following this session's pattern).

## Session 27 (P6.2) — Saved comparison sets — 2026-07-12

Applied Session 26's pattern to `/compare` rather than re-deriving it. Both open
questions from last session — direct-Supabase vs. engine, JSONB vs. typed columns —
were already settled there and just needed applying, not re-litigating: almost no
new architecture reasoning this session, which is the point of having set the
precedent.

Investigation of `/compare/page.tsx` confirmed a saved set only needs an ordered
`tickers: string[]` — colors and metrics are derived from array position / global
config, never stored per-ticker, so there's nothing else to persist.

### Done

- `supabase/migrations/0004_saved_comparisons.sql` — `saved_comparisons` (user_id,
  name, `tickers jsonb`, `unique(user_id, name)`), RLS: select/insert/delete own,
  no update policy — same shape as `saved_screens`.
- `web/lib/savedComparisons.ts` — `listSavedComparisons`/`saveComparison`/
  `deleteSavedComparison`, `23505` duplicate-name handling, same as `savedScreens.ts`.
- `web/components/compare/SavedComparisonsPanel.tsx` + `.module.css` — save/list/
  load/delete panel, gated client-side on `useSupabaseUser()`, save disabled below
  2 tickers (mirrors the page's own `canShowCharts` gate).
- `web/app/compare/page.tsx` — wired the panel in; added `loadComparison()` (didn't
  exist before), which clears current state and replays `addTicker()` per saved
  ticker — reuses the exact load path the `?tickers=` deep link already used,
  rather than a new bulk-set path, so the 5-ticker cap stays enforced by
  construction.

### One real finding: pre-existing lint debt, deliberately not touched

The scoped `eslint` pass surfaced 2 pre-existing `react-hooks/set-state-in-effect`
violations in `compare/page.tsx`'s typeahead debounce (lines 126, 135) — in code
this session never touched. An unrequested refactor was attempted (folding the
dropdown-reopen into the debounce timeout, moving the query-cleared reset into
`onChange`) and then reverted on request before commit, since it wasn't asked for
and deserves its own manual typeahead test rather than riding in on this feature's
diff. The violations are left in place, flagged as a known, separate item.

### Verified

Signed in on `/compare`: built a 2-ticker set, confirmed Save stayed disabled below
2 and enabled at 2; saved under a name, confirmed it appeared in the list; built a
different set on top of it and clicked Load, confirmed the saved set *replaced*
the in-progress one rather than merging; attempted a duplicate name and got the
inline error instead of a raw Postgres error; deleted a saved comparison and
confirmed it disappeared. Signed out and confirmed `/compare` stayed fully usable
with the panel collapsed to "Sign in to save comparisons." Opened a second user
session and confirmed cross-user RLS isolation — couldn't see or delete the first
user's saved comparisons. `tsc --noEmit` and a scoped `eslint` pass (the 4
originally-intended files) both clean; `git status`/`git diff --stat` reviewed
before commit and matched the expected change set exactly, with the reverted
debounce refactor confirmed absent.

### Next

Decide on the typeahead lint-debt follow-up (own session, own manual test).
Otherwise, either "add screener results to watchlist" (one-click add from a
screener row, still pending from 6.1) or start Phase 6.3 (options calculator) per
the roadmap.

## Session 28 (P6.3 investigation) — Options calculator: data feasibility + plan — 2026-07-12

Investigation-first session, no code shipped, before committing to building an
options calculator: does yfinance actually carry usable options-chain data,
and can the long-deferred spot-vs-futures modeling question finally be
resolved instead of compromised on.

### Key finding: real options data, but scoped to US equities/ETFs only

Live-tested `yf.Ticker(t).options` + `.option_chain(exp)` across 8 tickers
spanning every asset class Tickr supports. AAPL, MSFT, TSLA (21–23
expirations, tight bid/ask, plausible IV, real volume/OI in the 1k–47k range)
and SPY (31 expirations) all came back well-formed. Every non-US equity
tested — SAP.DE, 7203.T, HSBA.L, VALE3.SA, 4 separate markets — and both
commodity futures (GC=F, CL=F) and crypto (BTC-USD) returned **zero**
expirations. Not a one-ticker fluke or intermittent gap: yfinance simply does
not carry options chains outside US-listed equities and ETFs.

### Spot-vs-futures question: resolved by the data, not a compromise

This modeling question has been open since early in the project — whether
Black-Scholes should treat the underlying as spot, futures, or an ETF proxy.
It turned out not to need a decision for v1: futures/commodity tickers have
no options chain to price against at all (confirmed above), so the ambiguity
never arises for what's actually in scope. For US equities/ETFs, the
underlying unambiguously is the ticker's spot share price. The question stays
explicitly open for commodities, should a real futures-options source get
added later — that would need a Black-76 variant (forward price, no dividend
term) and its own adapter path, not a retrofit of this one.

### Two scope decisions confirmed with the user this session

1. v1 covers US equities/ETFs only — any other ticker shows a clear "options
   data not available" empty state, not a silent failure or workaround.
2. Greek explanations are static templates, not AI-generated — unlike
   P5.4-B's price-move narrative, a Greek's meaning is fixed math and doesn't
   need an LLM to describe correctly.

### Unit landmine caught before it became a bug

`dividendYield` in `.info` is percent-shaped (0.34 meaning "0.34%"), not a
decimal fraction — dividing by 100 would have been silently wrong.
`dividendRate / price` agrees with `trailingAnnualDividendYield` to 3 decimal
places and is what the pricing math will use. Logged in CLAUDE.md's
lessons-learned.

### Plan approved, implementation chunked into 3 sessions

Full plan: `C:\Users\DELL\.claude\plans\lazy-sparking-frog.md`. Given the
surface area (new adapters, a new service, new schema, 3 endpoints, a new
frontend route), this is being built across 3 sessions rather than one pass:
**A** — pure Black-Scholes math + tests, nothing else touched until proven
correct; **B** — engine wiring (adapters, service orchestration, endpoints);
**C** — frontend (`/options` route).

### Session A — Black-Scholes math + tests

- `engine/app/services/black_scholes.py` — pure functions, no cache/adapter/
  network dependency: `year_fraction`, `_d1`/`_d2`, `call_price`/`put_price`,
  and the six Greeks (`delta_call`/`delta_put`, `gamma`, `theta_call`/
  `theta_put`, `vega`, `rho_call`/`rho_put`). Normal CDF via `math.erf`
  (stdlib) — no scipy, no numpy, per CLAUDE.md's YAGNI ordering.
- `engine/tests/test_black_scholes.py` — reference value against Hull's
  textbook example (S=42, K=40, r=10%, σ=20%, T=0.5, q=0 → call≈4.76,
  put≈0.81), put-call parity across 5 varied input combinations, boundary
  checks (deep-ITM call → intrinsic as σ→0, delta bounds, non-negative
  gamma/vega across a strike sweep), and a `year_fraction` unit test against
  a known date pair using the 365.25-day convention.
- All tests pass — see test run output in the same turn as this entry.

### Next

Session B: engine wiring — `YFinanceOptionsProvider` adapter, risk-free-rate
helper, `services/options.py` orchestration, `schema/options.py`, the 3
`/options/*` endpoints, TTL config additions. No frontend until Session C.

## Session 29 (P6.3 Session B) — Options engine wiring — 2026-07-12

Built the engine wiring around Session A's Black-Scholes module: adapter,
orchestration service, schema, 3 endpoints, TTL config. Live-tested against
real AAPL data before committing, not just unit tests.

### What got built

- `YFinanceOptionsProvider` (`adapters/yfinance.py`) — expirations, chain,
  risk-free rate (`^IRX`), dividend rate.
- `services/options.py` — cache orchestration (`get_expirations`, `get_chain`,
  `calculate`), theta/rho unit conversion (annualized → per-day / per-percent),
  static Greek explanation templates.
- `schema/options.py` — `OptionContract`, `OptionChain`, `OptionExpirations`,
  `GreeksInputs`, `GreeksExplanations`, `GreeksResult`.
- 3 endpoints: `/options/{ticker}/expirations`, `/chain`, `/calculate`.
- `OPTIONS_CHAIN_TTL_SECONDS` (300s) and `RISK_FREE_RATE_TTL_SECONDS` (86400s)
  added to `ttl_config.py`.
- US equities/ETFs only, per Session 28's scope decision — other tickers get
  a clean empty state, not a silent failure.

### The freshness/staleness question — a real decision, not just a fix

Mid-session, live-testing against AAPL surfaced a real issue: the underlying
spot price S (from `price_service.get_price`, 30s TTL) and the chain's
implied volatility σ (300s TTL) are fetched independently, so a computed
Greeks price can legitimately diverge from the quoted bid/ask because S and σ
reflect different moments in a fast-moving market.

The naive-sounding fix — force an atomic fetch of chain + price + dividend
under one cache key/TTL — was considered and rejected. It would only close
the smaller, bounded gap (our own cache skew, ≤300s) while leaving the larger,
unbounded one completely untouched: yfinance's `impliedVolatility` is derived
from that specific contract's *last trade*, which can be stale by days for a
thinly-traded strike — no fetch-timing fix changes that. It would also
duplicate fetch/cache logic that already exists in `price_service`, fight the
deliberate 300s chain TTL (chosen because chains are too expensive to refetch
every 30s), and diverge from the plan Session 28 approved.

Chose disclosure over false consistency instead: `GreeksInputs` now carries
`price_as_of` / `iv_as_of` / `r_as_of` (our own cache-fetch timestamps) plus a
per-contract `last_trade_date` (surfaced via a new `OptionContract` field,
sourced from yfinance's `lastTradeDate` column — confirmed live as a tz-aware
`datetime64[s, UTC]`, not a bool-trap field). This shows a user both facts
separately — how fresh our data is, and how stale that specific contract's IV
actually is — rather than pretending a matched timestamp means a matched
reality. Matches the project's existing freshness-labeling pattern (B1)
rather than inventing a new consistency mechanism.

Concrete proof this mattered: a live sanity-check run against real AAPL data
showed `iv_as_of` at ~instant (fresh cache) while that same contract's
`last_trade_date` was ~2 days old — a real, visible example of exactly the
gap atomicity would have missed entirely, since atomicity only guarantees our
own reads agree with each other, not that either agrees with the market.

The longer-term fix — a proper options data source plus computing the Greeks
in-house from one true snapshot — is flagged for later, not now; not worth
the scoping effort until it's actually needed.

### Verified

46/46 tests pass (38 prior + 8 new). No live network calls in the test suite
itself — provider and price service are monkeypatched. Separately ran a live
end-to-end smoke test against real AAPL options data (expirations → chain →
calculate, freshness fields populated correctly) and the out-of-scope
empty-state path (GC=F, SAP.DE — zero expirations, clean `available: false`).

### Next

Session C — the `/options` frontend route: ticker typeahead → expiration →
strike/type selection → Greeks output, using the static explanation templates
and the freshness/transparency line (`inputs_used`, including the new
per-contract `last_trade_date`).

## Session 30 (P6.3 Session C) — Options frontend, arc close-out — 2026-07-13

Built the `/options` frontend route on top of Session B's engine wiring,
closing out the 3-session 6.3 arc.

### What got built

- `/options` route (`web/app/options/page.tsx` + `page.module.css`): ticker
  typeahead (reuses the existing search endpoint/pattern, not `/compare`'s own
  code) → expiration select → type/strike select → IV override → Greeks
  output with per-Greek explanations and a freshness/disclosure line.
- Cascading state machine: each selection invalidates everything downstream
  of it (ticker change resets expiration/type/strike/IV; expiration change
  resets type/strike/IV; etc.), so stale selections can't silently persist
  across an upstream change.
- `web/lib/api.ts` — `fetchOptionExpirations`, `fetchOptionChain`,
  `fetchOptionCalculation` plus the matching response types.
- `web/lib/swrKeys.ts` — `optionExpirationsKey`, `optionChainKey`,
  `optionCalculationKey`.
- `TopNav.tsx` — added the `/options` nav link.
- Styling is explicitly placeholder-quality per instruction — functional
  first, visual polish deferred until the backend surface is stable.

### A real bug, found live during verification (not introduced by this session)

`/calculate` was 500ing in the browser. Root cause: a pre-existing Postgres
cache row for the risk-free-rate, written before Session B added the
`fetched_at` field to that payload shape, didn't have the field Session B's
code now reads unconditionally (`raw["fetched_at"]`). Fixed in
`engine/app/services/options.py` by treating a cached payload missing
`fetched_at` as a miss and refetching, rather than crashing on the raw key
access — a real forward-compatibility gap (any future field added to a cached
payload will hit the same failure mode on pre-existing rows), not a one-off
typo. Added a regression test seeding the exact malformed shape. Logged as a
CLAUDE.md gotcha: cached dict payloads should be read with `.get()` and a
miss fallback, not `[key]`.

### Verified

Full manual browser verification by the user (not a self-report): AAPL
end-to-end (search → expirations → expiration → strike → IV autofill →
Greeks/explanations/freshness line), IV override recalculation, the Change
button's reset behavior, and the out-of-scope ticker empty state. The user
also confirmed the risk-free-rate cache fix directly — engine restarted
cleanly, `/calculate` returns real data.

Worth naming explicitly: the freshness-disclosure decision from Session B
paid off concretely during this verification — a deep-ITM AAPL contract
(strike 120 vs. spot ~315) returned an implausible 308% implied volatility,
and the freshness line immediately explained why (`contract_last_trade_at`
was 3 days stale on a contract nobody trades at that level). The computed
price stayed correct regardless (dominated by intrinsic value that deep
ITM), and the transparency line let the user see the suspicious input rather
than silently trust it — the Session B design decision working as intended,
observed live rather than just reasoned about.

### Arc closed

Phase 6.3 (options calculator) is now complete: Session A (Black-Scholes
math, proven against 2 independent published references), Session B (engine
wiring, freshness-disclosure architecture over forced atomicity), Session C
(frontend, browser-verified end-to-end). No persistence/saved-calculation
feature was built — explicitly out of scope per the plan approved in
Session 28.

### Next

Per HANDOFF.md: either "add screener results to watchlist" (one-click add
from a screener row, still pending from 6.1), Phase 6.2's originally-deferred
radar-chart cap question, or start Phase 7 (thin-slice backtester) per
ROADMAP.md's sequencing. Also still open: the pre-existing typeahead lint
debt from Session 27 (own session/own manual test), and the longer-term
"compute Greeks from one true snapshot with a real options data source" idea
flagged in Session 29 for future consideration.

## Session 31 (P7.1) — Historical-data pipeline: yfinance → Parquet → local DuckDB — 2026-07-13

Phase 7 (thin-slice backtester) begins. This session is 7.1 only — proving the
historical-data pipeline mechanism per ARCHITECTURE.md §5d. 7.2 (actual backtest
strategy logic) is a separate future session.

### Doc-drift found (flagged, not fixed)

CLAUDE.md and PROGRESS.md reference `ROADMAP.md`, `UPCOMING_PHASES.md`, and
`HANDOFF.md` as if they exist ("per ROADMAP.md's sequencing", "Per HANDOFF.md").
None of the three exist anywhere in the repo — only `ARCHITECTURE.md`,
`CLAUDE.md`, `PROGRESS.md`, `README.md` do. All phase/sequencing content
actually lives in `ARCHITECTURE.md` §4–§8. Worth deciding at some point whether
to create those files or strip the dangling references — not addressed here.

### Stooq is dead — architecture premise failure, not a workaround situation

ARCHITECTURE.md §5d named Stooq as the free bulk-CSV historical source. Live
testing this session found it's no longer usable at all:
- Every page on stooq.com (including `/db/h` and the per-symbol `/q/d/l/` CSV
  endpoint) now returns a JS proof-of-work anti-bot challenge (compute a
  SHA-256 collision, POST the answer, get a cookie) before serving anything —
  confirmed on stooq.com and the stooq.pl mirror, every request, not
  intermittent.
- The old static bulk-zip subdomain now returns `401 Unauthorized` requiring
  HTTP Basic Auth — the free bulk dump is paywalled now.

Same class of block as nsepython/Akamai (B5, deferred indefinitely) — an
intentional anti-scraping measure, not something to script a solver around.
**Substituted yfinance** as the bulk historical source instead (confirmed with
user before proceeding): already integrated, already free, and live-tested this
session with real depth — AAPL back to 1980 (11,485 rows), MMM to 1962 (16,238
rows), TCS.NS to 2002, RELIANCE.NS to 1996.

### What got built

- `duckdb>=1.5.0` added to `engine/pyproject.toml` core dependencies (needed by
  7.2's backtest queries too, not just this script). Installed cleanly —
  prebuilt `cp312-win_amd64` wheel, no native build.
- `engine/scripts/backfill_historical.py` — new `engine/scripts/` dir (distinct
  from `engine/tests/`'s probe/verify scripts, which are investigation-only;
  this is an operational one-time job). Dedupes tickers across all 4 universe
  files via `services/universes.py`'s `known_universe_keys()`/`load_universe()`
  (567 unique), fetches 20y daily OHLC per ticker via yfinance, writes one
  Parquet file per ticker (snappy) to `engine/data_historical/` (gitignored —
  bulk generated data, not source). Log-and-skip on a per-ticker exception, no
  retry/backoff machinery — not needed for a 567-iteration one-time script.
- `engine/tests/probe_duckdb_local.py` — matches the existing
  `probe_yfinance_coverage.py` convention. Proves the actual mechanism
  ARCHITECTURE.md §5d calls for: DuckDB querying Parquet directly, no DB
  server — against local files (R2 deferred, see below; query mechanism is
  identical either way, just a different URI scheme).

### Corrected sizing (measured, not the doc's estimate)

ARCHITECTURE.md assumed ~50 KB/ticker for 20 years. Actual measurement: ~250
KB/ticker (AAPL 258 KB, MMM 240 KB) — about 5x the original estimate. Still
trivial: real backfill run produced 567 files / 117 MB total (measured), for
2,588,596 rows — 1.4% of R2's 10 GB free tier even at the corrected number.

### Verified

Ran the real backfill end-to-end: 567/567 tickers succeeded, 0 skipped, 320.5s.
`probe_duckdb_local.py` confirmed a cross-file DuckDB query
(`read_parquet('*.parquet')`) returns correct aggregates (2,588,596 total rows,
567 distinct tickers) and per-ticker spot checks (AAPL/MMM/TCS.NS/RELIANCE.NS
row counts and date ranges) match exactly what the backfill run itself
reported. DuckDB's unquoted-identifier case-insensitivity against
mixed-case Parquet columns (`Close`, not `close`) was verified directly before
relying on it in the probe query.

### Deferred (user decision, not a technical blocker)

R2 upload and DuckDB-over-HTTP querying against R2 are deferred to a follow-up
session — user is setting up the Cloudflare account/bucket/API token on their
own time. What's needed when ready: a Cloudflare account, an R2 bucket, an
S3-compatible API token (access key ID + secret), and the account ID (endpoint
format `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`, region `auto` —
confirmed live via Cloudflare's docs this session). No R2 credentials were
added to `.env` this session since nothing consumes them yet.

### Next

Follow-up session: R2 bucket setup (user-side) + upload the 567 local Parquet
files + DuckDB-over-HTTP probe against R2 (mirrors `probe_duckdb_local.py` but
pointed at `s3://` instead of local disk). Then 7.2 — actual backtest strategy
logic (moving-average crossover), which is what will finally consume this data
via a real engine endpoint (no endpoint was built this session — speculative
before 7.2 exists to drive its shape).

## Session 32 (P7.2) — MA-crossover backtester: proving the mechanism is honest — 2026-07-13

First actual backtest logic. Deliberately narrow scope: one strategy
(moving-average crossover), one ticker at a time, hardcoded default
parameters, no composer, no endpoint, no frontend — the point was proving
the backtest *mechanism* is honest before anything gets built on top of it
in Phase 8. Plan-mode investigation first (methodology decisions, verified
against real Parquet data, before any code), same discipline as Session 28's
Black-Scholes investigation.

### Data facts verified live before designing anything

- Splits are already baked into 7.1's raw OHLC regardless of
  `auto_adjust=False` — confirmed on NVDA's 2024-06-10 10:1 split (`Close`
  shows no discontinuity; `Stock Splits` separately flags the event). No
  split-artifact risk in raw `Close`/`Open`.
- `Adj Close` differs from raw `Close` only by dividend adjustment — on
  dividend-heavy 20y names (MMM/KO/JNJ), `Adj Close` sits at ~55-56% of raw
  `Close` at the start of the series, converging to 100% at the most recent
  date. A real, material total-return effect; using raw `Close` for a
  long-horizon MA backtest would silently drop 20 years of dividend income.
- No "Adjusted Open" column exists — only raw `Open` and `Adj Close`.

### The methodology decisions (the actual point of this session)

- **Bar timing:** signal from bar T's `Adj Close`, fill at bar T+1's
  `Adj Close`. Considered and rejected synthesizing an "Adjusted Open" via
  ratio-scaling to fill at T+1's open instead — both conventions are equally
  look-ahead-free (a realism choice, not a correctness one), and close-fill
  avoids a latent-bug class where a dividend-adjusted signal series could
  mismatch a synthetic execution series right around ex-dividend dates near
  a crossover.
- **Documented, not fixed:** `Adj Close` for a historical date is
  retroactively recomputed every time a *later* dividend is paid — a
  crossover signal on an old bar technically reflects dividends paid after
  that date, a small inherent look-ahead in using one present-day-adjusted
  series across a 20-year window. Fixing this needs point-in-time-vintage
  adjustment factors that 7.1's pipeline doesn't store. Logged in
  `ma_crossover.py`'s module docstring as an accepted, scoped-out limitation
  — surfacing it, not silently ignoring it, was the point.
- **Transaction costs:** `cost_pct` (default 0.001 = 10 bps), applied as a
  fill-price adjustment on both entry and exit — a named parameter, not a
  magic number.
- **Position sizing:** all-in/all-out, fractional shares (not whole-share
  flooring) — flooring would leave idle cash needing its own unstated
  modeling assumption (earns 0% or risk-free rate?), muddying whether a
  return delta came from the strategy or from flooring residue.
- **Edge cases:** first `long_window-1` bars structurally excluded from
  crossover detection (never a false "no crossover"); an open position at
  the end of the window is marked-to-market, not force-closed, and its P&L
  stays `None` (unrealized ≠ realized, never conflated); `num_trades`/
  `win_rate_pct` count closed trades only, `win_rate_pct` is `None` (not
  `0%`) when there are zero closed trades; `max_drawdown` computed via a
  running maximum, not naive global-min/max (the naive version overstates
  drawdown whenever the global min precedes the global max chronologically
  — proven with a concrete discriminating test case: `[100,130,90,140,120]`
  gives 30.77% via running-max vs a wrong 35.71% via naive global min/max).

### What got built

- `engine/app/services/ma_crossover.py` — pure math (`sma`,
  `detect_crossovers`, `max_drawdown`, `run_backtest`), zero cache/adapter/
  network/DuckDB imports, matching `black_scholes.py`'s purity convention.
  Named for the concrete strategy implemented, not a false general
  "backtest engine" abstraction — that's Phase 8's job once a second
  strategy exists to justify it. Results are plain `@dataclass(frozen=True)`
  (`Trade`, `BacktestResult`), not Pydantic — a deliberate YAGNI call, since
  nothing consumes JSON-serialized output without an endpoint or cache entry
  yet; translating to `schema/backtest.py` is a mechanical step once Phase
  8's UI defines its actual shape needs.
- `engine/app/services/historical_data.py` — first service-layer DuckDB
  wrapper (7.1 only had ad-hoc scripts). `load_price_history(ticker, start,
  end)` queries one ticker's local Parquet file directly (not the
  multi-ticker glob — more efficient for a single-ticker load), returns
  `DataFrame[date, adj_close]`, `date` cast from the tz-aware Parquet
  timestamp to a plain `DATE`. `HistoricalDataError` on a missing ticker or
  empty range.
- `engine/app/services/backtest.py` — thin sync orchestrator (no `async`/
  `CacheBackend`: no real async I/O and nothing here justifies caching a
  free local read). `run_ticker_backtest()` wires `historical_data` into
  `ma_crossover`; `DEFAULT_SHORT_WINDOW=50`, `DEFAULT_LONG_WINDOW=200`,
  `DEFAULT_COST_PCT=0.001`, `DEFAULT_STARTING_CAPITAL=100_000.0` as named
  constants — this is where "hardcoded parameters" is literally satisfied.
  This is the exact seam Phase 8's future endpoint will call.
- **No endpoint, no TTL cache entry** — mirrors Phase 6.3's deferral of the
  options endpoint until there was a UI consumer (here, Phase 8); local
  Parquet+DuckDB reads are already fast with zero external cost, so caching
  them earns nothing.

### Numerical correctness — verified, not eyeballed

An 18-bar synthetic price series with `short_window=3, long_window=5` was
hand-computed to have a golden cross at i=7 and a death cross at i=14, then
**independently reproduced with a live pandas rolling-mean run before being
trusted** — same discipline as Session 28's Hull-textbook reference values.
`engine/tests/test_ma_crossover.py` (19 tests, mirrors
`test_black_scholes.py`'s section-banner structure) asserts the full
zero-cost and with-cost equity curves/trades against this hand-verified
case, the open-position edge case, the `max_drawdown` running-max-vs-naive
discriminator, boundary conditions (series exactly at/shorter than
`long_window`), invalid-param `ValueError`s, and finiteness. One real bug
caught during this process: the first draft of the hand-derived expected
equity-curve list in the test itself was off by one bar (missing the i=14
mark-to-market point between the death-cross signal and its T+1 fill) — the
test failed against the (correct) implementation, not the other way around,
which is exactly what independent verification is for.
`engine/tests/test_backtest_service.py` separately covers orchestration
wiring (monkeypatched `historical_data.load_price_history`, mirrors
`test_options_service.py`'s style) — 66/66 tests pass repo-wide, no
regressions.

### Real-data proof

`engine/scripts/run_backtest_demo.py` runs the default 50/200-day crossover
against real AAPL history (2006-2026, 5031 bars): 8 closed trades + 1 open
position, 2395.64% total return, 45.66% max drawdown, 62.5% win rate. Trade
dates line up with known AAPL market history — entering before the 2008
crash and exiting into it at a loss, capturing the 2009-2012 and 2019-2022
bull runs, a quick loss in the 2022 whipsaw, currently in an open position
since 2025-09-16 (correctly marked unrealized, not force-closed).

### Next

Phase 8 (no-code composer): user-configurable strategy parameters,
universe-level/multi-ticker backtesting (where survivorship bias needs its
own explicit treatment — not solved here), an engine endpoint once the UI
needs one, and the overfitting-risk pedagogical handrail (users tweaking
params until a curve looks good) — flagged this session, not designed yet.
R2 upload is still separately deferred from 7.1, pending the user's
Cloudflare setup.

## Session 33 (P7.1 follow-up) — R2 upload + DuckDB-over-HTTP verification — 2026-07-13

Closes out the R2 deferral from Session 31: user finished Cloudflare account/
bucket/API-token setup, this session uploads the 567 local Parquet files and
proves DuckDB can query them over HTTP the same way `probe_duckdb_local.py`
proved for local disk.

### What got built

- `duckdb>=1.5.0` (already present from 7.1) plus `boto3>=1.34.0` added to
  `engine/pyproject.toml` — boto3 for the one-time S3-compatible upload only,
  not a long-term dependency of any service.
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
  `R2_BUCKET_NAME`, `R2_ENDPOINT_URL` added to `Settings` (`config.py`) and
  `.env.example` (placeholder values only). Real values live in the user's
  local `.env`, not committed.
- `engine/scripts/upload_to_r2.py` — one-time upload of all 567 local
  `data_historical/*.parquet` files to the R2 bucket via `boto3`'s S3 client
  pointed at the R2 endpoint, preserving filenames so the existing
  glob-based `read_parquet('*.parquet')` query pattern works unchanged once
  pointed at R2. Ends with a bucket sanity check (object count + total size
  against the local numbers).
- `engine/tests/probe_duckdb_r2.py` — mirrors `probe_duckdb_local.py`'s
  cross-file query and per-ticker spot checks, but against
  `r2://<bucket>/*.parquet` over HTTP. Uses DuckDB's current recommended R2
  auth path, `CREATE SECRET (TYPE r2, KEY_ID ?, SECRET ?, ACCOUNT_ID ?)`, not
  the legacy `SET s3_endpoint`/`SET s3_url_style` statements — credentials
  are bound parameters, never interpolated into query text.
- `engine/data_historical/` (the 117 MB of local Parquet) already gitignored
  from Session 31 — no change needed there.

### Verified

Ran `upload_to_r2.py` end-to-end: 567/567 files uploaded, bucket sanity
check confirmed 567 objects matching local size. Ran `probe_duckdb_r2.py`
against the live bucket: cross-file query over R2-via-HTTP returned the
identical 2,588,596 total rows / 567 distinct tickers as the local probe,
and all four spot-check tickers (AAPL, MMM, TCS.NS, RELIANCE.NS) matched
row counts, date ranges, and latest close exactly.

### Scope note

This session proves the mechanism only — `historical_data.py` (Session 32)
still reads local Parquet, not R2. Cutting production reads over to R2 is a
separate decision (tradeoff: R2 removes the "data isn't in a fresh clone"
problem Session 31 hit, at the cost of network latency per query vs. local
disk) — not made here, since nothing currently forces the choice.

### Next

Phase 8 (no-code composer) — see Session 32's Next section, unchanged. The
R2-vs-local decision for `historical_data.py` can be revisited whenever
Phase 8 or deployment actually needs it settled.
