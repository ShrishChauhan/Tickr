# Abstract adapter contract — every data source implements this; engine never calls sources directly
from abc import ABC, abstractmethod
from typing import List, Optional
from ..schema import CompanyIdentity, NormalizedFundamentals, FilingReference
from ..schema.fundamentals import Period
from ..schema.filings import FilingType


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
