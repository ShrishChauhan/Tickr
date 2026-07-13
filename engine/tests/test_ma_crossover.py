import math

import pandas as pd
import pytest

from app.services.ma_crossover import sma, detect_crossovers, max_drawdown, run_backtest


# ---------------------------------------------------------------------------
# Reference series — hand-computed AND independently verified via a live
# pandas rolling-mean run before being trusted (see PROGRESS.md Session 32).
# short_window=3, long_window=5: golden cross at i=7 (SMA3=96.00 first
# exceeds SMA5=94.80), death cross at i=14 (SMA3=102.00 first drops below
# SMA5=103.20).
# ---------------------------------------------------------------------------

PRICES = [100, 98, 96, 94, 92, 94, 96, 98, 100, 102, 104, 106, 104, 102, 100, 98, 100, 102]
DATES = list(pd.date_range("2024-01-01", periods=len(PRICES), freq="D").date)


def _series():
    return pd.Series(DATES), pd.Series(PRICES, dtype=float)


# ---------------------------------------------------------------------------
# detect_crossovers: confirms the exact indices the reference cases rely on
# ---------------------------------------------------------------------------

def test_detect_crossovers_reference_series():
    prices = pd.Series(PRICES, dtype=float)
    short_ma = sma(prices, 3)
    long_ma = sma(prices, 5)
    events = detect_crossovers(short_ma, long_ma)
    assert events == [(7, "golden"), (14, "death")]


# ---------------------------------------------------------------------------
# Reference case: full backtest, zero cost
# ---------------------------------------------------------------------------

def test_reference_backtest_zero_cost():
    dates, prices = _series()
    result = run_backtest(dates, prices, short_window=3, long_window=5,
                           cost_pct=0.0, starting_capital=100_000.0)

    assert result.num_trades == 1
    trade = result.trades[0]
    assert trade.status == "closed"
    assert trade.entry_date == DATES[8]
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.exit_date == DATES[15]
    assert trade.exit_price == pytest.approx(98.0)
    assert trade.pnl == pytest.approx(-2000.0)
    assert trade.pnl_pct == pytest.approx(-2.0)

    expected_equity = [100_000] * 9 + [102_000, 104_000, 106_000, 104_000, 102_000, 100_000, 98_000, 98_000, 98_000]
    assert result.equity_curve == pytest.approx(expected_equity)
    assert result.total_return_pct == pytest.approx(-2.0)
    assert result.final_status == "flat"
    assert result.win_rate_pct == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Reference case: same series, with transaction cost applied on both legs
# ---------------------------------------------------------------------------

def test_reference_backtest_with_cost():
    dates, prices = _series()
    cost_pct = 0.001
    result = run_backtest(dates, prices, short_window=3, long_window=5,
                           cost_pct=cost_pct, starting_capital=100_000.0)

    trade = result.trades[0]
    expected_entry_fill = 100.0 * (1 + cost_pct)
    expected_exit_fill = 98.0 * (1 - cost_pct)
    assert trade.entry_price == pytest.approx(expected_entry_fill)
    assert trade.exit_price == pytest.approx(expected_exit_fill)

    expected_shares = 100_000.0 / expected_entry_fill
    expected_pnl = expected_shares * (expected_exit_fill - expected_entry_fill)
    assert trade.pnl == pytest.approx(expected_pnl)


# ---------------------------------------------------------------------------
# Edge case: open position at the end of the window — marked-to-market,
# never force-closed, never conflated with a realized trade
# ---------------------------------------------------------------------------

def test_open_position_not_force_closed():
    dates, prices = _series()
    dates, prices = dates.iloc[:10], prices.iloc[:10]  # golden cross at i=7, no death cross in range
    result = run_backtest(dates, prices, short_window=3, long_window=5,
                           cost_pct=0.0, starting_capital=100_000.0)

    assert result.final_status == "open"
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.status == "open"
    assert trade.entry_date == DATES[8]
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.exit_date is None
    assert trade.exit_price is None
    assert trade.pnl is None
    assert trade.pnl_pct is None

    assert result.num_trades == 0
    assert result.win_rate_pct is None

    expected_equity = [100_000] * 9 + [102_000]
    assert result.equity_curve == pytest.approx(expected_equity)


# ---------------------------------------------------------------------------
# max_drawdown: running-max vs the naive (and wrong) global-min/max formula
# ---------------------------------------------------------------------------

def test_max_drawdown_uses_running_max_not_global_min_max():
    equity = [100, 130, 90, 140, 120]
    assert max_drawdown(equity) == pytest.approx(30.769230769, abs=1e-6)
    naive_wrong = (max(equity) - min(equity)) / max(equity) * 100
    assert naive_wrong == pytest.approx(35.714285714, abs=1e-6)
    assert max_drawdown(equity) != pytest.approx(naive_wrong)


def test_max_drawdown_empty_and_flat():
    assert max_drawdown([]) == 0.0
    assert max_drawdown([100.0, 100.0, 100.0]) == 0.0


# ---------------------------------------------------------------------------
# Boundary checks
# ---------------------------------------------------------------------------

def test_series_exactly_long_window_has_no_crossovers():
    dates, prices = _series()
    dates, prices = dates.iloc[:5], prices.iloc[:5]  # exactly long_window=5 bars
    result = run_backtest(dates, prices, short_window=3, long_window=5, cost_pct=0.0)
    assert result.trades == []
    assert result.final_status == "flat"
    assert result.equity_curve == [100_000.0] * 5


def test_series_shorter_than_long_window_no_exception():
    dates, prices = _series()
    dates, prices = dates.iloc[:4], prices.iloc[:4]  # shorter than long_window=5
    result = run_backtest(dates, prices, short_window=3, long_window=5, cost_pct=0.0)
    assert result.trades == []
    assert result.equity_curve == [100_000.0] * 4


@pytest.mark.parametrize("kwargs,match", [
    ({"short_window": 0}, "short_window"),
    ({"short_window": 5, "long_window": 5}, "long_window"),
    ({"long_window": 3}, "long_window"),  # long_window < short_window(default omitted -> uses default 50) -> still <=, but here explicit
    ({"cost_pct": -0.01}, "cost_pct"),
    ({"cost_pct": 1.0}, "cost_pct"),
    ({"starting_capital": 0}, "starting_capital"),
    ({"starting_capital": -100}, "starting_capital"),
])
def test_invalid_params_raise_value_error(kwargs, match):
    dates, prices = _series()
    base = {"short_window": 3, "long_window": 5, "cost_pct": 0.0, "starting_capital": 100_000.0}
    base.update(kwargs)
    with pytest.raises(ValueError, match=match):
        run_backtest(dates, prices, **base)


def test_mismatched_lengths_raise_value_error():
    dates, prices = _series()
    with pytest.raises(ValueError, match="same length"):
        run_backtest(dates, prices.iloc[:-1], short_window=3, long_window=5)


# ---------------------------------------------------------------------------
# Sanity: no NaN/inf anywhere in the reference case's output
# ---------------------------------------------------------------------------

def test_reference_case_is_finite():
    dates, prices = _series()
    result = run_backtest(dates, prices, short_window=3, long_window=5, cost_pct=0.001)
    assert all(math.isfinite(v) for v in result.equity_curve)
    assert math.isfinite(result.total_return_pct)
    assert math.isfinite(result.max_drawdown_pct)
