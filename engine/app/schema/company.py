# Company identity model — every security carries market, exchange, and currency explicitly
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class Market(str, Enum):
    US = "US"
    IN = "IN"          # Phase 4


class Exchange(str, Enum):
    NYSE = "NYSE"
    NASDAQ = "NASDAQ"
    AMEX = "AMEX"
    NSE = "NSE"        # Phase 4
    BSE = "BSE"        # Phase 4


class Currency(str, Enum):
    USD = "USD"
    INR = "INR"        # Phase 4


class CompanyIdentity(BaseModel):
    ticker: str                         # exchange-scoped symbol: "AAPL", "RELIANCE"
    name: str
    market: Market
    exchange: Exchange
    currency: Currency                  # primary reporting currency
    cik: Optional[str] = None           # SEC CIK — US only
    isin: Optional[str] = None
    lei: Optional[str] = None
