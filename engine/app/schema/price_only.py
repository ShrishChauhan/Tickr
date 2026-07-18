from pydantic import BaseModel, computed_field
from typing import Optional
from datetime import date
from .freshness import classify_freshness


class OHLCBar(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


class PriceOnlyData(BaseModel):
    ticker: str
    name: str
    asset_type: str
    currency: str
    current_price: Optional[float] = None
    change_24h: Optional[float] = None
    change_24h_pct: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    market_cap: Optional[float] = None
    volume_24h: Optional[float] = None
    circulating_supply: Optional[float] = None
    contract_month: Optional[str] = None
    ohlc: list[OHLCBar] = []
    fetched_at: str
    source: str = "yfinance"
    # Additive (Phase 9.2 / Chunk 3) — default None so cached rows written
    # before these fields existed still deserialize without error.
    ohlc_source: Optional[str] = None
    ohlc_as_of: Optional[str] = None

    @computed_field
    @property
    def is_delayed(self) -> bool:
        return classify_freshness(self.source)["is_delayed"]

    @computed_field
    @property
    def freshness_label(self) -> str:
        return classify_freshness(self.source)["freshness_label"]
