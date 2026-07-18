# Local Parquet OHLC loader — the equity-OHLC chain's fallback tail
# (provider_registry.py, ("ohlc", "equity")) behind live yfinance. Reads the
# same Phase 7.1 backfill (data_historical/*.parquet) the backtester uses,
# via the additive services/historical_data.load_ohlc_bars().
import asyncio
from datetime import timedelta
from typing import Optional

from .base import LoaderLicense
from ..services.historical_data import HistoricalDataError, load_ohlc_bars

# This is a cached local copy of yfinance data (Phase 7.1 backfill), not an
# independent source — it inherits yfinance's PERSONAL_ONLY restriction
# rather than being separately commercial-safe just because it's on disk.
_LICENSE_REASON = "cached copy of yfinance data — inherits yfinance's PERSONAL_ONLY restriction"


def _sync_get_ohlc(ticker: str) -> tuple[list[dict], Optional[str]]:
    try:
        df = load_ohlc_bars(ticker)
    except HistoricalDataError:
        return [], None
    if df.empty:
        return [], None

    # Match yfinance's period="1y" window, anchored to the freshest local
    # row rather than today() — the backfill is a point-in-time snapshot,
    # not a live feed, so "now" would silently under-fill the window.
    max_date = df["date"].max()
    tail = df[df["date"] >= (max_date - timedelta(days=365))]

    bars = [
        {
            # DuckDB's CAST(... AS DATE) round-trips through fetchdf() as a
            # midnight pandas Timestamp, not a python date — same conversion
            # adapters/yfinance.py's _sync_get_ohlc_bars already applies.
            "date": row.date.date() if hasattr(row.date, "date") else row.date,
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
            "volume": float(row.volume) if row.volume is not None else None,
        }
        for row in tail.itertuples(index=False)
    ]
    max_date_only = max_date.date() if hasattr(max_date, "date") else max_date
    as_of = max_date_only.isoformat()
    return bars, as_of


class ParquetOHLCLoader:
    """Fallback tail for the equity OHLC chain when yfinance is unavailable.
    `license = PERSONAL_ONLY`: see _LICENSE_REASON above."""

    name = "parquet"
    license = LoaderLicense.PERSONAL_ONLY  # see _LICENSE_REASON

    async def get_ohlc(self, ticker: str) -> tuple[list[dict], Optional[str]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_get_ohlc, ticker)
