# Provider registry — (data_type, asset_class) -> ordered Loader list, first success wins.
# Fundamentals/company identity still go through DataAdapter directly
# (adapters/base.py) — that's an explicit user choice via ?source=, not a
# resilience fallback. yfinance is the universal quote fallback today; B4
# (Finnhub) prepends a class-specific provider with no changes to get_quote()'s
# call sites. B6 (FX) evaluated free sources and found none beat yfinance's
# own forex data — no provider added.
#
# Key is (data_type, asset_class), not asset_class alone — this is the ARCHITECTURE.md
# §4/§6/§9-specified shape. "quote" chains are keyed by asset class; the
# risk-free-rate chain uses the "global" sentinel since the rate itself is
# asset-class-agnostic. Unlike get_quote(), get_risk_free_rate() re-raises on
# total failure rather than swallowing to None/[] — see its docstring.
from typing import Optional

from ..adapters.yfinance import YFinanceQuoteProvider, YFinanceOptionsProvider
from ..adapters.coinbase import CoinbaseQuoteProvider
from ..adapters.finnhub import FinnhubQuoteProvider
from ..adapters.fred import FredRiskFreeRateProvider
from ..adapters.parquet_history import ParquetOHLCLoader

_yfinance_quote_provider = YFinanceQuoteProvider()
_coinbase_quote_provider = CoinbaseQuoteProvider()
_finnhub_quote_provider = FinnhubQuoteProvider()
_yfinance_options_provider = YFinanceOptionsProvider()
_fred_risk_free_provider = FredRiskFreeRateProvider()
_parquet_ohlc_loader = ParquetOHLCLoader()

_REGISTRY = {
    ("quote", "crypto"):    [_coinbase_quote_provider, _yfinance_quote_provider],  # B3
    ("quote", "forex"):     [_yfinance_quote_provider],   # B6 evaluated Frankfurter/exchangerate-api: both daily-only, worse than yfinance's minute-level forex data — no provider added, see PROGRESS.md
    ("quote", "commodity"): [_yfinance_quote_provider],
    ("quote", "index"):     [_yfinance_quote_provider],
    ("quote", "equity"):    [_finnhub_quote_provider, _yfinance_quote_provider],  # B4
    ("risk_free_rate", "global"): [_fred_risk_free_provider, _yfinance_options_provider],  # Phase 9.1
    ("ohlc", "equity"):     [_yfinance_quote_provider, _parquet_ohlc_loader],  # Phase 9.2 (Chunk 3)
}


def infer_asset_type_from_ticker(ticker: str) -> str:
    """Cheap ticker-syntax guess (yfinance's own suffix conventions) used only to
    pick a provider list — asset_type isn't known until a provider actually
    resolves the ticker. The authoritative asset_type in the response still comes
    from whichever provider serves the quote."""
    t = ticker.upper()
    if t.startswith("^"):
        return "index"
    if t.endswith("=F"):
        return "commodity"
    if t.endswith("=X"):
        return "forex"
    if "-USD" in t or "-USDT" in t or "-BTC" in t:
        return "crypto"
    return "equity"


async def get_quote(ticker: str) -> Optional[dict]:
    asset_type = infer_asset_type_from_ticker(ticker)
    for provider in _REGISTRY.get(("quote", asset_type), [_yfinance_quote_provider]):
        try:
            result = await provider.get_quote(ticker)
        except Exception:
            continue
        if result is not None:
            result["source"] = provider.name
            return result
    return None


async def get_risk_free_rate() -> tuple[float, Optional[str], str]:
    """(rate, as_of, source). Unlike get_quote(), re-raises the last provider's
    exception if every provider in the chain fails, rather than returning None —
    a total risk-free-rate outage must fail loudly, not silently price options
    at a fabricated/zero rate. Provenance (source, as_of) is stamped here, not
    at the call site, per adapters/base.py's provenance convention."""
    last_exc: Optional[Exception] = None
    for provider in _REGISTRY[("risk_free_rate", "global")]:
        try:
            rate, as_of = await provider.get_risk_free_rate()
        except Exception as e:
            last_exc = e
            continue
        return rate, as_of, provider.name
    raise last_exc


async def get_equity_ohlc(ticker: str) -> tuple[list[dict], Optional[str], Optional[str]]:
    """(bars, as_of, source). Historical OHLC bars for equities. Finnhub (the
    equity quote provider) never returns bars (see adapters/finnhub.py) — this
    chain is independent of which provider served the live quote.

    An empty bar list is treated the same as a raise (this provider declined/
    had nothing) and falls through to the next link — matching get_quote()'s
    None-means-decline semantics. Total failure preserves the pre-refactor
    contract exactly: ([], None, None), not None — callers that do
    `if not result.ohlc` must keep working unchanged."""
    for provider in _REGISTRY[("ohlc", "equity")]:
        try:
            bars, as_of = await provider.get_ohlc(ticker)
        except Exception:
            continue
        if bars:
            return bars, as_of, provider.name
    return [], None, None
