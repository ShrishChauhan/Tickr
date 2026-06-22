# Normalized financial statements and ratios — market-neutral, all values in declared currency
from enum import Enum
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel
from .company import CompanyIdentity, Currency


class Period(str, Enum):
    ANNUAL = "annual"
    QUARTERLY = "quarterly"
    TTM = "ttm"


class IncomeStatement(BaseModel):
    revenue: Optional[float] = None
    cost_of_revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    ebitda: Optional[float] = None
    net_income: Optional[float] = None
    eps_basic: Optional[float] = None
    eps_diluted: Optional[float] = None
    shares_outstanding_basic: Optional[float] = None
    shares_outstanding_diluted: Optional[float] = None


class BalanceSheet(BaseModel):
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_equity: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    total_debt: Optional[float] = None
    net_debt: Optional[float] = None
    goodwill: Optional[float] = None
    intangible_assets: Optional[float] = None


class CashFlowStatement(BaseModel):
    operating_cash_flow: Optional[float] = None
    capital_expenditures: Optional[float] = None
    free_cash_flow: Optional[float] = None
    investing_cash_flow: Optional[float] = None
    financing_cash_flow: Optional[float] = None
    dividends_paid: Optional[float] = None


class Ratios(BaseModel):
    # Valuation — may come from source or be derived by the engine
    pe_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    ev_ebitda: Optional[float] = None
    ev_revenue: Optional[float] = None
    # Profitability
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    roic: Optional[float] = None
    # Leverage
    debt_to_equity: Optional[float] = None
    debt_to_ebitda: Optional[float] = None
    interest_coverage: Optional[float] = None
    # Liquidity
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None


class NormalizedFundamentals(BaseModel):
    company: CompanyIdentity
    period: Period
    fiscal_year: Optional[int] = None
    fiscal_quarter: Optional[int] = None    # 1–4; None for annual/TTM
    period_end_date: date
    currency: Currency                      # all monetary values denominated in this currency
    income_statement: IncomeStatement
    balance_sheet: BalanceSheet
    cash_flow: CashFlowStatement
    ratios: Ratios
    source: str                             # "edgar" | "yfinance" | …
    fetched_at: datetime
    as_reported_currency: Optional[Currency] = None  # set if source currency differs from company.currency
