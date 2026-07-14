# FRED (Federal Reserve Economic Data) adapter — authoritative risk-free rate
# (Phase 9.1), replacing the ^IRX-via-yfinance proxy. DTB3 (3-Month Treasury
# Bill Secondary Market Rate, Discount Basis) is the correct like-for-like
# series: confirmed live against yfinance ^IRX (both discount-basis quoting,
# track within ~1bp) — DGS3MO (investment/coupon-equivalent basis) runs
# ~15bp higher and is NOT the right series despite covering the same maturity.
from typing import Optional

import httpx

from ..config import settings

_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
_SERIES_ID = "DTB3"


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


class FredRiskFreeRateProvider:
    """DTB3 only republishes once/day and can lag several calendar days behind
    (weekends + ~1 business day H.15 publication delay) — real, disclosed via
    the observation's own date, not papered over with a fetch-time stamp."""

    name = "fred"

    async def get_risk_free_rate(self) -> tuple[float, str]:
        if not settings.FRED_API_KEY:
            raise RuntimeError("FRED_API_KEY is not configured")

        params = {
            "series_id": _SERIES_ID,
            "api_key": settings.FRED_API_KEY,
            "file_type": "json",
            "sort_order": "desc",
            # Small lookback window — enough to skip a few holiday/missing
            # ("."), not a full history fetch for a single latest-value read.
            "limit": 10,
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(_BASE_URL, params=params)
            resp.raise_for_status()
        data = resp.json()

        for obs in data.get("observations", []):
            # FRED represents missing/holiday observations as the literal
            # string ".", not null or omission.
            raw_value = obs.get("value")
            if raw_value == "." or raw_value is None:
                continue
            pct = _safe_float(raw_value)
            if pct is None:
                continue
            return pct / 100.0, obs["date"]

        raise RuntimeError(f"No valid {_SERIES_ID} observation in the lookback window")
