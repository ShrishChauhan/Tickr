# Options service tests — no live network calls; the yfinance provider and
# price service are monkeypatched so this exercises only the orchestration
# logic (contract matching, unit conversion, error paths).
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytest

from app.services import options as options_service
from app.schema import PriceOnlyData
from app.schema.options import OptionChain, OptionContract


class InMemoryCache:
    def __init__(self):
        self._store: dict[str, Any] = {}

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value, ttl_seconds: int, **kwargs):
        self._store[key] = value

    async def delete(self, key: str):
        self._store.pop(key, None)


def _future_expiration() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")


@pytest.fixture
def cache():
    return InMemoryCache()


@pytest.fixture
def patched_provider(monkeypatch):
    """Stub out YFinanceOptionsProvider network calls with fixed values, and
    FRED's provider as declining by default — tests must be isolated from
    whatever FRED_API_KEY happens to be set to in the local .env, not rely on
    it being blank. Tests that specifically exercise the FRED-succeeds path
    (test_calculate_prefers_fred_when_available) override this explicitly."""
    async def fake_get_chain(ticker, expiration):
        return {
            "calls": [{"strike": 150.0, "bid": 5.0, "ask": 5.2, "last_price": 5.1,
                       "volume": 100.0, "open_interest": 500.0, "implied_volatility": 0.25,
                       "last_trade_date": "2026-07-11T20:00:00+00:00"}],
            "puts": [{"strike": 150.0, "bid": 4.0, "ask": 4.2, "last_price": 4.1,
                      "volume": 80.0, "open_interest": 400.0, "implied_volatility": 0.28,
                      "last_trade_date": "2026-07-11T20:00:00+00:00"}],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    async def fake_get_risk_free_rate():
        return 0.037, None

    async def fake_get_dividend_rate(ticker):
        return 1.08

    async def fake_fred_declines():
        raise RuntimeError("FRED_API_KEY is not configured")

    monkeypatch.setattr(options_service._provider, "get_chain", fake_get_chain)
    monkeypatch.setattr(options_service._provider, "get_risk_free_rate", fake_get_risk_free_rate)
    monkeypatch.setattr(options_service._provider, "get_dividend_rate", fake_get_dividend_rate)
    monkeypatch.setattr(options_service._fred_provider, "get_risk_free_rate", fake_fred_declines)

    async def fake_get_price(cache, ticker):
        return PriceOnlyData(
            ticker=ticker, name="Test Co", asset_type="equity", currency="USD",
            current_price=155.0, fetched_at=datetime.now(timezone.utc).isoformat(), source="yfinance",
        )

    monkeypatch.setattr(options_service.price_service, "get_price", fake_get_price)
    return None


# ---------------------------------------------------------------------------
# Expirations: empty-state path (no network — provider is patched)
# ---------------------------------------------------------------------------

async def test_get_expirations_empty_state(cache, monkeypatch):
    async def fake_get_expirations(ticker):
        return []
    monkeypatch.setattr(options_service._provider, "get_expirations", fake_get_expirations)

    result = await options_service.get_expirations(cache, "GC=F")
    assert result.available is False
    assert result.expirations == []


async def test_get_expirations_available(cache, monkeypatch):
    async def fake_get_expirations(ticker):
        return ["2026-08-21", "2026-09-18"]
    monkeypatch.setattr(options_service._provider, "get_expirations", fake_get_expirations)

    result = await options_service.get_expirations(cache, "AAPL")
    assert result.available is True
    assert result.expirations == ["2026-08-21", "2026-09-18"]


# ---------------------------------------------------------------------------
# calculate(): unit conversion + inputs echo
# ---------------------------------------------------------------------------

async def test_calculate_call_unit_conversion(cache, patched_provider):
    expiration = _future_expiration()
    result = await options_service.calculate(cache, "AAPL", expiration, 150.0, "call")

    assert 0.0 <= result.delta <= 1.0
    assert result.gamma >= 0.0
    # theta_per_day must be small-scale (a fraction of a dollar to a few
    # dollars per day), not the raw annualized value it's derived from.
    assert abs(result.theta_per_day) < 5.0
    assert result.inputs_used.S == 155.0
    assert result.inputs_used.K == 150.0
    assert result.inputs_used.r == pytest.approx(0.037)
    assert result.inputs_used.q == pytest.approx(1.08 / 155.0)
    assert result.inputs_used.sigma == pytest.approx(0.25)
    # Freshness disclosure: cache-fetch timestamps (price_as_of/iv_as_of/r_as_of)
    # are distinct from the contract's own last-trade timestamp, which is what
    # actually explains IV staleness for thin contracts.
    assert result.inputs_used.price_as_of
    assert result.inputs_used.iv_as_of
    assert result.inputs_used.r_as_of
    assert result.inputs_used.contract_last_trade_at == "2026-07-11T20:00:00+00:00"
    # patched_provider mocks FRED as declining (independent of the local
    # .env's actual FRED_API_KEY) so this falls back to the patched yfinance provider.
    assert result.inputs_used.r_source == "yfinance"


async def test_calculate_put_delta_bounds(cache, patched_provider):
    expiration = _future_expiration()
    result = await options_service.calculate(cache, "AAPL", expiration, 150.0, "put")
    assert -1.0 <= result.delta <= 0.0


async def test_calculate_iv_override_takes_precedence(cache, patched_provider):
    expiration = _future_expiration()
    result = await options_service.calculate(cache, "AAPL", expiration, 150.0, "call", iv_override=0.40)
    assert result.inputs_used.sigma == pytest.approx(0.40)


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

async def test_calculate_unknown_strike_raises(cache, patched_provider):
    expiration = _future_expiration()
    with pytest.raises(options_service.OptionsLookupError):
        await options_service.calculate(cache, "AAPL", expiration, 999.0, "call")


async def test_calculate_invalid_option_type_raises(cache, patched_provider):
    expiration = _future_expiration()
    with pytest.raises(options_service.OptionsLookupError):
        await options_service.calculate(cache, "AAPL", expiration, 150.0, "straddle")


async def test_calculate_tolerates_legacy_risk_free_rate_cache_entry(cache, patched_provider):
    # A cached payload missing a field the code now expects (e.g. from before
    # `fetched_at` was added) must be treated as a miss and refetched, not crash.
    await cache.set("options:risk_free_rate", {"rate": 0.02}, 86_400)

    expiration = _future_expiration()
    result = await options_service.calculate(cache, "AAPL", expiration, 150.0, "call")
    assert result.inputs_used.r == pytest.approx(0.037)
    assert result.inputs_used.r_as_of


async def test_calculate_prefers_fred_when_available(cache, patched_provider, monkeypatch):
    # FRED primary: when it succeeds, its own observation date becomes
    # r_as_of (not the fetch-time stamp) and r_source discloses the provider.
    async def fake_fred_rate():
        return 0.0371, "2026-07-10"
    monkeypatch.setattr(options_service._fred_provider, "get_risk_free_rate", fake_fred_rate)

    expiration = _future_expiration()
    result = await options_service.calculate(cache, "AAPL", expiration, 150.0, "call")

    assert result.inputs_used.r == pytest.approx(0.0371)
    assert result.inputs_used.r_as_of == "2026-07-10"
    assert result.inputs_used.r_source == "fred"


async def test_calculate_falls_back_to_yfinance_when_fred_unavailable(cache, patched_provider, monkeypatch):
    # FRED raising (blank key, network error, no valid observation) must fall
    # back to the existing yfinance ^IRX path rather than propagate the error.
    async def fake_fred_rate():
        raise RuntimeError("FRED_API_KEY is not configured")
    monkeypatch.setattr(options_service._fred_provider, "get_risk_free_rate", fake_fred_rate)

    expiration = _future_expiration()
    result = await options_service.calculate(cache, "AAPL", expiration, 150.0, "call")

    assert result.inputs_used.r == pytest.approx(0.037)
    assert result.inputs_used.r_source == "yfinance"


async def test_cached_fred_rate_survives_a_cache_hit_unchanged(cache, patched_provider, monkeypatch):
    # On a cache hit, the originally-fetched source/observation_date must be
    # returned as-is, not re-derived — same contract as the pre-existing
    # fetched_at-survives-a-cache-hit behavior this extends.
    await cache.set("options:risk_free_rate",
                     {"rate": 0.0371, "fetched_at": "2026-07-11T00:00:00+00:00",
                      "source": "fred", "observation_date": "2026-07-10"},
                     86_400)

    expiration = _future_expiration()
    result = await options_service.calculate(cache, "AAPL", expiration, 150.0, "call")

    assert result.inputs_used.r == pytest.approx(0.0371)
    assert result.inputs_used.r_as_of == "2026-07-10"
    assert result.inputs_used.r_source == "fred"


async def test_calculate_no_iv_no_override_raises(cache, monkeypatch):
    async def fake_get_chain(ticker, expiration):
        return {
            "calls": [{"strike": 150.0, "bid": 5.0, "ask": 5.2, "last_price": 5.1,
                       "volume": 100.0, "open_interest": 500.0, "implied_volatility": None}],
            "puts": [],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    monkeypatch.setattr(options_service._provider, "get_chain", fake_get_chain)

    expiration = _future_expiration()
    with pytest.raises(options_service.OptionsLookupError):
        await options_service.calculate(cache, "AAPL", expiration, 150.0, "call")
