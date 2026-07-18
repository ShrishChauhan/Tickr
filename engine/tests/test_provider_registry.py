# Provider registry tests — Chunks 1-2 of the Loader-registry refactor
# (see PROGRESS.md). Fake providers only; no live network calls.
import pytest

from app.adapters.base import LoaderLicense
from app.services import provider_registry
from app.services.provider_registry import (
    _fred_risk_free_provider,
    _yfinance_options_provider,
    _yfinance_quote_provider,
    _parquet_ohlc_loader,
)


# ---------------------------------------------------------------------------
# Registry shape — tuple-keyed dict must reproduce the pre-refactor
# asset-class -> provider-list mapping exactly (same providers, same order).
# ---------------------------------------------------------------------------

def test_registry_keys_are_data_type_asset_class_tuples():
    assert all(isinstance(k, tuple) and len(k) == 2 for k in provider_registry._REGISTRY)
    # "quote" is keyed per asset class; "risk_free_rate" (Chunk 2) uses the
    # "global" sentinel since the rate itself is asset-class-agnostic.
    quote_keys = [k for k in provider_registry._REGISTRY if k[0] == "quote"]
    assert {k[1] for k in quote_keys} == {"crypto", "forex", "commodity", "index", "equity"}
    assert ("risk_free_rate", "global") in provider_registry._REGISTRY


def test_quote_chain_matches_pre_refactor_asset_classes():
    expected = {
        "crypto":    ["coinbase", "yfinance"],
        "forex":     ["yfinance"],
        "commodity": ["yfinance"],
        "index":     ["yfinance"],
        "equity":    ["finnhub", "yfinance"],
    }
    for asset_class, names in expected.items():
        providers = provider_registry._REGISTRY[("quote", asset_class)]
        assert [p.name for p in providers] == names


# ---------------------------------------------------------------------------
# Fake providers — decline / raise / first-success-wins semantics
# ---------------------------------------------------------------------------

class _DeclineProvider:
    name = "decline"
    license = LoaderLicense.UNCLEAR

    def __init__(self):
        self.calls = 0

    async def get_quote(self, ticker: str):
        self.calls += 1
        return None


class _RaiseProvider:
    name = "raise"
    license = LoaderLicense.UNCLEAR

    def __init__(self):
        self.calls = 0

    async def get_quote(self, ticker: str):
        self.calls += 1
        raise RuntimeError("boom")


class _SuccessProvider:
    name = "success"
    license = LoaderLicense.UNCLEAR

    def __init__(self, payload=None):
        self.calls = 0
        self.payload = payload or {"current_price": 123.45}

    async def get_quote(self, ticker: str):
        self.calls += 1
        return dict(self.payload)


@pytest.fixture
def patched_equity_chain(monkeypatch):
    """Swap the ('quote', 'equity') chain for a caller-supplied list of fake
    providers; restored automatically after the test. AAPL (used below)
    resolves to 'equity' via infer_asset_type_from_ticker."""

    def _patch(providers):
        monkeypatch.setitem(provider_registry._REGISTRY, ("quote", "equity"), providers)

    return _patch


@pytest.mark.asyncio
async def test_decline_falls_through_to_next_provider(patched_equity_chain):
    decline = _DeclineProvider()
    success = _SuccessProvider()
    patched_equity_chain([decline, success])

    result = await provider_registry.get_quote("AAPL")

    assert decline.calls == 1
    assert success.calls == 1
    assert result["source"] == "success"


@pytest.mark.asyncio
async def test_raise_is_treated_as_decline(patched_equity_chain):
    raiser = _RaiseProvider()
    success = _SuccessProvider()
    patched_equity_chain([raiser, success])

    result = await provider_registry.get_quote("AAPL")

    assert raiser.calls == 1
    assert success.calls == 1
    assert result["source"] == "success"


@pytest.mark.asyncio
async def test_first_success_wins_second_provider_not_called(patched_equity_chain):
    first = _SuccessProvider({"current_price": 1.0})
    second = _SuccessProvider({"current_price": 2.0})
    patched_equity_chain([first, second])

    result = await provider_registry.get_quote("AAPL")

    assert first.calls == 1
    assert second.calls == 0
    assert result["current_price"] == 1.0
    assert result["source"] == "success"


@pytest.mark.asyncio
async def test_total_failure_returns_none(patched_equity_chain):
    patched_equity_chain([_DeclineProvider(), _RaiseProvider()])

    result = await provider_registry.get_quote("AAPL")

    assert result is None


# ---------------------------------------------------------------------------
# Risk-free-rate chain (Chunk 2) — asymmetric failure contract: unlike
# get_quote(), a total failure must re-raise, not swallow to None. A silent
# None here would let options.py price Greeks at a fabricated/zero rate.
# ---------------------------------------------------------------------------

def test_risk_free_rate_chain_is_fred_then_yfinance():
    providers = provider_registry._REGISTRY[("risk_free_rate", "global")]
    assert [p.name for p in providers] == ["fred", "yfinance"]


@pytest.mark.asyncio
async def test_risk_free_rate_first_success_wins(monkeypatch):
    async def fred_succeeds():
        return 0.0371, "2026-07-10"
    monkeypatch.setattr(_fred_risk_free_provider, "get_risk_free_rate", fred_succeeds)

    rate, as_of, source = await provider_registry.get_risk_free_rate()

    assert (rate, as_of, source) == (0.0371, "2026-07-10", "fred")


@pytest.mark.asyncio
async def test_risk_free_rate_falls_through_on_raise(monkeypatch):
    async def fred_fails():
        raise RuntimeError("FRED_API_KEY is not configured")
    async def yfinance_succeeds():
        return 0.037, None
    monkeypatch.setattr(_fred_risk_free_provider, "get_risk_free_rate", fred_fails)
    monkeypatch.setattr(_yfinance_options_provider, "get_risk_free_rate", yfinance_succeeds)

    rate, as_of, source = await provider_registry.get_risk_free_rate()

    assert (rate, as_of, source) == (0.037, None, "yfinance")


@pytest.mark.asyncio
async def test_risk_free_rate_total_failure_reraises_not_none(monkeypatch):
    async def fred_fails():
        raise RuntimeError("fred down")
    async def yfinance_fails():
        raise RuntimeError("yfinance down")
    monkeypatch.setattr(_fred_risk_free_provider, "get_risk_free_rate", fred_fails)
    monkeypatch.setattr(_yfinance_options_provider, "get_risk_free_rate", yfinance_fails)

    with pytest.raises(RuntimeError, match="yfinance down"):
        await provider_registry.get_risk_free_rate()


# ---------------------------------------------------------------------------
# Equity OHLC chain (Chunk 3) — [yfinance, parquet]. Unlike get_risk_free_rate(),
# total failure must preserve the pre-refactor contract: ([], None, None), not
# a raise. All mocked — no dependency on data_historical/ existing in CI.
# ---------------------------------------------------------------------------

def test_ohlc_chain_is_yfinance_then_parquet():
    providers = provider_registry._REGISTRY[("ohlc", "equity")]
    assert [p.name for p in providers] == ["yfinance", "parquet"]


@pytest.mark.asyncio
async def test_ohlc_yfinance_success_short_circuits_parquet(monkeypatch):
    async def yfinance_ok(ticker):
        return [{"date": "2026-07-17", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}], "2026-07-17T12:00:00+00:00"

    parquet_calls = {"n": 0}
    async def parquet_should_not_run(ticker):
        parquet_calls["n"] += 1
        return [], None

    monkeypatch.setattr(_yfinance_quote_provider, "get_ohlc", yfinance_ok)
    monkeypatch.setattr(_parquet_ohlc_loader, "get_ohlc", parquet_should_not_run)

    bars, as_of, source = await provider_registry.get_equity_ohlc("AAPL")

    assert source == "yfinance"
    assert as_of == "2026-07-17T12:00:00+00:00"
    assert len(bars) == 1
    assert parquet_calls["n"] == 0


@pytest.mark.asyncio
async def test_ohlc_falls_through_to_parquet_on_yfinance_failure(monkeypatch):
    async def yfinance_fails(ticker):
        raise RuntimeError("yfinance down")
    async def parquet_ok(ticker):
        return [{"date": "2026-07-10", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}], "2026-07-10"

    monkeypatch.setattr(_yfinance_quote_provider, "get_ohlc", yfinance_fails)
    monkeypatch.setattr(_parquet_ohlc_loader, "get_ohlc", parquet_ok)

    bars, as_of, source = await provider_registry.get_equity_ohlc("AAPL")

    assert source == "parquet"
    assert as_of == "2026-07-10"
    assert len(bars) == 1


@pytest.mark.asyncio
async def test_ohlc_empty_result_treated_as_decline(monkeypatch):
    """An empty-but-not-raised bar list (e.g. yfinance has no history for a
    brand-new listing) must also fall through, mirroring get_quote()'s
    None-means-decline semantics — not just exceptions."""
    async def yfinance_empty(ticker):
        return [], "2026-07-17T12:00:00+00:00"
    async def parquet_ok(ticker):
        return [{"date": "2026-07-10", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}], "2026-07-10"

    monkeypatch.setattr(_yfinance_quote_provider, "get_ohlc", yfinance_empty)
    monkeypatch.setattr(_parquet_ohlc_loader, "get_ohlc", parquet_ok)

    bars, as_of, source = await provider_registry.get_equity_ohlc("AAPL")

    assert source == "parquet"
    assert len(bars) == 1


@pytest.mark.asyncio
async def test_ohlc_total_failure_returns_empty_list_not_none(monkeypatch):
    async def yfinance_fails(ticker):
        raise RuntimeError("yfinance down")
    async def parquet_fails(ticker):
        raise RuntimeError("no local parquet file")

    monkeypatch.setattr(_yfinance_quote_provider, "get_ohlc", yfinance_fails)
    monkeypatch.setattr(_parquet_ohlc_loader, "get_ohlc", parquet_fails)

    bars, as_of, source = await provider_registry.get_equity_ohlc("AAPL")

    assert bars == []
    assert as_of is None
    assert source is None
