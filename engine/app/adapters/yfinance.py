# yfinance adapter — fetches fundamentals and ratios via the yfinance library
import asyncio
from datetime import date, datetime, timezone
from typing import List, Optional

import pandas as pd
import yfinance as yf

from .base import DataAdapter
from ..schema import CompanyIdentity, Market, Exchange, Currency
from ..schema import NormalizedFundamentals, Period, IncomeStatement, BalanceSheet, CashFlowStatement, Ratios
from ..schema import FilingReference, FilingType
from ..schema import ScreenerFields

_EXCHANGE_MAP = {
    # NASDAQ tiers
    "NMS": Exchange.NASDAQ,
    "NGM": Exchange.NASDAQ,
    "NCM": Exchange.NASDAQ,
    # NYSE
    "NYQ": Exchange.NYSE,
    "NYE": Exchange.NYSE,
    "PCX": Exchange.NYSE,   # NYSE Arca
    # AMEX
    "ASE": Exchange.AMEX,
    "ASQ": Exchange.AMEX,
    # Global (codes returned by yfinance — suffix map is primary; these are fallbacks)
    "LSE": Exchange.LSE,
    "IOB": Exchange.LSE,
    "GER": Exchange.XETRA,
    "DEX": Exchange.XETRA,
    "ETR": Exchange.XETRA,
    "TYO": Exchange.TSE,
    "OSA": Exchange.TSE,
    "NSI": Exchange.NSE,
    "BOM": Exchange.BSE,
    "SAO": Exchange.B3,
    "MEX": Exchange.BMV,
}

# Ticker suffix → (exchange, market, default_currency)
_SUFFIX_MAP: dict[str, tuple] = {
    ".L":  (Exchange.LSE,   Market.UK, Currency.GBP),
    ".DE": (Exchange.XETRA, Market.DE, Currency.EUR),
    ".T":  (Exchange.TSE,   Market.JP, Currency.JPY),
    ".NS": (Exchange.NSE,   Market.IN, Currency.INR),
    ".BO": (Exchange.BSE,   Market.IN, Currency.INR),
    ".SA": (Exchange.B3,    Market.BR, Currency.BRL),
    ".MX": (Exchange.BMV,   Market.MX, Currency.MXN),
}

_CURRENCY_MAP: dict[str, Currency] = {
    "USD": Currency.USD,
    "GBP": Currency.GBP,
    "EUR": Currency.EUR,
    "JPY": Currency.JPY,
    "INR": Currency.INR,
    "BRL": Currency.BRL,
    "MXN": Currency.MXN,
}

_CURRENCY_TO_MARKET: dict[Currency, Market] = {
    Currency.USD: Market.US,
    Currency.GBP: Market.UK,
    Currency.EUR: Market.DE,
    Currency.JPY: Market.JP,
    Currency.INR: Market.IN,
    Currency.BRL: Market.BR,
    Currency.MXN: Market.MX,
}

_FILING_TYPE_MAP = {
    "10-K": FilingType.TEN_K,
    "10-Q": FilingType.TEN_Q,
    "8-K": FilingType.EIGHT_K,
    "DEF 14A": FilingType.DEF_14A,
}

_FREQ_MAP = {
    Period.ANNUAL: "yearly",
    Period.QUARTERLY: "quarterly",
    Period.TTM: "trailing",
}


def _safe(val) -> Optional[float]:
    """Convert a value to float, returning None for NaN/None/inf."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if (pd.isna(f) or f != f) else f
    except (TypeError, ValueError):
        return None


def _row(df: pd.DataFrame, key: str, col) -> Optional[float]:
    if key not in df.index:
        return None
    return _safe(df.loc[key, col])


def _build_income_statement(is_df: pd.DataFrame, col) -> IncomeStatement:
    r = lambda k: _row(is_df, k, col)
    cost = r("CostOfRevenue") or r("ReconciledCostOfRevenue")
    # Small IFRS synonym fallback — revenue, operating income, net income only
    revenue         = r("TotalRevenue")    or r("Revenue")         or r("NetRevenue")
    operating_income = r("OperatingIncome") or r("OperatingProfit") or r("EBIT")
    net_income      = r("NetIncome")       or r("NetIncomeLoss")   or r("ProfitLoss")
    return IncomeStatement(
        revenue=revenue,
        cost_of_revenue=cost,
        gross_profit=r("GrossProfit"),
        operating_income=operating_income,
        ebitda=r("EBITDA"),
        net_income=net_income,
        eps_basic=r("BasicEPS"),
        eps_diluted=r("DilutedEPS"),
        shares_outstanding_basic=r("BasicAverageShares"),
        shares_outstanding_diluted=r("DilutedAverageShares"),
    )


def _build_balance_sheet(bs_df: pd.DataFrame, col) -> BalanceSheet:
    r = lambda k: _row(bs_df, k, col)
    return BalanceSheet(
        total_assets=r("TotalAssets"),
        total_liabilities=r("TotalLiabilitiesNetMinorityInterest"),
        total_equity=r("TotalEquityGrossMinorityInterest") or r("StockholdersEquity"),
        cash_and_equivalents=r("CashAndCashEquivalents"),
        total_debt=r("TotalDebt"),
        net_debt=r("NetDebt"),
        goodwill=r("Goodwill"),
        intangible_assets=r("GoodwillAndOtherIntangibleAssets") or r("OtherIntangibleAssets"),
    )


def _build_cash_flow(cf_df: pd.DataFrame, col) -> CashFlowStatement:
    r = lambda k: _row(cf_df, k, col)
    return CashFlowStatement(
        operating_cash_flow=r("OperatingCashFlow"),
        capital_expenditures=r("CapitalExpenditure"),
        free_cash_flow=r("FreeCashFlow"),
        investing_cash_flow=r("InvestingCashFlow"),
        financing_cash_flow=r("FinancingCashFlow"),
        dividends_paid=r("CommonStockDividendPaid") or r("CashDividendsPaid"),
    )


def _build_ratios_from_info(info: dict) -> Ratios:
    g = lambda k: _safe(info.get(k))
    return Ratios(
        pe_ratio=g("trailingPE"),
        ps_ratio=g("priceToSalesTrailing12Months"),
        pb_ratio=g("priceToBook"),
        ev_ebitda=g("enterpriseToEbitda"),
        ev_revenue=g("enterpriseToRevenue"),
        market_cap=g("marketCap"),
        gross_margin=g("grossMargins"),
        operating_margin=g("operatingMargins"),
        net_margin=g("profitMargins"),
        roe=g("returnOnEquity"),
        roa=g("returnOnAssets"),
        roic=None,
        debt_to_equity=g("debtToEquity"),
        debt_to_ebitda=None,
        interest_coverage=None,
        current_ratio=g("currentRatio"),
        quick_ratio=g("quickRatio"),
    )


class YFinanceAdapter(DataAdapter):
    @property
    def source_name(self) -> str:
        return "yfinance"

    async def get_company(self, ticker: str, market: str = "US") -> CompanyIdentity:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_get_company, ticker)

    def _sync_get_company(self, ticker: str) -> CompanyIdentity:
        t = yf.Ticker(ticker)
        info = t.info
        name = info.get("longName") or info.get("shortName")
        if not name:
            raise ValueError(f"Ticker not found in yfinance: {ticker}")

        upper = ticker.upper()
        currency_str = info.get("currency", "USD")
        currency = _CURRENCY_MAP.get(currency_str, Currency.USD)

        # Suffix-based resolution is most reliable for global tickers
        resolved = None
        for suffix, (sx_exchange, sx_market, sx_currency) in _SUFFIX_MAP.items():
            if upper.endswith(suffix):
                resolved = (sx_exchange, sx_market, currency)  # prefer info currency
                break

        if resolved:
            exchange, market, currency = resolved
        else:
            # US ticker path: map exchange code; infer market from currency
            exchange_code = info.get("exchange", "")
            exchange = _EXCHANGE_MAP.get(exchange_code, Exchange.OTHER)
            market = _CURRENCY_TO_MARKET.get(currency, Market.US)

        quote_type = info.get("quoteType", "")
        asset_type_map = {
            "CRYPTOCURRENCY": "crypto",
            "CURRENCY": "forex",
            "FUTURE": "commodity",
            "INDEX": "index",
        }
        asset_type = asset_type_map.get(quote_type, "equity")

        return CompanyIdentity(
            ticker=upper,
            name=name,
            market=market,
            exchange=exchange,
            currency=currency,
            asset_type=asset_type,
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
        t = yf.Ticker(company.ticker)
        info = t.info
        ratios = _build_ratios_from_info(info)

        if period == Period.TTM:
            return self._extract_ttm(t, company, ratios)

        freq = _FREQ_MAP.get(period, "yearly")
        try:
            is_df = t.get_income_stmt(freq=freq)
            bs_df = t.get_balance_sheet(freq=freq)
            cf_df = t.get_cash_flow(freq=freq)
        except Exception:
            return []

        if is_df is None or is_df.empty:
            return []

        # Columns are Timestamps, sorted newest-first
        cols = is_df.columns.tolist()
        now = datetime.now(timezone.utc)
        results = []

        for col in cols[:limit]:
            col_date = date(col.year, col.month, col.day)
            is_stmt = _build_income_statement(is_df, col)

            # BS columns must also contain this timestamp
            bs_stmt = BalanceSheet()
            if bs_df is not None and col in bs_df.columns:
                bs_stmt = _build_balance_sheet(bs_df, col)

            cf_stmt = CashFlowStatement()
            if cf_df is not None and col in cf_df.columns:
                cf_stmt = _build_cash_flow(cf_df, col)

            # Attach live ratios only to the most recent period
            period_ratios = ratios if col == cols[0] else Ratios()

            fiscal_year = col_date.year
            fiscal_quarter = None
            if period == Period.QUARTERLY:
                # yfinance quarterly cols: determine quarter from month
                fiscal_quarter = (col_date.month - 1) // 3 + 1

            results.append(
                NormalizedFundamentals(
                    company=company,
                    period=period,
                    fiscal_year=fiscal_year,
                    fiscal_quarter=fiscal_quarter,
                    period_end_date=col_date,
                    currency=company.currency,
                    income_statement=is_stmt,
                    balance_sheet=bs_stmt,
                    cash_flow=cf_stmt,
                    ratios=period_ratios,
                    source=self.source_name,
                    fetched_at=now,
                )
            )

        return results

    def _extract_ttm(
        self, t: yf.Ticker, company: CompanyIdentity, ratios: Ratios
    ) -> List[NormalizedFundamentals]:
        now = datetime.now(timezone.utc)
        try:
            ttm_is = t.ttm_income_stmt
            ttm_bs = t.get_balance_sheet(freq="yearly")
            ttm_cf = t.ttm_cash_flow
        except Exception:
            return []

        is_stmt = IncomeStatement()
        if ttm_is is not None and not ttm_is.empty:
            col = ttm_is.columns[0]
            is_stmt = _build_income_statement(ttm_is, col)

        bs_stmt = BalanceSheet()
        if ttm_bs is not None and not ttm_bs.empty:
            col = ttm_bs.columns[0]
            bs_stmt = _build_balance_sheet(ttm_bs, col)

        cf_stmt = CashFlowStatement()
        if ttm_cf is not None and not ttm_cf.empty:
            col = ttm_cf.columns[0]
            cf_stmt = _build_cash_flow(ttm_cf, col)

        return [
            NormalizedFundamentals(
                company=company,
                period=Period.TTM,
                fiscal_year=now.year,
                fiscal_quarter=None,
                period_end_date=now.date(),
                currency=company.currency,
                income_statement=is_stmt,
                balance_sheet=bs_stmt,
                cash_flow=cf_stmt,
                ratios=ratios,
                source=self.source_name,
                fetched_at=now,
            )
        ]

    async def get_lite_fundamentals(self, ticker: str) -> ScreenerFields:
        """`.info`-only fetch for the screener batch endpoint — skips the 3 statement calls
        that `_sync_get_fundamentals` makes, at the cost of free_cash_flow (no .info equivalent)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_get_lite_fundamentals, ticker)

    def _sync_get_lite_fundamentals(self, ticker: str) -> ScreenerFields:
        t = yf.Ticker(ticker)
        info = t.info
        g = lambda k: _safe(info.get(k))
        return ScreenerFields(
            currency=info.get("currency"),
            market_cap=g("marketCap"),
            pe_ratio=g("trailingPE"),
            net_margin=g("profitMargins"),
            roe=g("returnOnEquity"),
            debt_to_equity=g("debtToEquity"),
            gross_margin=g("grossMargins"),
            revenue=g("totalRevenue"),
            free_cash_flow=None,
        )

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
        t = yf.Ticker(company.ticker)
        raw = t.sec_filings or []
        now = datetime.now(timezone.utc)
        results = []

        for entry in raw:
            form_str = str(entry.get("type", ""))
            filing_type = _FILING_TYPE_MAP.get(form_str)
            if filing_type is None:
                continue
            if filing_types and filing_type not in filing_types:
                continue

            filed_date_raw = entry.get("date")
            if filed_date_raw is None:
                continue
            if isinstance(filed_date_raw, date):
                filed_date = filed_date_raw
            else:
                try:
                    filed_date = date.fromisoformat(str(filed_date_raw))
                except Exception:
                    continue

            # Primary URL: the filing exhibit or edgarUrl
            exhibits = entry.get("exhibits", {})
            primary_url = exhibits.get(form_str) or entry.get("edgarUrl", "")

            results.append(
                FilingReference(
                    company=company,
                    filing_type=filing_type,
                    filed_date=filed_date,
                    period_of_report=None,
                    accession_number=None,
                    url=primary_url,
                    source=self.source_name,
                    fetched_at=now,
                )
            )

            if len(results) >= limit:
                break

        return results
