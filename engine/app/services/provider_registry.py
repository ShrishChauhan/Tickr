# Provider registry — (data_type, asset_class) -> ordered Loader list, first success wins.
# Fundamentals/company identity still go through DataAdapter directly
# (adapters/base.py) — that's an explicit user choice via ?source=, not a
# resilience fallback. yfinance is the universal quote fallback today; B4
# (Finnhub) prepends a class-specific provider with no changes to get_quote()'s
# call sites. B6 (FX) evaluated free sources and found none beat yfinance's
# own forex data — no provider added.
#
# Key is (data_type, asset_class), not asset_class alone — this is the ARCHITECTURE.md
# §4/§6/§9-specified shape. Only "quote" is populated this chunk; future data
# types (risk-free rate, OHLC, ...) reuse the same tuple-keyed shape.
from typing import Optional

from ..adapters.yfinance import YFinanceQuoteProvider
from ..adapters.coinbase import CoinbaseQuoteProvider
from ..adapters.finnhub import FinnhubQuoteProvider

_yfinance_quote_provider = YFinanceQuoteProvider()
_coinbase_quote_provider = CoinbaseQuoteProvider()
_finnhub_quote_provider = FinnhubQuoteProvider()

_REGISTRY = {
    ("quote", "crypto"):    [_coinbase_quote_provider, _yfinance_quote_provider],  # B3
    ("quote", "forex"):     [_yfinance_quote_provider],   # B6 evaluated Frankfurter/exchangerate-api: both daily-only, worse than yfinance's minute-level forex data — no provider added, see PROGRESS.md
    ("quote", "commodity"): [_yfinance_quote_provider],
    ("quote", "index"):     [_yfinance_quote_provider],
    ("quote", "equity"):    [_finnhub_quote_provider, _yfinance_quote_provider],  # B4
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


async def get_equity_ohlc(ticker: str) -> list[dict]:
    """Historical OHLC bars for equities. Finnhub (the equity quote provider)
    never returns bars (see adapters/finnhub.py) — always goes to yfinance,
    regardless of which provider actually served the live quote."""
    try:
        return await _yfinance_quote_provider.get_ohlc(ticker)
    except Exception:
        return []
