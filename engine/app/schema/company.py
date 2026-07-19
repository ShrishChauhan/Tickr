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
    CA = "CA"  # Canada
    AU = "AU"  # Australia
    CH = "CH"  # Switzerland
    KR = "KR"  # South Korea (KOSPI + KOSDAQ)
    TW = "TW"  # Taiwan
    HK = "HK"  # Hong Kong
    CN = "CN"  # China (Shanghai + Shenzhen)
    SA = "SA"  # Saudi Arabia
    ZA = "ZA"  # South Africa
    FR = "FR"  # France
    NL = "NL"  # Netherlands
    BE = "BE"  # Belgium
    IE = "IE"  # Ireland
    PT = "PT"  # Portugal
    IT = "IT"  # Italy
    NO = "NO"  # Norway
    GR = "GR"  # Greece


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
    TSX     = "TSX"     # Toronto Stock Exchange
    ASX     = "ASX"     # Australian Securities Exchange
    SIX     = "SIX"     # SIX Swiss Exchange
    KOSPI   = "KOSPI"   # Korea Exchange — main board
    KOSDAQ  = "KOSDAQ"  # Korea Exchange — KOSDAQ tier
    TWSE    = "TWSE"    # Taiwan Stock Exchange
    HKEX    = "HKEX"    # Hong Kong Stock Exchange
    SSE     = "SSE"     # Shanghai Stock Exchange
    SZSE    = "SZSE"    # Shenzhen Stock Exchange
    TADAWUL = "TADAWUL" # Saudi Exchange
    JSE     = "JSE"     # Johannesburg Stock Exchange
    EURONEXT_PARIS     = "EURONEXT_PARIS"
    EURONEXT_AMSTERDAM = "EURONEXT_AMSTERDAM"
    EURONEXT_BRUSSELS  = "EURONEXT_BRUSSELS"
    EURONEXT_DUBLIN    = "EURONEXT_DUBLIN"
    EURONEXT_LISBON    = "EURONEXT_LISBON"
    EURONEXT_MILAN     = "EURONEXT_MILAN"
    EURONEXT_OSLO      = "EURONEXT_OSLO"
    EURONEXT_ATHENS    = "EURONEXT_ATHENS"
    OTHER  = "OTHER"  # Fallback for unmapped exchanges


class Currency(str, Enum):
    USD = "USD"
    GBP = "GBP"
    EUR = "EUR"
    JPY = "JPY"
    INR = "INR"
    BRL = "BRL"
    MXN = "MXN"
    CAD = "CAD"
    AUD = "AUD"
    CHF = "CHF"
    KRW = "KRW"
    TWD = "TWD"
    HKD = "HKD"
    CNY = "CNY"
    SAR = "SAR"
    ZAR = "ZAR"
    NOK = "NOK"


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
