# Company identity model — every security carries market, exchange, and currency explicitly
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class Market(str, Enum):
    US = "US"
    UK = "UK"
    DE = "DE"
    JP = "JP"
    IN = "IN"
    BR = "BR"
    MX = "MX"


class Exchange(str, Enum):
    NYSE   = "NYSE"
    NASDAQ = "NASDAQ"
    AMEX   = "AMEX"
    LSE    = "LSE"    # London Stock Exchange
    XETRA  = "XETRA" # Deutsche Börse / Frankfurt
    TSE    = "TSE"    # Tokyo Stock Exchange
    NSE    = "NSE"    # National Stock Exchange (India)
    BSE    = "BSE"    # Bombay Stock Exchange
    B3     = "B3"     # Brasil Bolsa Balcão
    BMV    = "BMV"    # Bolsa Mexicana de Valores
    OTHER  = "OTHER"  # Fallback for unmapped exchanges


class Currency(str, Enum):
    USD = "USD"
    GBP = "GBP"
    EUR = "EUR"
    JPY = "JPY"
    INR = "INR"
    BRL = "BRL"
    MXN = "MXN"


class CompanyIdentity(BaseModel):
    ticker: str                         # exchange-scoped symbol: "AAPL", "RELIANCE"
    name: str
    market: Market
    exchange: Exchange
    currency: Currency                  # primary reporting currency
    asset_type: str = "equity"          # "equity", "crypto", "forex", "commodity", "index"
    cik: Optional[str] = None           # SEC CIK — US only
    isin: Optional[str] = None
    lei: Optional[str] = None
