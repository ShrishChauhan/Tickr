# FRED risk-free-rate adapter tests — no live network calls, httpx.AsyncClient
# is monkeypatched with a canned response (mirrors options service tests'
# no-live-network convention).
import pytest

from app.adapters import fred as fred_adapter
from app.config import settings


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        return _FakeResponse(self._payload)


@pytest.fixture
def fred_key(monkeypatch):
    monkeypatch.setattr(settings, "FRED_API_KEY", "testkey1234567890")


def _patch_client(monkeypatch, payload):
    monkeypatch.setattr(fred_adapter.httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(payload))


async def test_skips_missing_observations_and_converts_percent_to_decimal(monkeypatch, fred_key):
    # FRED represents missing/holiday observations as the literal string ".",
    # not null or omission, and returns most-recent-first under sort_order=desc.
    payload = {
        "observations": [
            {"date": "2026-07-13", "value": "."},
            {"date": "2026-07-10", "value": "3.71"},
            {"date": "2026-07-09", "value": "3.69"},
        ]
    }
    _patch_client(monkeypatch, payload)

    rate, observation_date = await fred_adapter.FredRiskFreeRateProvider().get_risk_free_rate()

    assert rate == pytest.approx(0.0371)
    # The as-of is the observation's own date, not datetime.now() — honest
    # about FRED's publication lag rather than stamping "just fetched."
    assert observation_date == "2026-07-10"


async def test_raises_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "FRED_API_KEY", "")
    with pytest.raises(RuntimeError):
        await fred_adapter.FredRiskFreeRateProvider().get_risk_free_rate()


async def test_raises_when_all_observations_in_window_are_missing(monkeypatch, fred_key):
    payload = {"observations": [{"date": "2026-07-13", "value": "."}, {"date": "2026-07-12", "value": "."}]}
    _patch_client(monkeypatch, payload)

    with pytest.raises(RuntimeError):
        await fred_adapter.FredRiskFreeRateProvider().get_risk_free_rate()
