# Local Parquet historical OHLC loader (Phase 7.1 pipeline) — first
# service-layer DuckDB wrapper. Pure I/O boundary: hands the pure
# ma_crossover module a plain [date, adj_close] DataFrame and nothing else,
# so the math stays independently testable on synthetic data.
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data_historical"


class HistoricalDataError(Exception):
    """Carries a message so callers can surface it directly."""


def load_price_history(ticker: str, start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
    """Returns DataFrame[date, adj_close], ascending by date. `date` is a
    plain date (Parquet's tz-aware timestamp is cast away — the time-of-day
    component is yfinance-index noise, not meaningful for daily bars).
    `start`/`end` are optional 'YYYY-MM-DD' bounds, inclusive.
    Raises HistoricalDataError if no local Parquet file exists for the
    ticker or the query returns zero rows."""
    ticker = ticker.upper()
    parquet_path = _DATA_DIR / f"{ticker}.parquet"
    if not parquet_path.exists():
        raise HistoricalDataError(f"No local historical data for '{ticker}' — run backfill_historical.py first")

    con = duckdb.connect()
    query = (
        "SELECT CAST(date AS DATE) AS date, \"Adj Close\" AS adj_close "
        f"FROM read_parquet('{parquet_path.as_posix()}')"
    )
    params = []
    if start is not None:
        query += " WHERE date >= ?"
        params.append(start)
        if end is not None:
            query += " AND date <= ?"
            params.append(end)
    elif end is not None:
        query += " WHERE date <= ?"
        params.append(end)
    query += " ORDER BY date"

    df = con.execute(query, params).fetchdf()
    if df.empty:
        raise HistoricalDataError(f"No historical rows for '{ticker}' in the requested range")
    return df


def load_ohlc_bars(ticker: str, start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
    """Returns DataFrame[date, open, high, low, close, volume], ascending by
    date — additive alongside load_price_history(), which stays untouched for
    the backtester's narrower [date, adj_close] need.

    `close` is sourced from Parquet's "Adj Close" column, not "Close" — this
    matches live yfinance OHLC's default (dividend-adjusted) convention, so a
    provider-registry fallback from yfinance to this loader doesn't show a
    fake discontinuity at the failover boundary. `open`/`high`/`low` are
    Parquet's raw (split-adjusted-only, per CLAUDE.md's yfinance lesson;
    never dividend-adjusted) columns — a smaller, disclosed seam, since
    yfinance itself doesn't expose dividend-adjusted O/H/L either.

    Raises HistoricalDataError if no local Parquet file exists for the
    ticker or the query returns zero rows."""
    ticker = ticker.upper()
    parquet_path = _DATA_DIR / f"{ticker}.parquet"
    if not parquet_path.exists():
        raise HistoricalDataError(f"No local historical data for '{ticker}' — run backfill_historical.py first")

    con = duckdb.connect()
    query = (
        "SELECT CAST(date AS DATE) AS date, \"Open\" AS open, \"High\" AS high, "
        "\"Low\" AS low, \"Adj Close\" AS close, \"Volume\" AS volume "
        f"FROM read_parquet('{parquet_path.as_posix()}')"
    )
    params = []
    if start is not None:
        query += " WHERE date >= ?"
        params.append(start)
        if end is not None:
            query += " AND date <= ?"
            params.append(end)
    elif end is not None:
        query += " WHERE date <= ?"
        params.append(end)
    query += " ORDER BY date"

    df = con.execute(query, params).fetchdf()
    if df.empty:
        raise HistoricalDataError(f"No historical rows for '{ticker}' in the requested range")
    return df
