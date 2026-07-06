# API routes — thin HTTP layer; no business logic, only adapter dispatch + cache
# Cache key scheme:
#   {source}:company:{TICKER}
#   {source}:fundamentals:{TICKER}:{period}:{limit}
#   {source}:filings:{TICKER}:{limit}:{types_str}   (types_str = sorted comma-joined values or "all")
#   analysis:{TICKER}:{source}:{period}:{limit}
#   price:{TICKER}
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import yfinance as yf
from fastapi import APIRouter, HTTPException, Query

from ..adapters.edgar import EdgarAdapter
from ..adapters.yfinance import YFinanceAdapter
from ..analysis.interface import AnalysisEngine
from ..cache.layered import LayeredCacheBackend
from ..cache.ttl_config import (
    COMPANY_INFO_TTL_SECONDS,
    FUNDAMENTALS_TTL_SECONDS,
    FILING_REF_TTL_SECONDS,
    AI_ANALYSIS_TTL_SECONDS,
    PRICE_DATA_TTL_SECONDS,
)
from ..config import settings
from ..schema import CompanyIdentity, NormalizedFundamentals, FilingReference, AnalysisResult, PriceOnlyData, OHLCBar
from ..schema.company import Currency, Exchange, Market
from ..schema.fundamentals import Period
from ..schema.filings import FilingType
from ..utils.ratios import derive_ratios

router = APIRouter()

_adapters = {
    "edgar": EdgarAdapter(),
    "yfinance": YFinanceAdapter(),
}

_cache = LayeredCacheBackend()

_UNIVERSES_DIR = Path(__file__).resolve().parent.parent / "data" / "universes"
_UNIVERSES = {
    "dow30": json.loads((_UNIVERSES_DIR / "dow30.json").read_text(encoding="utf-8")),
    "nifty50": json.loads((_UNIVERSES_DIR / "nifty50.json").read_text(encoding="utf-8")),
    "nasdaq100": json.loads((_UNIVERSES_DIR / "nasdaq100.json").read_text(encoding="utf-8")),
    "sp500": json.loads((_UNIVERSES_DIR / "sp500.json").read_text(encoding="utf-8")),
}

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


_NON_EQUITY_QUOTE_TYPES = {"FUTURE", "CRYPTOCURRENCY", "CURRENCY", "INDEX", "ETF", "MUTUALFUND"}

_ASSET_TYPE_MAP = {
    "EQUITY":         "equity",
    "CRYPTOCURRENCY": "crypto",
    "CURRENCY":       "forex",
    "FUTURE":         "commodity",
    "INDEX":          "index",
    "ETF":            "etf",
    "MUTUALFUND":     "fund",
}

_CURRENCY_TO_MARKET = {
    "GBP": Market.UK,
    "EUR": Market.DE,
    "JPY": Market.JP,
    "INR": Market.IN,
    "BRL": Market.BR,
    "MXN": Market.MX,
}


def _build_non_equity_identity(ticker: str) -> Optional[CompanyIdentity]:
    info = yf.Ticker(ticker).info
    quote_type = (info.get("quoteType") or "").upper()
    if quote_type not in _NON_EQUITY_QUOTE_TYPES:
        return None

    name = info.get("shortName") or info.get("longName") or ticker

    raw_exchange = info.get("exchange") or ""
    exchange_display = EXCHANGE_DISPLAY.get(raw_exchange, raw_exchange)
    try:
        exchange = Exchange(exchange_display)
    except ValueError:
        exchange = Exchange.OTHER

    currency_str = (info.get("currency") or "USD").upper()
    try:
        currency = Currency(currency_str)
    except ValueError:
        currency = Currency.USD

    market = _CURRENCY_TO_MARKET.get(currency.value, Market.US)

    return CompanyIdentity(
        ticker=ticker,
        name=name,
        exchange=exchange,
        market=market,
        currency=currency,
        asset_type=_ASSET_TYPE_MAP.get(quote_type, "equity"),
        cik=None,
    )


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
    except Exception as original_exc:
        loop = asyncio.get_event_loop()
        try:
            identity = await loop.run_in_executor(None, _build_non_equity_identity, ticker)
        except Exception:
            identity = None

        if identity is None:
            raise HTTPException(status_code=404, detail=str(original_exc))

        await _cache.set(cache_key, identity.model_dump(mode="json"), COMPANY_INFO_TTL_SECONDS,
                         data_type="company", ticker=ticker, source=source)
        return identity

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
        items = [NormalizedFundamentals.model_validate(item) for item in raw]
        return [f.model_copy(update={"ratios": derive_ratios(f)}) for f in items]

    try:
        company = await adapter.get_company(ticker)
        result = await adapter.get_fundamentals(company, period_enum, limit)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    result = [f.model_copy(update={"ratios": derive_ratios(f)}) for f in result]
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


EXCHANGE_DISPLAY = {
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ",
    "NYQ": "NYSE",   "ASE": "AMEX",
    "LSE": "LSE",    "IOB": "LSE",
    "GER": "XETRA",  "DEX": "XETRA", "ETR": "XETRA",
    "TYO": "TSE",    "OSA": "TSE",
    "NSI": "NSE",    "BSE": "BSE",    "BOM": "BSE",
    "SAO": "B3",     "MEX": "BMV",
    "CCC": "Crypto", "CCY": "Forex",
}

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


_FUTURES_MONTH_CODE = {
    "F": "Jan", "G": "Feb", "H": "Mar", "J": "Apr",
    "K": "May", "M": "Jun", "N": "Jul", "Q": "Aug",
    "U": "Sep", "V": "Oct", "X": "Nov", "Z": "Dec",
}

_SHORT_MONTHS = {"Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"}


def _derive_contract_month(info: dict, base_ticker: str) -> Optional[str]:
    import re
    # 1. shortName often contains "Gold Aug 26" — extract "Mon YY/YYYY" pattern
    short_name = info.get("shortName") or ""
    m = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{2,4})', short_name)
    if m:
        month, yr = m.group(1), m.group(2)
        year = int(yr)
        if year < 100:
            year += 2000
        return f"{month} {year}"

    # 2. underlyingSymbol like "GCQ26.CMX" — parse month code
    underlying = info.get("underlyingSymbol") or ""
    root = base_ticker.rstrip("=F").upper()
    if underlying.upper().startswith(root):
        suffix = underlying[len(root):]
        suffix = suffix.split(".")[0]  # drop exchange suffix
        if len(suffix) >= 2:
            month_code = suffix[0].upper()
            year_digits = suffix[1:]
            month = _FUTURES_MONTH_CODE.get(month_code)
            if month and year_digits.isdigit():
                year = int(year_digits)
                if year < 100:
                    year += 2000
                return f"{month} {year}"

    # 3. expireDate as Unix timestamp
    expire = info.get("expireDate")
    if expire and isinstance(expire, (int, float)) and expire > 0:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(expire, tz=timezone.utc)
        return dt.strftime("%b %Y")

    return None


def _sync_fetch_price_data(ticker: str) -> PriceOnlyData:
    t = yf.Ticker(ticker)
    info = t.info

    def g(k):
        v = info.get(k)
        if v is None:
            return None
        try:
            f = float(v)
            import math
            return None if (math.isnan(f) or math.isinf(f)) else f
        except (TypeError, ValueError):
            return None

    name = info.get("longName") or info.get("shortName") or ticker
    currency = info.get("currency", "USD")
    quote_type = info.get("quoteType", "")
    asset_type_map = {
        "CRYPTOCURRENCY": "crypto",
        "CURRENCY": "forex",
        "FUTURE": "commodity",
        "INDEX": "index",
    }
    asset_type = asset_type_map.get(quote_type, "equity")

    current_price = g("currentPrice") or g("regularMarketPrice") or g("ask")
    change_24h = g("regularMarketChange")
    change_24h_pct = g("regularMarketChangePercent")
    high_52w = g("fiftyTwoWeekHigh")
    low_52w = g("fiftyTwoWeekLow")
    market_cap = g("marketCap")
    volume_24h = g("volume24Hr") or g("regularMarketVolume")
    circulating_supply = g("circulatingSupply")

    contract_month = None
    if asset_type == "commodity":
        contract_month = _derive_contract_month(info, ticker)

    hist = t.history(period="1y", interval="1d")
    ohlc_bars: list[OHLCBar] = []
    if hist is not None and not hist.empty:
        for ts, row in hist.iterrows():
            bar_date = ts.date() if hasattr(ts, "date") else ts
            try:
                ohlc_bars.append(OHLCBar(
                    date=bar_date,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]) if row["Volume"] else None,
                ))
            except (KeyError, TypeError, ValueError):
                continue

    return PriceOnlyData(
        ticker=ticker.upper(),
        name=name,
        asset_type=asset_type,
        currency=currency,
        current_price=current_price,
        change_24h=change_24h,
        change_24h_pct=change_24h_pct,
        high_52w=high_52w,
        low_52w=low_52w,
        market_cap=market_cap,
        volume_24h=volume_24h,
        circulating_supply=circulating_supply,
        contract_month=contract_month,
        ohlc=ohlc_bars,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/assets/{ticker}/price", response_model=PriceOnlyData)
async def get_asset_price(ticker: str):
    ticker = ticker.upper()
    cache_key = f"price:{ticker}"

    raw = await _cache.get(cache_key)
    if raw is not None:
        return PriceOnlyData.model_validate(raw)

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _sync_fetch_price_data, ticker)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    await _cache.set(
        cache_key,
        result.model_dump(mode="json"),
        PRICE_DATA_TTL_SECONDS,
        data_type="price",
        ticker=ticker,
        source="yfinance",
    )
    return result


@router.get("/screener/universes/{key}")
async def get_screener_universe(key: str):
    universe = _UNIVERSES.get(key)
    if universe is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown universe '{key}'. Valid: {', '.join(_UNIVERSES.keys())}",
        )
    return universe
