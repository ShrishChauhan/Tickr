# API routes — thin HTTP layer; no business logic, only adapter dispatch + cache
# Cache key scheme:
#   {source}:company:{TICKER}
#   {source}:fundamentals:{TICKER}:{period}:{limit}
#   {source}:filings:{TICKER}:{limit}:{types_str}   (types_str = sorted comma-joined values or "all")
#   analysis:{TICKER}:{source}:{period}:{limit}
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..adapters.edgar import EdgarAdapter
from ..adapters.yfinance import YFinanceAdapter
from ..analysis.interface import AnalysisEngine
from ..cache.postgres import PostgresCacheBackend
from ..cache.ttl_config import (
    COMPANY_INFO_TTL_SECONDS,
    FUNDAMENTALS_TTL_SECONDS,
    FILING_REF_TTL_SECONDS,
    AI_ANALYSIS_TTL_SECONDS,
)
from ..config import settings
from ..schema import CompanyIdentity, NormalizedFundamentals, FilingReference, AnalysisResult
from ..schema.fundamentals import Period
from ..schema.filings import FilingType

router = APIRouter()

_adapters = {
    "edgar": EdgarAdapter(),
    "yfinance": YFinanceAdapter(),
}

_cache = PostgresCacheBackend()

_analysis_engine: Optional[AnalysisEngine] = None

_DISCLAIMER = (
    "AI-generated analysis based on reported financial data. "
    "Not investment advice. Verify figures independently before making any financial decision."
)


def _get_adapter(source: str):
    adapter = _adapters.get(source)
    if adapter is None:
        raise HTTPException(status_code=400, detail=f"Unknown source '{source}'. Valid: edgar, yfinance")
    return adapter


def _get_analysis_engine() -> Optional[AnalysisEngine]:
    global _analysis_engine
    if _analysis_engine is None and settings.GROQ_API_KEY:
        from ..analysis.groq_engine import GroqAnalysisEngine
        _analysis_engine = GroqAnalysisEngine()
    return _analysis_engine


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


@router.get("/companies/{ticker}/analyze", response_model=AnalysisResult)
async def analyze_company(
    ticker: str,
    source: str = Query(default="yfinance", description="Data source for underlying data: yfinance or edgar"),
    period: str = Query(default="annual", description="Fundamental period: annual or quarterly"),
    limit: int = Query(default=5, ge=1, le=10, description="Number of periods to include in analysis"),
):
    engine = _get_analysis_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="AI analysis not configured (GROQ_API_KEY missing)")

    adapter = _get_adapter(source)
    try:
        period_enum = Period(period)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid period '{period}'. Valid: annual, quarterly")

    ticker = ticker.upper()
    cache_key = f"analysis:{ticker}:{source}:{period}:{limit}"

    raw = await _cache.get(cache_key)
    if raw is not None:
        return AnalysisResult(
            ticker=ticker,
            analysis=raw["analysis"],
            disclaimer=_DISCLAIMER,
            generated_at=datetime.fromisoformat(raw["generated_at"]),
            cached=True,
            source=source,
            period=period,
            periods_analyzed=raw.get("periods_analyzed", limit),
        )

    try:
        company = await adapter.get_company(ticker)
        fundamentals = await adapter.get_fundamentals(company, period_enum, limit)
        filings = await adapter.get_filings(company, None, 5)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not fundamentals:
        raise HTTPException(status_code=404, detail=f"No fundamentals found for {ticker}")

    try:
        analysis_text = await engine.analyze_company(company, fundamentals, filings, "")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {e}")

    generated_at = datetime.now(timezone.utc)
    periods_analyzed = len(fundamentals)

    await _cache.set(
        cache_key,
        {
            "analysis": analysis_text,
            "generated_at": generated_at.isoformat(),
            "periods_analyzed": periods_analyzed,
        },
        AI_ANALYSIS_TTL_SECONDS,
        data_type="analysis",
        ticker=ticker,
        source=source,
    )

    return AnalysisResult(
        ticker=ticker,
        analysis=analysis_text,
        disclaimer=_DISCLAIMER,
        generated_at=generated_at,
        cached=False,
        source=source,
        period=period,
        periods_analyzed=periods_analyzed,
    )
