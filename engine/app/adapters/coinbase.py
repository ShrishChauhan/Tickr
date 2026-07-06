# Coinbase Exchange adapter — real-time crypto quotes. Chosen over Binance (see
# PROGRESS.md B3 session) because Binance's public API returns HTTP 451 to
# US-region IPs, a realistic risk given Tickr's deploy region isn't fixed yet;
# Coinbase's public endpoints carry no such geo-block.
from datetime import datetime, timezone
from typing import Optional

import httpx

_BASE_URL = "https://api.exchange.coinbase.com"
_HEADERS = {"User-Agent": "tickr-app"}


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


class CoinbaseQuoteProvider:
    """Coinbase Exchange public REST — no key required. Product IDs (e.g.
    BTC-USD) match Tickr's crypto ticker format directly, so no ticker mapping
    is needed; a symbol Coinbase doesn't list simply 404s and the registry
    falls through to yfinance."""

    name = "coinbase"

    async def get_quote(self, ticker: str) -> Optional[dict]:
        product_id = ticker.upper()
        base_currency = product_id.split("-")[0]
        quote_currency = product_id.split("-")[1] if "-" in product_id else "USD"

        async with httpx.AsyncClient(base_url=_BASE_URL, headers=_HEADERS, timeout=5.0) as client:
            ticker_resp, stats_resp, candles_resp = (
                await client.get(f"/products/{product_id}/ticker"),
                await client.get(f"/products/{product_id}/stats"),
                await client.get(f"/products/{product_id}/candles", params={"granularity": 86400}),
            )
            for resp in (ticker_resp, stats_resp, candles_resp):
                resp.raise_for_status()

            name = base_currency
            currency_resp = await client.get(f"/currencies/{base_currency}")
            if currency_resp.status_code == 200:
                name = currency_resp.json().get("name") or base_currency

        tick = ticker_resp.json()
        stats = stats_resp.json()
        candles = candles_resp.json()

        current_price = _safe_float(tick.get("price"))
        open_24h = _safe_float(stats.get("open"))
        change_24h = None
        change_24h_pct = None
        if current_price is not None and open_24h:
            change_24h = current_price - open_24h
            change_24h_pct = (change_24h / open_24h) * 100

        ohlc_bars = []
        for row in candles or []:
            try:
                ohlc_bars.append({
                    "date": datetime.fromtimestamp(row[0], tz=timezone.utc).date(),
                    "low": float(row[1]),
                    "high": float(row[2]),
                    "open": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]) if row[5] is not None else None,
                })
            except (IndexError, TypeError, ValueError):
                continue
        ohlc_bars.sort(key=lambda b: b["date"])

        # Candles cover ~300 days (Coinbase's per-request cap), not a full 52
        # weeks — best-effort high/low from that window, falling back to the
        # exchange's own 24h stats if candles came back empty.
        high_52w = max((b["high"] for b in ohlc_bars), default=_safe_float(stats.get("high")))
        low_52w = min((b["low"] for b in ohlc_bars), default=_safe_float(stats.get("low")))

        return {
            "ticker": product_id,
            "name": name,
            "asset_type": "crypto",
            "currency": quote_currency,
            "current_price": current_price,
            "change_24h": change_24h,
            "change_24h_pct": change_24h_pct,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "market_cap": None,
            "volume_24h": _safe_float(stats.get("volume")),
            "circulating_supply": None,
            "contract_month": None,
            "ohlc": ohlc_bars,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
