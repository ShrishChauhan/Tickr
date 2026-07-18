# Cache-orchestration for price/quote data — extracted from routes.py, mirrors
# services/company.py and services/fundamentals.py (A2).
from typing import Optional

from ..cache.base import CacheBackend
from ..cache.ttl_config import PRICE_DATA_TTL_SECONDS, PRICE_TTL_SECONDS
from ..schema import OHLCBar, PriceOnlyData
from . import provider_registry


class PriceLookupError(Exception):
    """Carries a message so routes.py can raise HTTPException(404, ...) unchanged."""


async def get_price(cache: CacheBackend, ticker: str) -> PriceOnlyData:
    ticker = ticker.upper()
    if provider_registry.infer_asset_type_from_ticker(ticker) == "equity":
        return await _get_equity_price(cache, ticker)
    return await _get_bundled_price(cache, ticker)


async def _fetch_quote(ticker: str) -> dict:
    try:
        quote = await provider_registry.get_quote(ticker)
    except Exception as e:
        raise PriceLookupError(str(e)) from e
    if quote is None:
        raise PriceLookupError(f"No price data available for {ticker}")
    return quote


async def _get_bundled_price(cache: CacheBackend, ticker: str) -> PriceOnlyData:
    """Crypto/forex/commodity/index: the winning provider (Coinbase/yfinance)
    already returns quote + OHLC bars from one atomic fetch, so one cache entry
    is correct here — splitting it would add a second key for data already
    obtained in a single round-trip."""
    cache_key = f"price:{ticker}"

    raw = await cache.get(cache_key)
    if raw is not None:
        return PriceOnlyData.model_validate(raw)

    quote = await _fetch_quote(ticker)
    result = PriceOnlyData(**quote)
    # Real-time sources (B3+) get a much shorter TTL — caching a live quote for
    # 15 min would silently turn it back into delayed data.
    ttl = PRICE_TTL_SECONDS if not result.is_delayed else PRICE_DATA_TTL_SECONDS
    await cache.set(cache_key, result.model_dump(mode="json"), ttl,
                     data_type="price", ticker=ticker, source=result.source)
    return result


async def _get_equity_price(cache: CacheBackend, ticker: str) -> PriceOnlyData:
    """Equities: Finnhub serves the live quote (short TTL) but never OHLC bars
    (adapters/finnhub.py hardcodes ohlc: []) — bars are fetched from yfinance and
    cached independently on a long TTL, so a 30s quote refresh never re-triggers
    a yfinance historical fetch."""
    quote_key = f"quote:{ticker}"

    raw_quote = await cache.get(quote_key)
    if raw_quote is not None:
        result = PriceOnlyData.model_validate(raw_quote)
    else:
        quote = await _fetch_quote(ticker)
        result = PriceOnlyData(**quote)
        ttl = PRICE_TTL_SECONDS if not result.is_delayed else PRICE_DATA_TTL_SECONDS
        await cache.set(quote_key, result.model_dump(mode="json"), ttl,
                         data_type="quote", ticker=ticker, source=result.source)

    if not result.ohlc:
        # Only Finnhub-served quotes reach here empty — a yfinance-fallback quote
        # (e.g. no FINNHUB_API_KEY) already carries real bars from the same fetch.
        result.ohlc, result.ohlc_source, result.ohlc_as_of = await _get_equity_ohlc(cache, ticker)
    elif result.ohlc_source is None:
        # Bundled yfinance-fallback quote: bars came from the same fetch as
        # the quote itself, never through the OHLC chain — reuse its provenance
        # rather than re-fetching. Also backfills legacy cached rows (written
        # before ohlc_source existed) so they don't stay permanently unset.
        result.ohlc_source = result.source
        result.ohlc_as_of = result.fetched_at
    return result


async def _get_equity_ohlc(cache: CacheBackend, ticker: str) -> tuple[list[OHLCBar], Optional[str], Optional[str]]:
    cache_key = f"ohlc:{ticker}"

    raw = await cache.get(cache_key)
    if raw is None:
        try:
            bars, as_of, source = await provider_registry.get_equity_ohlc(ticker)
        except Exception:
            bars, as_of, source = [], None, None
        raw = {
            "bars": [OHLCBar(**bar).model_dump(mode="json") for bar in bars],
            "source": source,
            "as_of": as_of,
        }
        await cache.set(cache_key, raw, PRICE_DATA_TTL_SECONDS,
                         data_type="ohlc", ticker=ticker, source=source or "")

    if isinstance(raw, list):
        # Pre-Chunk-3 cache shape (bare bar list, always yfinance, no as_of) —
        # still valid during this TTL's rollout window.
        return [OHLCBar.model_validate(bar) for bar in raw], "yfinance", None

    bar_dicts = raw.get("bars", [])
    return [OHLCBar.model_validate(bar) for bar in bar_dicts], raw.get("source"), raw.get("as_of")
