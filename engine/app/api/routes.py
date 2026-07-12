# API routes — thin HTTP layer; no business logic, only adapter dispatch + cache
# Cache key scheme:
#   {source}:company:{TICKER}
#   {source}:fundamentals:{TICKER}:{period}:{limit}
#   {source}:filings:{TICKER}:{limit}:{types_str}   (types_str = sorted comma-joined values or "all")
#   analysis:{TICKER}:{source}:{period}:{limit}
#   price:{TICKER}
#   explain:{TICKER}:{change_bucket}
import asyncio
from datetime import datetime, timezone
from typing import List, Optional

import yfinance as yf
from fastapi import APIRouter, HTTPException, Query

from ..adapters.edgar import EdgarAdapter
from ..adapters.yfinance import YFinanceAdapter
from ..analysis.interface import AnalysisEngine
from ..cache.layered import LayeredCacheBackend
from ..cache.ttl_config import (
    FILING_REF_TTL_SECONDS,
    AI_ANALYSIS_TTL_SECONDS,
)
from ..config import settings
from ..schema import CompanyIdentity, NormalizedFundamentals, FilingReference, AnalysisResult, PriceOnlyData, ScreenerRow
from ..schema.fundamentals import Period
from ..schema.filings import FilingType
from ..schema.explain import ExplainRequest, ExplainResult
from ..schema.options import OptionExpirations, OptionChain, GreeksResult
from ..services import company as company_service
from ..services import fundamentals as fundamentals_service
from ..services import price as price_service
from ..services import screener as screener_service
from ..services import explain as explain_service
from ..services import options as options_service
from ..services.company import CompanyLookupError, EXCHANGE_DISPLAY
from ..services.fundamentals import FundamentalsLookupError
from ..services.price import PriceLookupError
from ..services.options import OptionsLookupError
from ..services.universes import load_universe, UnknownUniverseError

router = APIRouter()

_adapters = {
    "edgar": EdgarAdapter(),
    "yfinance": YFinanceAdapter(),
}

_cache = LayeredCacheBackend()

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
    try:
        return await company_service.get_company_identity(adapter, _cache, ticker, source)
    except CompanyLookupError as e:
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
        return await fundamentals_service.get_fundamentals(adapter, _cache, ticker, source, period_enum, limit)
    except FundamentalsLookupError as e:
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


@router.post("/explain", response_model=ExplainResult)
async def explain_price_move(request: ExplainRequest):
    engine = _get_analysis_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="AI analysis not configured (GROQ_API_KEY missing)")
    try:
        return await explain_service.get_explanation(_cache, engine, request)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI explanation failed: {e}")


_SEARCH_TTL_SECONDS = 3600


@router.get("/search")
async def search_assets(q: str = Query(..., min_length=1, max_length=50)):
    q = q.strip()
    if not q:
        return []

    cache_key = f"search:{q.lower()}"
    raw = await _cache.get(cache_key)
    if raw is not None:
        return raw

    loop = asyncio.get_event_loop()

    def _sync_search():
        try:
            results = yf.Search(q, max_results=8).quotes
        except Exception:
            return []

        out = []
        for r in results:
            symbol = r.get("symbol") or r.get("ticker")
            if not symbol:
                continue
            name = (r.get("shortname") or r.get("longname")
                    or r.get("shortName") or r.get("longName") or symbol)
            quote_type = (r.get("quoteType") or "").upper()
            asset_type_map = {
                "EQUITY":         "equity",
                "CRYPTOCURRENCY": "crypto",
                "CURRENCY":       "forex",
                "FUTURE":         "commodity",
                "INDEX":          "index",
                "ETF":            "etf",
                "MUTUALFUND":     "fund",
            }
            asset_type = asset_type_map.get(quote_type, "equity")
            exchange = r.get("exchange") or r.get("exchDisp") or ""
            exchange = EXCHANGE_DISPLAY.get(exchange, exchange)
            sector = r.get("sector") or r.get("industry") or None

            out.append({
                "ticker":     symbol,
                "name":       name,
                "exchange":   exchange,
                "asset_type": asset_type,
                "sector":     sector,
            })
        return out

    results = await loop.run_in_executor(None, _sync_search)
    if results:
        await _cache.set(cache_key, results, _SEARCH_TTL_SECONDS,
                         data_type="search", ticker=q, source="yfinance")
    return results


@router.get("/assets/{ticker}/price", response_model=PriceOnlyData)
async def get_asset_price(ticker: str):
    try:
        return await price_service.get_price(_cache, ticker)
    except PriceLookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/screener/universes/{key}")
async def get_screener_universe(key: str):
    try:
        return load_universe(key)
    except UnknownUniverseError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/screener/{universe_key}/rows", response_model=List[ScreenerRow])
async def get_screener_rows(universe_key: str):
    adapter = _get_adapter("yfinance")
    try:
        return await screener_service.get_screener_rows(adapter, _cache, universe_key, "yfinance")
    except UnknownUniverseError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/options/{ticker}/expirations", response_model=OptionExpirations)
async def get_option_expirations(ticker: str):
    return await options_service.get_expirations(_cache, ticker)


@router.get("/options/{ticker}/chain", response_model=OptionChain)
async def get_option_chain(
    ticker: str,
    expiration: str = Query(..., description="Expiration date, YYYY-MM-DD"),
):
    try:
        return await options_service.get_chain(_cache, ticker, expiration)
    except OptionsLookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/options/{ticker}/calculate", response_model=GreeksResult)
async def calculate_option_greeks(
    ticker: str,
    expiration: str = Query(..., description="Expiration date, YYYY-MM-DD"),
    strike: float = Query(...),
    type: str = Query(..., description="call or put"),
    iv: Optional[float] = Query(default=None, description="Override implied volatility (decimal, e.g. 0.25)"),
):
    try:
        return await options_service.calculate(_cache, ticker, expiration, strike, type, iv)
    except OptionsLookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
