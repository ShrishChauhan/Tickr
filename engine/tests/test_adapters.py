# Integration tests — real live API calls; no mocks.
# These verify that both adapters return correctly-typed, sanity-checked data.
import pytest
from datetime import date

from app.adapters.edgar import EdgarAdapter
from app.adapters.yfinance import YFinanceAdapter
from app.schema import CompanyIdentity, NormalizedFundamentals, FilingReference, Market, Currency
from app.schema.fundamentals import Period, IncomeStatement, BalanceSheet, CashFlowStatement
from app.schema.filings import FilingType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def edgar():
    return EdgarAdapter()


@pytest.fixture(scope="module")
def yfinance():
    return YFinanceAdapter()


# ---------------------------------------------------------------------------
# EDGAR — get_company
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edgar_get_company_aapl(edgar):
    c = await edgar.get_company("AAPL")
    assert isinstance(c, CompanyIdentity)
    assert c.ticker == "AAPL"
    assert "Apple" in c.name
    assert c.market == Market.US
    assert c.currency == Currency.USD
    assert c.cik is not None
    assert c.cik == "320193"


@pytest.mark.asyncio
async def test_edgar_get_company_jpm(edgar):
    c = await edgar.get_company("JPM")
    assert isinstance(c, CompanyIdentity)
    assert c.ticker == "JPM"
    assert c.cik is not None


@pytest.mark.asyncio
async def test_edgar_get_company_brkb(edgar):
    c = await edgar.get_company("BRK-B")
    assert isinstance(c, CompanyIdentity)
    assert c.cik is not None


# ---------------------------------------------------------------------------
# EDGAR — get_fundamentals (annual)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edgar_annual_fundamentals_aapl(edgar):
    c = await edgar.get_company("AAPL")
    fundas = await edgar.get_fundamentals(c, Period.ANNUAL, limit=3)

    assert len(fundas) > 0
    latest = fundas[0]

    assert isinstance(latest, NormalizedFundamentals)
    assert latest.period == Period.ANNUAL
    assert latest.fiscal_quarter is None
    assert latest.currency == Currency.USD
    assert latest.source == "edgar"
    assert isinstance(latest.period_end_date, date)

    is_ = latest.income_statement
    assert isinstance(is_, IncomeStatement)
    # AAPL FY2025 revenue ~$416B — sanity check (allow ±10%)
    assert is_.revenue is not None
    assert 370_000_000_000 < is_.revenue < 460_000_000_000, f"AAPL revenue out of range: {is_.revenue}"
    assert is_.net_income is not None
    assert is_.gross_profit is not None
    assert is_.operating_income is not None

    bs_ = latest.balance_sheet
    assert isinstance(bs_, BalanceSheet)
    assert bs_.total_assets is not None
    assert bs_.total_assets > 0

    cf_ = latest.cash_flow
    assert isinstance(cf_, CashFlowStatement)
    assert cf_.operating_cash_flow is not None
    assert cf_.operating_cash_flow > 0, "AAPL operating CF should be positive"


@pytest.mark.asyncio
async def test_edgar_annual_fundamentals_returns_multiple_periods(edgar):
    c = await edgar.get_company("AAPL")
    fundas = await edgar.get_fundamentals(c, Period.ANNUAL, limit=3)
    assert len(fundas) >= 2, "Should return at least 2 annual periods"
    # Ensure each period has a different period_end_date
    dates = [f.period_end_date for f in fundas]
    assert len(set(dates)) == len(dates), "Duplicate period dates returned"


@pytest.mark.asyncio
async def test_edgar_annual_fundamentals_jpm(edgar):
    c = await edgar.get_company("JPM")
    fundas = await edgar.get_fundamentals(c, Period.ANNUAL, limit=2)
    assert len(fundas) > 0
    latest = fundas[0]
    # JPM 2025 total assets ~$4.4T — banks use "LiabilitiesAndEquity" as total assets fallback
    assert latest.balance_sheet.total_assets is not None
    assert latest.balance_sheet.total_assets > 3_000_000_000_000


# ---------------------------------------------------------------------------
# EDGAR — get_fundamentals (quarterly)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edgar_quarterly_fundamentals_aapl(edgar):
    c = await edgar.get_company("AAPL")
    fundas = await edgar.get_fundamentals(c, Period.QUARTERLY, limit=2)
    assert len(fundas) > 0
    q = fundas[0]
    assert q.period == Period.QUARTERLY
    assert q.fiscal_quarter in (1, 2, 3, 4)
    assert q.income_statement.revenue is not None
    assert q.income_statement.revenue > 0


# ---------------------------------------------------------------------------
# EDGAR — get_filings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edgar_filings_aapl(edgar):
    c = await edgar.get_company("AAPL")
    filings = await edgar.get_filings(c, limit=10)

    assert len(filings) > 0
    for f in filings:
        assert isinstance(f, FilingReference)
        assert f.filing_type in list(FilingType)
        assert isinstance(f.filed_date, date)
        assert f.url.startswith("https://")
        assert f.accession_number is not None
        assert f.source == "edgar"


@pytest.mark.asyncio
async def test_edgar_filings_filtered_type(edgar):
    c = await edgar.get_company("AAPL")
    tenk_filings = await edgar.get_filings(c, filing_types=[FilingType.TEN_K], limit=5)
    assert len(tenk_filings) > 0
    assert all(f.filing_type == FilingType.TEN_K for f in tenk_filings)


@pytest.mark.asyncio
async def test_edgar_filings_brkb(edgar):
    c = await edgar.get_company("BRK-B")
    filings = await edgar.get_filings(c, limit=5)
    assert len(filings) > 0


# ---------------------------------------------------------------------------
# yfinance — get_company
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_yfinance_get_company_aapl(yfinance):
    c = await yfinance.get_company("AAPL")
    assert isinstance(c, CompanyIdentity)
    assert c.ticker == "AAPL"
    assert "Apple" in c.name
    assert c.market == Market.US
    assert c.currency == Currency.USD
    assert c.cik is None  # yfinance does not provide CIK


@pytest.mark.asyncio
async def test_yfinance_get_company_jpm(yfinance):
    c = await yfinance.get_company("JPM")
    assert isinstance(c, CompanyIdentity)
    assert c.ticker == "JPM"


# ---------------------------------------------------------------------------
# yfinance — get_fundamentals (annual)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_yfinance_annual_fundamentals_aapl(yfinance):
    c = await yfinance.get_company("AAPL")
    fundas = await yfinance.get_fundamentals(c, Period.ANNUAL, limit=5)

    assert len(fundas) > 0
    latest = fundas[0]

    assert isinstance(latest, NormalizedFundamentals)
    assert latest.period == Period.ANNUAL
    assert latest.source == "yfinance"

    is_ = latest.income_statement
    # AAPL FY2025 revenue ~$416B
    assert is_.revenue is not None
    assert 370_000_000_000 < is_.revenue < 460_000_000_000, f"AAPL revenue out of range: {is_.revenue}"
    assert is_.net_income is not None
    assert is_.ebitda is not None
    assert is_.ebitda > 0

    # Ratios on most recent period
    r = latest.ratios
    assert r.pe_ratio is not None
    assert r.pe_ratio > 0
    assert r.gross_margin is not None


@pytest.mark.asyncio
async def test_yfinance_annual_fundamentals_returns_multiple_periods(yfinance):
    c = await yfinance.get_company("AAPL")
    fundas = await yfinance.get_fundamentals(c, Period.ANNUAL, limit=5)
    # yfinance should provide at least 4 years for AAPL
    assert len(fundas) >= 3


@pytest.mark.asyncio
async def test_yfinance_annual_fundamentals_jpm(yfinance):
    c = await yfinance.get_company("JPM")
    fundas = await yfinance.get_fundamentals(c, Period.ANNUAL, limit=3)
    assert len(fundas) > 0
    latest = fundas[0]
    assert latest.balance_sheet.total_assets is not None


@pytest.mark.asyncio
async def test_yfinance_annual_fundamentals_brkb(yfinance):
    c = await yfinance.get_company("BRK-B")
    fundas = await yfinance.get_fundamentals(c, Period.ANNUAL, limit=3)
    assert len(fundas) > 0


# ---------------------------------------------------------------------------
# yfinance — get_fundamentals (quarterly)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_yfinance_quarterly_fundamentals_aapl(yfinance):
    c = await yfinance.get_company("AAPL")
    fundas = await yfinance.get_fundamentals(c, Period.QUARTERLY, limit=4)
    assert len(fundas) > 0
    q = fundas[0]
    assert q.period == Period.QUARTERLY
    assert q.income_statement.revenue is not None
    assert q.income_statement.revenue > 0


# ---------------------------------------------------------------------------
# yfinance — get_filings (proxied via sec_filings)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_yfinance_filings_aapl(yfinance):
    c = await yfinance.get_company("AAPL")
    filings = await yfinance.get_filings(c, limit=5)
    assert len(filings) > 0
    for f in filings:
        assert isinstance(f, FilingReference)
        assert isinstance(f.filed_date, date)
        assert f.url != ""


# ---------------------------------------------------------------------------
# Cross-source sanity check: EDGAR and yfinance should agree on AAPL revenue
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cross_source_aapl_revenue_agreement(edgar, yfinance):
    """EDGAR and yfinance AAPL FY2025 revenue should be within 1% of each other."""
    ec = await edgar.get_company("AAPL")
    edgar_fundas = await edgar.get_fundamentals(ec, Period.ANNUAL, limit=1)

    yc = await yfinance.get_company("AAPL")
    yf_fundas = await yfinance.get_fundamentals(yc, Period.ANNUAL, limit=1)

    assert edgar_fundas and yf_fundas
    e_rev = edgar_fundas[0].income_statement.revenue
    y_rev = yf_fundas[0].income_statement.revenue
    assert e_rev is not None and y_rev is not None

    diff_pct = abs(e_rev - y_rev) / max(e_rev, y_rev)
    assert diff_pct < 0.01, f"Revenue mismatch: EDGAR={e_rev:,.0f} yfinance={y_rev:,.0f} ({diff_pct:.1%})"
