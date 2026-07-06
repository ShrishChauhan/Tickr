# Provider registry — (asset_type) -> ordered QuoteProvider list, first success wins.
# Only price/quote data flows through here; fundamentals/company identity still go
# through DataAdapter directly (adapters/base.py). yfinance is the universal
# fallback today; B3 (Binance)/B4 (Finnhub)/B6 (FX) will prepend class-specific
# providers to the relevant bucket with no changes to get_quote()'s call sites.
from typing import Optional

from ..adapters.yfinance import YFinanceQuoteProvider

_yfinance_quote_provider = YFinanceQuoteProvider()

_REGISTRY = {
    "crypto":    [_yfinance_quote_provider],   # B3 will prepend Binance here
    "forex":     [_yfinance_quote_provider],   # B6 will prepend a free FX source here
    "commodity": [_yfinance_quote_provider],
    "index":     [_yfinance_quote_provider],
    "equity":    [_yfinance_quote_provider],   # B4 will prepend Finnhub here
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
    for provider in _REGISTRY.get(asset_type, [_yfinance_quote_provider]):
        try:
            result = await provider.get_quote(ticker)
        except Exception:
            continue
        if result is not None:
            result["source"] = provider.name
            return result
    return None
