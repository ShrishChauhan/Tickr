# Finnhub adapter — real-time US equity quotes (free tier, 60 calls/min).
# Declines any ticker with an exchange suffix (non-US per Phase 4a's _SUFFIX_MAP)
# and declines entirely if FINNHUB_API_KEY is unset, so local dev without a key
# falls straight through to yfinance with no error.
from datetime import datetime, timezone
from typing import Optional

import httpx

from ..config import settings
from .base import LoaderLicense

_BASE_URL = "https://finnhub.io/api/v1"


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f  # NaN check
    except (TypeError, ValueError):
        return None


class FinnhubQuoteProvider:
    """Covers US-listed equities only — Finnhub's free tier has no reliable
    coverage for Tickr's other markets (UK, Germany, Japan, India, Brazil,
    Mexico), all of which use dotted ticker suffixes. Declines those so the
    registry falls through to yfinance."""

    name = "finnhub"
    license = LoaderLicense.UNCLEAR  # ToS review pending — see adapters/base.py LoaderLicense

    async def get_quote(self, ticker: str) -> Optional[dict]:
        if not settings.FINNHUB_API_KEY:
            return None

        symbol = ticker.upper()
        if "." in symbol:
            return None

        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=5.0) as client:
            resp = await client.get(
                "/quote", params={"symbol": symbol, "token": settings.FINNHUB_API_KEY}
            )
            resp.raise_for_status()

        data = resp.json()
        current_price = _safe_float(data.get("c"))
        if not current_price:
            # Finnhub returns all-zero fields for symbols it doesn't recognize
            return None

        return {
            "ticker": symbol,
            "name": symbol,
            "asset_type": "equity",
            "currency": "USD",
            "current_price": current_price,
            "change_24h": _safe_float(data.get("d")),
            "change_24h_pct": _safe_float(data.get("dp")),
            "high_52w": None,
            "low_52w": None,
            "market_cap": None,
            "volume_24h": None,
            "circulating_supply": None,
            "contract_month": None,
            "ohlc": [],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
