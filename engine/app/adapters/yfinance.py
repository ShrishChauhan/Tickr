# yfinance adapter — fetches prices and basic fundamentals via the yfinance library
# TODO(Phase 1): implement get_company, get_fundamentals, get_filings
from typing import List, Optional
from .base import DataAdapter
from ..schema import CompanyIdentity, NormalizedFundamentals, FilingReference
from ..schema.fundamentals import Period
from ..schema.filings import FilingType


class YFinanceAdapter(DataAdapter):
    @property
    def source_name(self) -> str:
        return "yfinance"

    async def get_company(self, ticker: str, market: str = "US") -> CompanyIdentity:
        raise NotImplementedError("TODO(Phase 1): implement yfinance company lookup")

    async def get_fundamentals(
        self,
        company: CompanyIdentity,
        period: Period = Period.ANNUAL,
        limit: int = 5,
    ) -> List[NormalizedFundamentals]:
        raise NotImplementedError("TODO(Phase 1): implement yfinance fundamentals")

    async def get_filings(
        self,
        company: CompanyIdentity,
        filing_types: Optional[List[FilingType]] = None,
        limit: int = 10,
    ) -> List[FilingReference]:
        raise NotImplementedError("TODO(Phase 1): yfinance does not provide filings — use EDGAR adapter")
