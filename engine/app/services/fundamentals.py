# Cache-orchestration + normalization for fundamentals — extracted from routes.py
from typing import List

from ..adapters.base import DataAdapter
from ..cache.base import CacheBackend
from ..cache.ttl_config import FUNDAMENTALS_TTL_SECONDS
from ..schema import NormalizedFundamentals
from ..schema.fundamentals import Period
from ..utils.ratios import derive_ratios


class FundamentalsLookupError(Exception):
    """Carries the original exception's message for HTTPException(404, detail=str(e))."""


async def get_fundamentals(
    adapter: DataAdapter,
    cache: CacheBackend,
    ticker: str,
    source: str,
    period: Period,
    limit: int,
) -> List[NormalizedFundamentals]:
    ticker = ticker.upper()
    cache_key = f"{source}:fundamentals:{ticker}:{period.value}:{limit}"

    raw = await cache.get(cache_key)
    if raw is not None:
        items = [NormalizedFundamentals.model_validate(item) for item in raw]
        return [f.model_copy(update={"ratios": derive_ratios(f)}) for f in items]

    try:
        company = await adapter.get_company(ticker)
        result = await adapter.get_fundamentals(company, period, limit)
    except Exception as e:
        raise FundamentalsLookupError(str(e)) from e

    result = [f.model_copy(update={"ratios": derive_ratios(f)}) for f in result]
    await cache.set(cache_key, [item.model_dump(mode="json") for item in result],
                     FUNDAMENTALS_TTL_SECONDS, data_type="fundamentals", ticker=ticker, source=source)
    return result
