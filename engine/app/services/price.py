# Cache-orchestration for price/quote data — extracted from routes.py, mirrors
# services/company.py and services/fundamentals.py (A2).
from ..cache.base import CacheBackend
from ..cache.ttl_config import PRICE_DATA_TTL_SECONDS
from ..schema import PriceOnlyData
from . import provider_registry


class PriceLookupError(Exception):
    """Carries a message so routes.py can raise HTTPException(404, ...) unchanged."""


async def get_price(cache: CacheBackend, ticker: str) -> PriceOnlyData:
    ticker = ticker.upper()
    cache_key = f"price:{ticker}"

    raw = await cache.get(cache_key)
    if raw is not None:
        return PriceOnlyData.model_validate(raw)

    try:
        quote = await provider_registry.get_quote(ticker)
    except Exception as e:
        raise PriceLookupError(str(e)) from e

    if quote is None:
        raise PriceLookupError(f"No price data available for {ticker}")

    result = PriceOnlyData(**quote)
    await cache.set(cache_key, result.model_dump(mode="json"), PRICE_DATA_TTL_SECONDS,
                     data_type="price", ticker=ticker, source=result.source)
    return result
