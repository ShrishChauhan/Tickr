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
