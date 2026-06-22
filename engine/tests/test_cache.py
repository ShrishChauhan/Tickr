# Cache tests — run against real Neon DB; unique keys per run prevent collisions.
import asyncio
import pytest
from datetime import date, datetime, timezone
from uuid import uuid4

from app.cache.postgres import PostgresCacheBackend
from app.cache.ttl_config import COMPANY_INFO_TTL_SECONDS, FUNDAMENTALS_TTL_SECONDS
from app.schema import CompanyIdentity, NormalizedFundamentals, Market, Exchange, Currency
from app.schema.fundamentals import Period, IncomeStatement, BalanceSheet, CashFlowStatement, Ratios
from app.schema.filings import FilingReference, FilingType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cache():
    return PostgresCacheBackend()


@pytest.fixture
def unique_key():
    return f"test:{uuid4()}"


def _make_company() -> CompanyIdentity:
    return CompanyIdentity(
        ticker="AAPL",
        name="Apple Inc.",
        market=Market.US,
        exchange=Exchange.NASDAQ,
        currency=Currency.USD,
        cik="320193",
    )


def _make_fundamentals() -> NormalizedFundamentals:
    company = _make_company()
    return NormalizedFundamentals(
        company=company,
        period=Period.ANNUAL,
        fiscal_year=2025,
        fiscal_quarter=None,
        period_end_date=date(2025, 9, 27),
        currency=Currency.USD,
        income_statement=IncomeStatement(
            revenue=416_000_000_000.0,
            net_income=112_000_000_000.0,
        ),
        balance_sheet=BalanceSheet(total_assets=364_000_000_000.0),
        cash_flow=CashFlowStatement(operating_cash_flow=118_000_000_000.0),
        ratios=Ratios(pe_ratio=36.1),
        source="test",
        fetched_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_round_trip_company(cache, unique_key):
    """CompanyIdentity survives JSON round-trip with correct enum types."""
    original = _make_company()
    key = unique_key + ":company:AAPL"

    await cache.set(key, original.model_dump(mode="json"), COMPANY_INFO_TTL_SECONDS,
                    data_type="company", ticker="AAPL", source="test")

    raw = await cache.get(key)
    assert raw is not None, "Cache get returned None immediately after set"

    recovered = CompanyIdentity.model_validate(raw)
    assert recovered.ticker == "AAPL"
    assert recovered.name == "Apple Inc."
    assert recovered.market == Market.US
    assert isinstance(recovered.market, Market)
    assert recovered.exchange == Exchange.NASDAQ
    assert isinstance(recovered.exchange, Exchange)
    assert recovered.currency == Currency.USD
    assert recovered.cik == "320193"


@pytest.mark.asyncio
async def test_cache_round_trip_fundamentals(cache, unique_key):
    """NormalizedFundamentals list survives JSON round-trip; dates/datetimes/enums correct types."""
    original = _make_fundamentals()
    key = unique_key + ":fundamentals:AAPL:annual:1"

    payload = [original.model_dump(mode="json")]
    await cache.set(key, payload, FUNDAMENTALS_TTL_SECONDS,
                    data_type="fundamentals", ticker="AAPL", source="test")

    raw = await cache.get(key)
    assert raw is not None

    recovered_list = [NormalizedFundamentals.model_validate(item) for item in raw]
    assert len(recovered_list) == 1
    f = recovered_list[0]

    # Period enum round-trip
    assert f.period == Period.ANNUAL
    assert isinstance(f.period, Period)

    # date field must come back as a date, not a string
    assert f.period_end_date == date(2025, 9, 27)
    assert isinstance(f.period_end_date, date)

    # datetime field must come back as a datetime, not a string
    assert isinstance(f.fetched_at, datetime)

    # Nested model fields
    assert f.income_statement.revenue == 416_000_000_000.0
    assert f.company.exchange == Exchange.NASDAQ
    assert isinstance(f.company.exchange, Exchange)


# ---------------------------------------------------------------------------
# Expiry test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_expiry(cache, unique_key):
    """Entry with TTL=1s is treated as a miss after 2 seconds."""
    key = unique_key + ":expiry"
    await cache.set(key, {"value": 42}, ttl_seconds=1,
                    data_type="company", ticker="TEST", source="test")

    # Confirm it's there immediately
    assert await cache.get(key) is not None

    await asyncio.sleep(2)

    result = await cache.get(key)
    assert result is None, f"Expected None (expired) but got: {result}"


# ---------------------------------------------------------------------------
# Cache-hit-skips-adapter test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_hit_skips_adapter(cache, unique_key):
    """Second cache_or_fetch call returns from cache; adapter NOT called again."""
    from app.adapters.yfinance import YFinanceAdapter

    adapter = YFinanceAdapter()
    real_get_company = adapter.get_company
    call_count = 0

    async def spy_get_company(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return await real_get_company(*args, **kwargs)

    adapter.get_company = spy_get_company
    key = unique_key + ":company:AAPL"

    async def cache_or_fetch_company(ticker: str) -> CompanyIdentity:
        raw = await cache.get(key)
        if raw is not None:
            return CompanyIdentity.model_validate(raw)
        result = await adapter.get_company(ticker)
        await cache.set(key, result.model_dump(mode="json"), COMPANY_INFO_TTL_SECONDS,
                        data_type="company", ticker=ticker, source="yfinance")
        return result

    r1 = await cache_or_fetch_company("AAPL")
    r2 = await cache_or_fetch_company("AAPL")

    assert call_count == 1, f"Adapter called {call_count} times across 2 requests; expected 1 (cache miss + hit)"
    assert r1.ticker == "AAPL"
    assert r2.ticker == "AAPL"
    assert r1.market == r2.market == Market.US
