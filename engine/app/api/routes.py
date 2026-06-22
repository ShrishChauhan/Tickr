# API routes — thin HTTP layer; no business logic, only adapter dispatch
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..adapters.edgar import EdgarAdapter
from ..adapters.yfinance import YFinanceAdapter
from ..schema import CompanyIdentity, NormalizedFundamentals, FilingReference
from ..schema.fundamentals import Period
from ..schema.filings import FilingType

router = APIRouter()

_adapters = {
    "edgar": EdgarAdapter(),
    "yfinance": YFinanceAdapter(),
}


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
    try:
        return await adapter.get_company(ticker.upper())
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


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
    try:
        company = await adapter.get_company(ticker.upper())
        return await adapter.get_fundamentals(company, period_enum, limit)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


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
    try:
        company = await adapter.get_company(ticker.upper())
        return await adapter.get_filings(company, filing_types, limit)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
