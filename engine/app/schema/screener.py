from typing import Optional

from pydantic import BaseModel


class ScreenerFields(BaseModel):
    currency: Optional[str] = None
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    net_margin: Optional[float] = None
    roe: Optional[float] = None
    debt_to_equity: Optional[float] = None
    gross_margin: Optional[float] = None
    revenue: Optional[float] = None
    free_cash_flow: Optional[float] = None  # always null — no .info equivalent, see CLAUDE.md lessons


class ScreenerRow(ScreenerFields):
    ticker: str
    name: str
