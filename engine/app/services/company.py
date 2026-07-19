# Cache-orchestration + normalization for company identity — extracted from routes.py
import asyncio
from typing import Optional

import yfinance as yf

from ..adapters.base import DataAdapter
from ..cache.base import CacheBackend
from ..cache.ttl_config import COMPANY_INFO_TTL_SECONDS
from ..schema import CompanyIdentity
from ..schema.company import Currency, Exchange, Market

# NOTE: adapters/yfinance.py's _EXCHANGE_MAP is an independently-maintained
# duplicate of this map (raw yfinance exchange code -> Exchange, via a display
# string here vs. direct enum there — not kept in sync by any test) — e.g. this
# map carries "CCC"/"CCY" entries _EXCHANGE_MAP lacks (crypto/forex, out of
# _EXCHANGE_MAP's equity-only scope), while _EXCHANGE_MAP carries "NYE"/"PCX"/
# "ASQ" entries this map lacks. Drift is real and active, not theoretical —
# not resolved here, just flagged.
EXCHANGE_DISPLAY = {
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ",
    "NYQ": "NYSE",   "ASE": "AMEX",
    "LSE": "LSE",    "IOB": "LSE",
    "GER": "XETRA",  "DEX": "XETRA", "ETR": "XETRA",
    "TYO": "TSE",    "OSA": "TSE",
    "NSI": "NSE",    "BSE": "BSE",    "BOM": "BSE",
    "SAO": "B3",     "MEX": "BMV",
    "CCC": "Crypto", "CCY": "Forex",
    "TOR": "TSX",    "ASX": "ASX",    "EBS": "SIX",
    "KSC": "KOSPI",  "KOE": "KOSDAQ",
    "TAI": "TWSE",   "HKG": "HKEX",
    "SHH": "SSE",    "SHZ": "SZSE",
    "SAU": "TADAWUL",
    "JNB": "JSE",
    "PAR": "EURONEXT_PARIS",  "AMS": "EURONEXT_AMSTERDAM", "BRU": "EURONEXT_BRUSSELS",
    "ISE": "EURONEXT_DUBLIN", "LIS": "EURONEXT_LISBON",    "MIL": "EURONEXT_MILAN",
    "OSL": "EURONEXT_OSLO",   "ATH": "EURONEXT_ATHENS",
    "CPH": "NASDAQ_COPENHAGEN", "STO": "NASDAQ_STOCKHOLM", "HEL": "NASDAQ_HELSINKI",
    "TAL": "NASDAQ_TALLINN",    "RIS": "NASDAQ_RIGA",      "LIT": "NASDAQ_VILNIUS",
    "ICE": "NASDAQ_ICELAND",
}

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
    "CAD": Market.CA,
    "AUD": Market.AU,
    "CHF": Market.CH,
    "KRW": Market.KR,
    "TWD": Market.TW,
    "HKD": Market.HK,
    "CNY": Market.CN,
    "SAR": Market.SA,
    "ZAR": Market.ZA,
    "NOK": Market.NO,
    "DKK": Market.DK,
    "SEK": Market.SE,
    "ISK": Market.IS,
}


class CompanyLookupError(Exception):
    """Carries the original adapter exception's message, so routes.py can
    reproduce HTTPException(404, detail=str(original_exc)) unchanged."""


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


async def get_company_identity(
    adapter: DataAdapter,
    cache: CacheBackend,
    ticker: str,
    source: str,
) -> CompanyIdentity:
    ticker = ticker.upper()
    cache_key = f"{source}:company:{ticker}"

    raw = await cache.get(cache_key)
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
            raise CompanyLookupError(str(original_exc)) from original_exc

        await cache.set(cache_key, identity.model_dump(mode="json"), COMPANY_INFO_TTL_SECONDS,
                         data_type="company", ticker=ticker, source=source)
        return identity

    await cache.set(cache_key, result.model_dump(mode="json"), COMPANY_INFO_TTL_SECONDS,
                     data_type="company", ticker=ticker, source=source)
    return result
