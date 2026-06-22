# API routes — thin HTTP layer; no business logic, only adapter dispatch + cache
# Cache key scheme:
#   {source}:company:{TICKER}
#   {source}:fundamentals:{TICKER}:{period}:{limit}
#   {source}:filings:{TICKER}:{limit}:{types_str}   (types_str = sorted comma-joined values or "all")
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..adapters.edgar import EdgarAdapter
from ..adapters.yfinance import YFinanceAdapter
from ..cache.postgres import PostgresCacheBackend
from ..cache.ttl_config import COMPANY_INFO_TTL_SECONDS, FUNDAMENTALS_TTL_SECONDS, FILING_REF_TTL_SECONDS
from ..schema import CompanyIdentity, NormalizedFundamentals, FilingReference
from ..schema.fundamentals import Period
from ..schema.filings import FilingType

router = APIRouter()

_adapters = {
    "edgar": EdgarAdapter(),
    "yfinance": YFinanceAdapter(),
}

_cache = PostgresCacheBackend()


def _get_adapter(source: str):
    adapter = _adapters.get(source)
    if adapter is None:
        raise HTTPException(status_code=400, detail=f"Unknown source '{source}'. Valid: edgar, yfinance")
    return adapter


@router.get("/companies/{ticker}", response_model=CompanyIdentity)
async def get_company(
    ticker: str,
    source: str = Query(default="edgar", description="Data source: edgar or yfinance"),
):
    adapter = _get_adapter(source)
    ticker = ticker.upper()
    cache_key = f"{source}:company:{ticker}"

    raw = await _cache.get(cache_key)
    if raw is not None:
        return CompanyIdentity.model_validate(raw)

    try:
        result = await adapter.get_company(ticker)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    await _cache.set(cache_key, result.model_dump(mode="json"), COMPANY_INFO_TTL_SECONDS,
                     data_type="company", ticker=ticker, source=source)
    return result


@router.get("/companies/{ticker}/fundamentals", response_model=List[NormalizedFundamentals])
async def get_fundamentals(
    ticker: str,
    source: str = Query(default="yfinance", description="Data source: edgar or yfinance"),
    period: str = Query(default="annual", description="Period: annual, quarterly, or ttm"),
    limit: int = Query(default=5, ge=1, le=20, description="Number of periods to return"),
):
    adapter = _get_adapter(source)
    try:
        period_enum = Period(period)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid period '{period}'. Valid: annual, quarterly, ttm")

    ticker = ticker.upper()
    cache_key = f"{source}:fundamentals:{ticker}:{period}:{limit}"

    raw = await _cache.get(cache_key)
    if raw is not None:
        return [NormalizedFundamentals.model_validate(item) for item in raw]

    try:
        company = await adapter.get_company(ticker)
        result = await adapter.get_fundamentals(company, period_enum, limit)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    await _cache.set(cache_key, [item.model_dump(mode="json") for item in result],
                     FUNDAMENTALS_TTL_SECONDS, data_type="fundamentals", ticker=ticker, source=source)
    return result


@router.get("/companies/{ticker}/filings", response_model=List[FilingReference])
async def get_filings(
    ticker: str,
    source: str = Query(default="edgar", description="Data source: edgar or yfinance"),
    limit: int = Query(default=10, ge=1, le=50, description="Number of filings to return"),
    types: Optional[str] = Query(default=None, description="Comma-separated filing types: 10-K,10-Q,8-K,DEF 14A"),
):
    adapter = _get_adapter(source)
    filing_types = None
    if types:
        try:
            filing_types = [FilingType(t.strip()) for t in types.split(",")]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid filing type: {e}")

    ticker = ticker.upper()
    types_str = ",".join(sorted(t.value for t in filing_types)) if filing_types else "all"
    cache_key = f"{source}:filings:{ticker}:{limit}:{types_str}"

    raw = await _cache.get(cache_key)
    if raw is not None:
        return [FilingReference.model_validate(item) for item in raw]

    try:
        company = await adapter.get_company(ticker)
        result = await adapter.get_filings(company, filing_types, limit)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    await _cache.set(cache_key, [item.model_dump(mode="json") for item in result],
                     FILING_REF_TTL_SECONDS, data_type="filings", ticker=ticker, source=source)
    return result
