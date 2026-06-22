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
