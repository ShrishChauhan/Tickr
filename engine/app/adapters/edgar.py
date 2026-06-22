# SEC EDGAR adapter — fetches filings and XBRL financials via edgartools
# TODO(Phase 1): implement get_company, get_fundamentals, get_filings
from typing import List, Optional
from .base import DataAdapter
from ..schema import CompanyIdentity, NormalizedFundamentals, FilingReference
from ..schema.fundamentals import Period
from ..schema.filings import FilingType


class EdgarAdapter(DataAdapter):
    @property
    def source_name(self) -> str:
        return "edgar"

    async def get_company(self, ticker: str, market: str = "US") -> CompanyIdentity:
        raise NotImplementedError("TODO(Phase 1): implement EDGAR company lookup")

    async def get_fundamentals(
        self,
        company: CompanyIdentity,
        period: Period = Period.ANNUAL,
        limit: int = 5,
    ) -> List[NormalizedFundamentals]:
        raise NotImplementedError("TODO(Phase 1): implement EDGAR fundamentals via XBRL")

    async def get_filings(
        self,
        company: CompanyIdentity,
        filing_types: Optional[List[FilingType]] = None,
        limit: int = 10,
    ) -> List[FilingReference]:
        raise NotImplementedError("TODO(Phase 1): implement EDGAR filing search")
