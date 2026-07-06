# Source-driven freshness classification — labels read whichever source actually
# served a response, so B3 (Coinbase)/B4 (Finnhub) light up "Real-time" automatically
# later without touching call sites.
from typing import TypedDict

DELAYED_SOURCES = {"yfinance", "edgar"}
REAL_TIME_SOURCES: set[str] = {"coinbase"}  # B4 adds "finnhub"


class Freshness(TypedDict):
    is_delayed: bool
    freshness_label: str


def classify_freshness(source: str) -> Freshness:
    if source in REAL_TIME_SOURCES:
        return {"is_delayed": False, "freshness_label": "Real-time"}
    return {"is_delayed": True, "freshness_label": "~15 min delayed"}
