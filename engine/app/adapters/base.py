# Abstract adapter contract — every data source implements this; engine never calls sources directly
from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Optional, Protocol
from ..schema import CompanyIdentity, NormalizedFundamentals, FilingReference
from ..schema.fundamentals import Period
from ..schema.filings import FilingType


class LoaderLicense(str, Enum):
    """Metadata only this phase — no enforcement. Classifications (yfinance
    personal-only, EDGAR/FRED commercial-ok, Coinbase/Finnhub unclear pending
    ToS review) are judgment calls introduced by this refactor; no prior
    written policy exists to codify."""

    COMMERCIAL_OK = "commercial_ok"
    PERSONAL_ONLY = "personal_only"
    UNCLEAR = "unclear"


class Loader(Protocol):
    """Minimal common shape every data source structurally satisfies.
    Capability-specific protocols (QuoteProvider, ...) extend this rather
    than every source implementing one do-everything interface — Coinbase
    doesn't do fundamentals, FRED doesn't do quotes."""

    name: str
    license: LoaderLicense


# Provenance convention, binding for all future loaders:
#   `source`          — when the schema *is* one loader's whole payload (PriceOnlyData.source)
#   `<field>_source`   — when a loader's answer is one field in a larger, multi-sourced schema
#   `<field>_as_of`    — always paired with `<field>_source`; the source's own notion of
#                         currency when it has one, else a fetch-time timestamp
# Every chain-walk stamps provenance in provider_registry.py itself, never at the call site.


class DataAdapter(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Short identifier for this source, e.g. 'edgar', 'yfinance'."""
        ...

    @abstractmethod
    async def get_company(self, ticker: str, market: str = "US") -> CompanyIdentity:
        """Resolve a ticker symbol to a fully-populated CompanyIdentity."""
        ...

    @abstractmethod
    async def get_fundamentals(
        self,
        company: CompanyIdentity,
        period: Period = Period.ANNUAL,
        limit: int = 5,
    ) -> List[NormalizedFundamentals]:
        """Return normalized financials for `limit` most recent periods."""
        ...

    @abstractmethod
    async def get_filings(
        self,
        company: CompanyIdentity,
        filing_types: Optional[List[FilingType]] = None,
        limit: int = 10,
    ) -> List[FilingReference]:
        """Return filing references, newest first. None = all supported types."""
        ...


class QuoteProvider(Loader, Protocol):
    """Narrower than DataAdapter — real-time-ish quote sources (Binance, Finnhub)
    only ever serve price/quote data, never fundamentals/filings (no cheap free
    real-time fundamentals source exists)."""

    name: str  # becomes PriceOnlyData.source downstream

    async def get_quote(self, ticker: str) -> Optional[dict]:
        """Return a quote dict, or None if this provider can't/won't serve this
        ticker. Raising is also treated as a decline by the registry."""
        ...
