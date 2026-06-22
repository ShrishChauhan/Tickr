# Analysis tests — no real Groq calls; spy on _call_groq to stay fast and deterministic.
import asyncio
import pytest
from datetime import date, datetime, timezone
from uuid import uuid4

from app.analysis.groq_engine import GroqAnalysisEngine
from app.cache.postgres import PostgresCacheBackend
from app.cache.ttl_config import AI_ANALYSIS_TTL_SECONDS
from app.schema import CompanyIdentity, NormalizedFundamentals, Market, Exchange, Currency
from app.schema.fundamentals import Period, IncomeStatement, BalanceSheet, CashFlowStatement, Ratios
from app.schema.filings import FilingReference, FilingType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
            gross_profit=199_000_000_000.0,
            operating_income=133_000_000_000.0,
            ebitda=144_700_000_000.0,
            net_income=112_000_000_000.0,
            eps_diluted=7.46,
        ),
        balance_sheet=BalanceSheet(
            total_assets=364_000_000_000.0,
            total_debt=97_000_000_000.0,
            cash_and_equivalents=30_000_000_000.0,
        ),
        cash_flow=CashFlowStatement(
            operating_cash_flow=118_000_000_000.0,
            free_cash_flow=108_000_000_000.0,
        ),
        ratios=Ratios(pe_ratio=36.1, gross_margin=47.9, net_margin=26.9, roe=141.5),
        source="test",
        fetched_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Test 1: Prompt grounding — actual figures appear in the prompt sent to LLM
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analysis_prompt_includes_actual_figures():
    """_build_prompt embeds the actual revenue and ticker from the fundamentals."""
    engine = GroqAnalysisEngine.__new__(GroqAnalysisEngine)  # skip __init__ (no API key needed)

    company = _make_company()
    fundamentals = [_make_fundamentals()]
    filings: list = []

    prompt = engine._build_prompt(company, fundamentals, filings, "")

    # Revenue is $416.0B — formatted by _build_prompt as "$416.0B"
    assert "416.0" in prompt, f"Revenue figure not found in prompt. Prompt preview:\n{prompt[:500]}"
    assert "AAPL" in prompt
    assert "Apple Inc." in prompt
    assert "FY2025" in prompt
    # EBITDA should appear
    assert "144.7" in prompt


# ---------------------------------------------------------------------------
# Test 2: Cache hit skips LLM — _call_groq invoked exactly once across two requests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analysis_cache_hit_skips_llm():
    """Second analyze call returns from cache; LLM not called again."""
    engine = GroqAnalysisEngine.__new__(GroqAnalysisEngine)
    call_count = 0

    def spy_call_groq(prompt: str) -> str:
        nonlocal call_count
        call_count += 1
        return "Mocked analysis: revenue was $416.0B."

    engine._call_groq = spy_call_groq

    cache = PostgresCacheBackend()
    unique_key = f"test:analysis:AAPL:{uuid4()}"

    company = _make_company()
    fundamentals = [_make_fundamentals()]
    filings: list = []

    async def analyze_with_cache() -> str:
        raw = await cache.get(unique_key)
        if raw is not None:
            return raw["analysis"]
        # engine.analyze_company uses run_in_executor → calls _call_groq
        result = await engine.analyze_company(company, fundamentals, filings, "")
        generated_at = datetime.now(timezone.utc)
        await cache.set(
            unique_key,
            {"analysis": result, "generated_at": generated_at.isoformat(), "periods_analyzed": 1},
            AI_ANALYSIS_TTL_SECONDS,
            data_type="analysis",
            ticker="AAPL",
            source="test",
        )
        return result

    r1 = await analyze_with_cache()
    r2 = await analyze_with_cache()

    assert call_count == 1, (
        f"_call_groq invoked {call_count} times across 2 requests; expected exactly 1 (cache miss + HIT)"
    )
    assert r1 == r2 == "Mocked analysis: revenue was $416.0B."
