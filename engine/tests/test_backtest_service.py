# Backtest orchestration tests — no local Parquet/DuckDB touched;
# historical_data.load_price_history is monkeypatched so this exercises only
# the wiring (params passed through correctly, echoed in the result).
import pandas as pd
import pytest

from app.services import backtest, historical_data


@pytest.fixture
def patched_loader(monkeypatch):
    prices = [100, 98, 96, 94, 92, 94, 96, 98, 100, 102, 104, 106, 104, 102, 100, 98, 100, 102]
    dates = pd.date_range("2024-01-01", periods=len(prices), freq="D").date

    def fake_load_price_history(ticker, start=None, end=None):
        return pd.DataFrame({"date": dates, "adj_close": [float(p) for p in prices]})

    monkeypatch.setattr(historical_data, "load_price_history", fake_load_price_history)
    return fake_load_price_history


def test_run_ticker_backtest_wires_params_through(patched_loader):
    result = backtest.run_ticker_backtest(
        "AAPL", short_window=3, long_window=5, cost_pct=0.002, starting_capital=50_000.0,
    )
    assert result.params == {
        "short_window": 3, "long_window": 5,
        "cost_pct": 0.002, "starting_capital": 50_000.0,
    }
    assert result.num_trades == 1
    assert result.trades[0].entry_price == pytest.approx(100.0 * 1.002)


def test_run_ticker_backtest_uses_defaults(patched_loader):
    result = backtest.run_ticker_backtest("AAPL")
    assert result.params == {
        "short_window": backtest.DEFAULT_SHORT_WINDOW,
        "long_window": backtest.DEFAULT_LONG_WINDOW,
        "cost_pct": backtest.DEFAULT_COST_PCT,
        "starting_capital": backtest.DEFAULT_STARTING_CAPITAL,
    }
    # 18 bars < default long_window=200 -> no defined MA anywhere, flat throughout
    assert result.trades == []
    assert result.final_status == "flat"
