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
    Capability-specific protocols (QuoteProvider, RateProvider, ...) extend
    this rather than every source implementing one do-everything interface —
    Coinbase doesn't do fundamentals, FRED doesn't do quotes."""

    name: str
    license: LoaderLicense


# Provenance convention, binding for all future loaders:
#   `source`          — when the schema *is* one loader's whole payload (PriceOnlyData.source)
#   `<field>_source`   — when a loader's answer is one field in a larger, multi-sourced schema
#                         (GreeksInputs.r_source)
#   `<field>_as_of`    — always paired with `<field>_source`; the source's own notion of
#                         currency when it has one (FRED's observation date), else a
#                         fetch-time timestamp (yfinance quotes)
# Every chain-walk stamps provenance in provider_registry.py itself, never at the call site.


class DataAdapter(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Short identifier for this source, e.g. 'edgar', 'yfinance'."""
        ...

    @property
    @abstractmethod
    def license(self) -> LoaderLicense:
        """LoaderLicense classification for this source — see LoaderLicense above."""
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


class RateProvider(Loader, Protocol):
    """Risk-free-rate sources — asset-class-agnostic (registry key is
    ("risk_free_rate", "global")), unlike QuoteProvider's per-asset-class chains."""

    name: str  # becomes GreeksInputs.r_source downstream

    async def get_risk_free_rate(self) -> tuple[float, Optional[str]]:
        """Return (rate, as_of) where as_of is the source's own observation
        date if it has one (FRED), else None (yfinance ^IRX has no finer-grained
        as-of of its own). Raising signals unavailability; unlike QuoteProvider's
        chain, the registry walker re-raises if every provider in the chain
        fails rather than returning a fallback value — a total outage must not
        silently price options at a fabricated/zero rate."""
        ...
