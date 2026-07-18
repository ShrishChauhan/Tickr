# Provider registry tests — Chunk 1 of the Loader-registry refactor
# (see PROGRESS.md). Fake providers only; no live network calls.
import pytest

from app.adapters.base import LoaderLicense
from app.services import provider_registry


# ---------------------------------------------------------------------------
# Registry shape — tuple-keyed dict must reproduce the pre-refactor
# asset-class -> provider-list mapping exactly (same providers, same order).
# ---------------------------------------------------------------------------

def test_registry_keys_are_data_type_asset_class_tuples():
    assert all(isinstance(k, tuple) and len(k) == 2 for k in provider_registry._REGISTRY)
    quote_keys = [k for k in provider_registry._REGISTRY if k[0] == "quote"]
    assert {k[1] for k in quote_keys} == {"crypto", "forex", "commodity", "index", "equity"}


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
