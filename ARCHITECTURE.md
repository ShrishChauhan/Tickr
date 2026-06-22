# Tickr — Architecture

## System overview

```
┌─────────────────────────────────────────────────┐
│  Clients (thin — no business logic)             │
│                                                 │
│   ┌──────────────┐      ┌────────────────────┐  │
│   │  Web App     │      │  MCP Server        │  │
│   │  (Next.js)   │      │  (Phase 5)         │  │
│   └──────┬───────┘      └────────┬───────────┘  │
└──────────┼──────────────────────┼───────────────┘
           │ HTTP / function calls │
           ▼                       ▼
┌──────────────────────────────────────────────────┐
│  ENGINE  (FastAPI — all logic here)              │
│                                                  │
│  ┌─────────────┐  ┌──────────────┐               │
│  │ API routes  │  │ AI analysis  │               │
│  │ (thin HTTP) │  │ layer        │               │
│  └──────┬──────┘  └──────┬───────┘               │
│         │                │                       │
│  ┌──────▼────────────────▼───────┐               │
│  │  Data adapters (one per src)  │               │
│  │  edgar.py  │  yfinance.py     │               │
│  │  (Phase 4: india sources)     │               │
│  └──────┬────────────────────────┘               │
│         │  Internal schema only crosses here     │
│  ┌──────▼───────────────┐                        │
│  │  Cache layer (TTL)   │◄──── PostgreSQL        │
│  └──────────────────────┘                        │
└──────────────────────────────────────────────────┘
           │
           ▼  (adapters reach outward to live sources)
┌────────────────────────────────────────────────────┐
│  Data sources                                      │
│  SEC EDGAR (edgartools)  ·  yfinance               │
│  Phase 4: NSE/BSE India sources                    │
└────────────────────────────────────────────────────┘
```

---

## Core design rules

### 1. Adapter pattern — the only way to add a data source

Each data source is a class that implements `DataAdapter` (see `engine/app/adapters/base.py`).
The contract:

```python
async def get_company(ticker, market) -> CompanyIdentity
async def get_fundamentals(company, period, limit) -> List[NormalizedFundamentals]
async def get_filings(company, filing_types, limit) -> List[FilingReference]
```

The engine only ever calls this interface. Raw API responses never cross the adapter boundary.
**Adding India (Phase 4)** = two new files (`nse.py`, `bse.py` or combined), zero changes to engine core.

### 2. Internal schema — market-aware from day one

Every company/security carries `market`, `exchange`, and `currency` explicitly
(`engine/app/schema/company.py`). These are enums — extending for India means adding enum
values, not changing the model shape. All monetary values in `NormalizedFundamentals` are
denominated in the declared `currency` field.

### 3. Caching — lazy, TTL-based, layered over live fetches

Request flow:
```
1. Check cache (PostgreSQL key-value with expires_at)
2. Cache hit → return immediately
3. Cache miss → fetch live via adapter → store with TTL → return
```

TTL by data type (see `engine/app/cache/ttl_config.py`):

| Data type | TTL | Rationale |
|-----------|-----|-----------|
| Live prices | 30 s | Stale fast; often skip entirely |
| Fundamentals (quarterly/annual) | 1 day | Rarely changes intra-day |
| Filing references | 1 day | New filings uncommon |
| AI-generated analysis | 7 days | Expensive; valid until next filing |
| Company metadata | 1 day | Name/exchange changes are rare |

AI analysis is the most expensive thing to generate — cache it hardest.

### 4. No business logic in clients

The web app and MCP server are presentation/transport layers only. They call engine HTTP
endpoints and render responses. If a rule, calculation, or decision touches data, it belongs
in the engine — not in a React component or an MCP tool handler.

---

## Phase roadmap

| Phase | Focus |
|-------|-------|
| 0 (done) | Scaffold, schema, adapter interface |
| 1 | EDGAR + yfinance adapters, fundamentals API endpoints |
| 2 | PostgreSQL cache layer, DB models, Alembic migrations |
| 3 | Next.js web app — company pages + AI Q&A UI |
| 4 | India data sources (NSE/BSE) as new adapters |
| 5 | MCP server exposing engine to Claude Code/Desktop |
