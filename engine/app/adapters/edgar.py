# SEC EDGAR adapter — fetches filings and XBRL financials via edgartools
import asyncio
import re
from datetime import date, datetime, timezone
from typing import List, Optional

import pandas as pd
import edgar
from edgar import CompanyNotFoundError

from .base import DataAdapter, LoaderLicense
from ..config import settings
from ..schema import CompanyIdentity, Market, Exchange, Currency
from ..schema import NormalizedFundamentals, Period, IncomeStatement, BalanceSheet, CashFlowStatement, Ratios
from ..schema import FilingReference, FilingType

_EXCHANGE_MAP = {
    "Nasdaq": Exchange.NASDAQ,
    "NASDAQ": Exchange.NASDAQ,
    "Nasdaq Global Select Market": Exchange.NASDAQ,
    "NYSE": Exchange.NYSE,
    "New York Stock Exchange": Exchange.NYSE,
    "NYSE American": Exchange.AMEX,
    "NYSE Amex": Exchange.AMEX,
    "American Stock Exchange": Exchange.AMEX,
    "AMEX": Exchange.AMEX,
}

_FILING_TYPE_MAP = {
    "10-K": FilingType.TEN_K,
    "10-Q": FilingType.TEN_Q,
    "8-K": FilingType.EIGHT_K,
    "DEF 14A": FilingType.DEF_14A,
}


def _get_value(df: pd.DataFrame, standard_concept: str, col: str) -> Optional[float]:
    """Extract the primary (non-abstract, non-breakdown) value for a standard_concept."""
    rows = df[
        (df["standard_concept"] == standard_concept)
        & (df["abstract"] == False)
        & (df["is_breakdown"] == False)
    ]
    if rows.empty:
        return None
    val = rows.iloc[0][col]
    if pd.isna(val):
        return None
    return float(val)


def _get_value_by_concept(df: pd.DataFrame, us_gaap_concept: str, col: str) -> Optional[float]:
    """Extract by raw XBRL concept name (fallback when no standard_concept mapping exists)."""
    rows = df[
        (df["concept"] == us_gaap_concept)
        & (df["abstract"] == False)
        & (df["is_breakdown"] == False)
    ]
    if rows.empty:
        return None
    val = rows.iloc[0][col]
    if pd.isna(val):
        return None
    return float(val)


def _parse_fy_col(col: str):
    """Parse an annual IS/CF column like '2025-09-27 (FY)' → (date, fiscal_year)."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})\s+\(FY\)", col)
    if not m:
        return None, None
    d = date.fromisoformat(m.group(1))
    return d, d.year


def _parse_q_col(col: str):
    """Parse a quarterly IS/CF column like '2026-03-28 (Q2)' → (date, quarter)."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})\s+\(Q(\d)\)", col)
    if not m:
        return None, None
    d = date.fromisoformat(m.group(1))
    return d, int(m.group(2))


def _build_income_statement(is_df: pd.DataFrame, col: str) -> IncomeStatement:
    g = lambda sc: _get_value(is_df, sc, col)
    gc = lambda concept: _get_value_by_concept(is_df, concept, col)
    return IncomeStatement(
        revenue=g("Revenue"),
        cost_of_revenue=g("CostOfGoodsAndServicesSold"),
        gross_profit=g("GrossProfit"),
        operating_income=g("OperatingIncomeLoss"),
        ebitda=None,  # derived below if possible
        net_income=g("NetIncome"),
        eps_basic=gc("us-gaap_EarningsPerShareBasic"),
        eps_diluted=gc("us-gaap_EarningsPerShareDiluted"),
        shares_outstanding_basic=g("SharesAverage"),
        shares_outstanding_diluted=g("SharesFullyDilutedAverage"),
    )


def _build_balance_sheet(bs_df: pd.DataFrame, col: str) -> BalanceSheet:
    g = lambda sc: _get_value(bs_df, sc, col)
    equity = g("AllEquityBalance")
    liabilities = g("Liabilities")

    # Primary: "Assets" standard_concept. For financial institutions (banks, insurers),
    # XBRL sometimes maps "Assets" to a sub-line rather than total assets. Fall back
    # to "LiabilitiesAndEquity" which always equals total assets by accounting identity.
    total_assets = g("Assets")
    liabilities_and_equity = g("LiabilitiesAndEquity")
    if total_assets is None or (
        equity is not None
        and liabilities is not None
        and total_assets < equity + liabilities * 0.5
    ):
        total_assets = liabilities_and_equity

    long_term_debt = g("LongTermDebt")
    current_debt = g("CurrentPortionOfLongTermDebt")
    short_term_debt = g("ShortTermDebt")
    cash = g("CashAndMarketableSecurities")

    components = [x for x in [long_term_debt, current_debt, short_term_debt] if x is not None]
    total_debt = sum(components) if components else None
    net_debt = (total_debt - cash) if (total_debt is not None and cash is not None) else None

    return BalanceSheet(
        total_assets=total_assets,
        total_liabilities=liabilities,
        total_equity=equity,
        cash_and_equivalents=cash,
        total_debt=total_debt,
        net_debt=net_debt,
        goodwill=g("Goodwill"),
        intangible_assets=g("OtherIntangibleAssets") or g("IntangibleAssets"),
    )


def _build_cash_flow(cf_df: pd.DataFrame, col: str) -> CashFlowStatement:
    g = lambda sc: _get_value(cf_df, sc, col)
    opcf = g("NetCashFromOperatingActivities")
    capex = g("CapitalExpenses")  # stored as negative in XBRL
    free_cf = (opcf + capex) if (opcf is not None and capex is not None) else None
    dividends = g("DistributionsToMinorityInterests")

    return CashFlowStatement(
        operating_cash_flow=opcf,
        capital_expenditures=capex,
        free_cash_flow=free_cf,
        investing_cash_flow=g("NetCashFromInvestingActivities"),
        financing_cash_flow=g("NetCashFromFinancingActivities"),
        dividends_paid=dividends,
    )


def _derive_ebitda(is_stmt: IncomeStatement, cf_stmt: CashFlowStatement, cf_df: pd.DataFrame, col: str) -> Optional[float]:
    """EBITDA = operating_income + D&A (from cash flow statement)."""
    if is_stmt.operating_income is None:
        return None
    da = _get_value(cf_df, "DepreciationExpense", col)
    if da is None:
        return None
    return is_stmt.operating_income + abs(da)


def _resolve_exchange(exchanges: List[str]) -> Exchange:
    for ex in exchanges:
        mapped = _EXCHANGE_MAP.get(ex)
        if mapped:
            return mapped
    return Exchange.NASDAQ  # default for US


def _resolve_bs_col(bs_df: pd.DataFrame, period_date: date) -> Optional[str]:
    """Find the balance sheet column matching a given date (BS cols have no period suffix)."""
    date_str = period_date.isoformat()
    for col in bs_df.columns:
        if col == date_str:
            return col
    # Tolerate small date differences (within 5 days — fiscal calendars vary)
    for col in bs_df.columns:
        m = re.match(r"(\d{4}-\d{2}-\d{2})$", col)
        if m:
            col_date = date.fromisoformat(m.group(1))
            if abs((col_date - period_date).days) <= 5:
                return col
    return None


class EdgarAdapter(DataAdapter):
    def __init__(self):
        edgar.set_identity(settings.SEC_IDENTITY)

    @property
    def source_name(self) -> str:
        return "edgar"

    @property
    def license(self) -> LoaderLicense:
        return LoaderLicense.COMMERCIAL_OK  # public-domain SEC data

    async def get_company(self, ticker: str, market: str = "US") -> CompanyIdentity:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_get_company, ticker)

    def _sync_get_company(self, ticker: str) -> CompanyIdentity:
        c = edgar.Company(ticker)  # raises CompanyNotFoundError if not found
        exchanges = c.get_exchanges() or []
        exchange = _resolve_exchange(exchanges)
        return CompanyIdentity(
            ticker=c.get_ticker() or ticker.upper(),
            name=c.name,
            market=Market.US,
            exchange=exchange,
            currency=Currency.USD,
            cik=str(c.cik),
        )

    async def get_fundamentals(
        self,
        company: CompanyIdentity,
        period: Period = Period.ANNUAL,
        limit: int = 5,
    ) -> List[NormalizedFundamentals]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_get_fundamentals, company, period, limit)

    def _sync_get_fundamentals(
        self, company: CompanyIdentity, period: Period, limit: int
    ) -> List[NormalizedFundamentals]:
        c = edgar.Company(company.ticker)
        results = []

        if period == Period.ANNUAL:
            fin = c.get_financials()
            if fin is None:
                return []
            results = self._extract_annual(fin, company, limit)

        elif period == Period.QUARTERLY:
            # Iterate through 10-Q filings; each gives one quarter's data
            tenq_list = c.get_filings(form="10-Q").to_pandas()
            for _, row in tenq_list.head(limit).iterrows():
                if len(results) >= limit:
                    break
                try:
                    filing_obj = c.get_filings(form="10-Q").get(
                        tenq_list.index.get_loc(row.name)
                    )
                    fin_q = filing_obj.obj().financials
                    if fin_q is None:
                        continue
                    quarters = self._extract_quarters(fin_q, company, max_periods=1)
                    results.extend(quarters)
                except Exception:
                    continue

        return results[:limit]

    def _extract_annual(
        self, fin, company: CompanyIdentity, limit: int
    ) -> List[NormalizedFundamentals]:
        """Extract up to `limit` annual periods from a Financials object."""
        try:
            is_df = fin.income_statement().to_dataframe()
            bs_obj = fin.balance_sheet()
            bs_df = bs_obj.to_dataframe() if bs_obj else pd.DataFrame()
            cf_df = fin.cash_flow_statement().to_dataframe()
        except Exception:
            return []

        # IS/CF columns: "YYYY-MM-DD (FY)"
        fy_cols = [c for c in is_df.columns if re.match(r"\d{4}-\d{2}-\d{2}\s+\(FY\)", c)]
        results = []
        now = datetime.now(timezone.utc)

        for col in fy_cols[:limit]:
            period_date, fiscal_year = _parse_fy_col(col)
            if period_date is None:
                continue

            is_stmt = _build_income_statement(is_df, col)
            bs_col = _resolve_bs_col(bs_df, period_date) if not bs_df.empty else None
            bs_stmt = _build_balance_sheet(bs_df, bs_col) if bs_col else BalanceSheet()
            cf_stmt = _build_cash_flow(cf_df, col)
            ebitda = _derive_ebitda(is_stmt, cf_stmt, cf_df, col)
            is_stmt = is_stmt.model_copy(update={"ebitda": ebitda})

            results.append(
                NormalizedFundamentals(
                    company=company,
                    period=Period.ANNUAL,
                    fiscal_year=fiscal_year,
                    fiscal_quarter=None,
                    period_end_date=period_date,
                    currency=Currency.USD,
                    income_statement=is_stmt,
                    balance_sheet=bs_stmt,
                    cash_flow=cf_stmt,
                    ratios=Ratios(),
                    source=self.source_name,
                    fetched_at=now,
                )
            )
        return results

    def _extract_quarters(
        self, fin, company: CompanyIdentity, max_periods: int = 2
    ) -> List[NormalizedFundamentals]:
        """Extract quarterly periods from a Financials object (from a 10-Q filing)."""
        try:
            is_df = fin.income_statement().to_dataframe()
            bs_obj = fin.balance_sheet()
            bs_df = bs_obj.to_dataframe() if bs_obj else pd.DataFrame()
            cf_df = fin.cash_flow_statement().to_dataframe()
        except Exception:
            return []

        # IS/CF columns: "YYYY-MM-DD (Q#)"
        q_cols = [c for c in is_df.columns if re.match(r"\d{4}-\d{2}-\d{2}\s+\(Q\d\)", c)]
        results = []
        now = datetime.now(timezone.utc)

        for col in q_cols[:max_periods]:
            period_date, quarter = _parse_q_col(col)
            if period_date is None:
                continue

            is_stmt = _build_income_statement(is_df, col)
            bs_col = _resolve_bs_col(bs_df, period_date) if not bs_df.empty else None
            bs_stmt = _build_balance_sheet(bs_df, bs_col) if bs_col else BalanceSheet()
            cf_stmt = _build_cash_flow(cf_df, col)
            ebitda = _derive_ebitda(is_stmt, cf_stmt, cf_df, col)
            is_stmt = is_stmt.model_copy(update={"ebitda": ebitda})

            results.append(
                NormalizedFundamentals(
                    company=company,
                    period=Period.QUARTERLY,
                    fiscal_year=period_date.year,
                    fiscal_quarter=quarter,
                    period_end_date=period_date,
                    currency=Currency.USD,
                    income_statement=is_stmt,
                    balance_sheet=bs_stmt,
                    cash_flow=cf_stmt,
                    ratios=Ratios(),
                    source=self.source_name,
                    fetched_at=now,
                )
            )
        return results

    async def get_filings(
        self,
        company: CompanyIdentity,
        filing_types: Optional[List[FilingType]] = None,
        limit: int = 10,
    ) -> List[FilingReference]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_get_filings, company, filing_types, limit)

    def _sync_get_filings(
        self, company: CompanyIdentity, filing_types: Optional[List[FilingType]], limit: int
    ) -> List[FilingReference]:
        c = edgar.Company(company.ticker)

        # Build the form filter list
        if filing_types:
            forms = [ft.value for ft in filing_types if ft in _FILING_TYPE_MAP.values()]
            # Reverse map to get form strings
            inv_map = {v: k for k, v in _FILING_TYPE_MAP.items()}
            forms = [inv_map[ft] for ft in filing_types if ft in inv_map]
        else:
            forms = ["10-K", "10-Q", "8-K", "DEF 14A"]

        filings_df = c.get_filings(form=forms).to_pandas()
        now = datetime.now(timezone.utc)
        results = []

        for _, row in filings_df.head(limit).iterrows():
            form_str = str(row.get("form", ""))
            filing_type = _FILING_TYPE_MAP.get(form_str)
            if filing_type is None:
                continue

            filed_date_raw = row.get("filing_date")
            if filed_date_raw is None:
                continue
            if isinstance(filed_date_raw, str):
                filed_date = date.fromisoformat(filed_date_raw)
            else:
                filed_date = date(filed_date_raw.year, filed_date_raw.month, filed_date_raw.day)

            report_date_raw = row.get("reportDate")
            period_of_report = None
            if report_date_raw and report_date_raw != "":
                try:
                    if isinstance(report_date_raw, str):
                        period_of_report = date.fromisoformat(report_date_raw)
                    else:
                        period_of_report = date(report_date_raw.year, report_date_raw.month, report_date_raw.day)
                except Exception:
                    pass

            accession = str(row.get("accession_number", ""))
            cik = company.cik or ""
            # Build primary document URL
            primary_doc = str(row.get("primaryDocument", ""))
            acc_nodash = accession.replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{primary_doc}"

            results.append(
                FilingReference(
                    company=company,
                    filing_type=filing_type,
                    filed_date=filed_date,
                    period_of_report=period_of_report,
                    accession_number=accession,
                    url=url,
                    source=self.source_name,
                    fetched_at=now,
                )
            )

        return results
