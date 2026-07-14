from typing import Optional
from pydantic import BaseModel


class OptionContract(BaseModel):
    strike: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    last_price: Optional[float] = None
    volume: Optional[float] = None
    open_interest: Optional[float] = None
    implied_volatility: Optional[float] = None
    # When this contract last traded — the actual basis for implied_volatility
    # (yfinance derives it from the last trade, not the live book), so this is
    # what explains IV staleness, separate from our own cache freshness.
    last_trade_date: Optional[str] = None


class OptionChain(BaseModel):
    ticker: str
    expiration: str
    calls: list[OptionContract] = []
    puts: list[OptionContract] = []
    fetched_at: str


class OptionExpirations(BaseModel):
    ticker: str
    available: bool
    expirations: list[str] = []


class GreeksInputs(BaseModel):
    """Transparency echo of the exact inputs priced — lets a user or a future
    debugging session sanity-check the calculation themselves. The *_as_of
    fields are our own cache freshness (bounded by TTL); contract_last_trade_at
    is the separate, unbounded staleness of the vendor's IV itself, which can
    lag far behind even a perfectly fresh cache fetch for thin contracts."""
    S: float
    K: float
    T: float
    r: float
    q: float
    sigma: float
    price_as_of: str
    iv_as_of: str
    r_as_of: str
    # Which provider produced the current risk-free rate ("fred" or
    # "yfinance") — FRED is authoritative but daily/lagged; yfinance ^IRX is
    # the resilience-chain fallback. Disclosed so r_as_of's meaning is clear.
    r_source: str
    contract_last_trade_at: Optional[str] = None


class GreeksExplanations(BaseModel):
    delta: str
    gamma: str
    theta: str
    vega: str
    rho: str


class GreeksResult(BaseModel):
    ticker: str
    expiration: str
    option_type: str  # "call" or "put"
    price: float
    delta: float
    gamma: float
    theta_per_day: float
    vega: float
    rho_per_percent: float
    explanations: GreeksExplanations
    inputs_used: GreeksInputs
