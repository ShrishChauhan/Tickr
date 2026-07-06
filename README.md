# Tickr

A free, AI-native equity research web app. It covers global equities across
seven markets, price-only quotes for crypto/forex/commodities/indices, and
tools to compare and screen companies side by side — all on top of public,
no-API-key-required data sources.

This is a portfolio project built to demonstrate both engineering and
product thinking. The docs in this repo (`ARCHITECTURE.md`, `PROGRESS.md`)
track real design tradeoffs as they happened, including what got cut and why
— a fundamentals-cache field with no cheap data source, a client-side
fan-out pattern that had to be pulled back into the server, and so on.

---

## What works today

- **Global equity coverage** — companies across seven markets: US, UK,
  Germany (XETRA), Japan (TSE), India (NSE/BSE), Brazil (B3), and Mexico
  (BMV), each with market-aware currency and exchange handling.
- **Price-only assets** — crypto, forex, commodities, and indices get an
  adaptive price/chart view instead of a fundamentals table.
- **Tagged typeahead search** — find a company or asset without needing to
  know its exchange suffix.
- **Comparison page** (`/compare`) — up to 5 tickers, a 5-metric radar chart
  (margins, ROE, ROA) plus a full transposed fundamentals table with
  best-per-row highlighting.
- **Screener** (`/screener`) — Dow 30, NASDAQ-100, NIFTY 50, and S&P 500
  universes, with 7 filters (market cap, P/E, net margin, ROE, debt/equity,
  gross margin, revenue) over a single batched server-side endpoint.
- **Data freshness indicators** — every page shows how old the underlying
  data is, so nothing is presented as more current than it actually is.

---

## Architecture

Tickr runs a FastAPI engine that owns all business logic, backed by a
layered cache (an in-process L1 in front of a Neon Postgres L2), with a
Next.js frontend that stays a thin client — no fetching or orchestration
logic in the browser. Everything is built to stay on free tiers.

The project is mid-way through an architecture migration aimed at latency:
extracting cache orchestration into a `services/` layer and replacing
client-side data fan-out with batched server endpoints. As of the last
completed session, the in-process L1 cache is live, orchestration has been
extracted for the company/fundamentals paths, and the screener now runs
through a single batched endpoint instead of hundreds of per-ticker browser
requests.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full current-vs-target
diagrams, the latency plan, the data-source plan, and the migration
sequencing.

---

## Where this is headed

**Near-term:**
- Remaining latency work — a pre-warm cron for the screener universes and
  client-side stale-while-revalidate caching.
- Fresher real-time data per asset class (crypto, US equities, India), each
  gated behind a reliability check before it ships.

**Once a permanent user-data store exists** (planned: Supabase, kept
separate from the disposable Postgres cache):
- A profile/login system — watchlists and saved research.

**Further out:**
- An options pricing calculator.
- The long-term centerpiece: a no-code strategy creator with backtesting —
  building and sharing trading strategies the way people share code on
  GitHub, backed by historical data and Monte Carlo / VaR simulation.
- An **MCP server** exposing Tickr's research engine as tools inside Claude
  Code, Claude Desktop, and similar AI assistants — letting an agent query
  fundamentals, run comparisons, or pull screener results directly through
  Tickr's API. This is a future direction, not a built feature.

---

## Development notes

`CLAUDE.md` has the working conventions (directory map, adapter pattern,
caching rules). `PROGRESS.md` has the full session-by-session build log,
including the roadblocks hit and how they were resolved.

---

## Author

Shrish Chauhan — [f20221095@pilani.bits-pilani.ac.in](mailto:f20221095@pilani.bits-pilani.ac.in)
