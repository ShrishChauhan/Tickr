import math

import pandas as pd
import pytest

from app.services import ma_crossover
from app.services.historical_data import load_price_history
from app.services.rule_engine import (
    Indicator,
    Rule,
    Strategy,
    detect_rising_edges,
    run_rule_backtest,
)

# ---------------------------------------------------------------------------
# Same hand-verified 18-bar reference series as test_ma_crossover.py: golden
# cross at i=7 (SMA3 first exceeds SMA5), death cross at i=14 (SMA3 first
# drops below SMA5).
# ---------------------------------------------------------------------------

PRICES = [100, 98, 96, 94, 92, 94, 96, 98, 100, 102, 104, 106, 104, 102, 100, 98, 100, 102]
DATES = list(pd.date_range("2024-01-01", periods=len(PRICES), freq="D").date)


def _series():
    return pd.Series(DATES), pd.Series(PRICES, dtype=float)


def _crossover_strategy(short_window=3, long_window=5) -> Strategy:
    short = Indicator("SMA", short_window)
    long = Indicator("SMA", long_window)
    return Strategy(
        entry=Rule(short, "CROSSES_ABOVE", long),
        exit=Rule(short, "CROSSES_BELOW", long),
    )


# ---------------------------------------------------------------------------
# Indicator.compute
# ---------------------------------------------------------------------------

def test_indicator_price_is_identity():
    _, prices = _series()
    result = Indicator("PRICE").compute(prices)
    assert result.equals(prices)


def test_indicator_sma_matches_ma_crossover_sma():
    _, prices = _series()
    result = Indicator("SMA", 3).compute(prices)
    expected = ma_crossover.sma(prices, 3)
    assert result.equals(expected)


def test_indicator_sma_requires_window():
    _, prices = _series()
    with pytest.raises(ValueError, match="window"):
        Indicator("SMA").compute(prices)


# ---------------------------------------------------------------------------
# detect_rising_edges: NaN-reset semantics match ma_crossover.detect_crossovers
# ---------------------------------------------------------------------------

def test_rule_evaluate_matches_detect_crossovers_indices():
    _, prices = _series()
    short_ma = ma_crossover.sma(prices, 3)
    long_ma = ma_crossover.sma(prices, 5)
    events = ma_crossover.detect_crossovers(short_ma, long_ma)
    assert events == [(7, "golden"), (14, "death")]

    strategy = _crossover_strategy()
    entry_edges = strategy.entry.evaluate(prices)
    exit_edges = strategy.exit.evaluate(prices)
    assert entry_edges == [7]
    assert exit_edges == [14]


def test_detect_rising_edges_treats_nan_as_undefined_not_false():
    # Two NaN bars, then False, then True: the True must register as an
    # edge (prev reset to None by the NaNs, not left as False from before
    # the gap).
    condition = pd.Series([float("nan"), float("nan"), False, True])
    assert detect_rising_edges(condition) == [3]


def test_detect_rising_edges_no_false_edge_at_warmup_boundary():
    # First defined bar is True. If NaN were coerced to False (pandas'
    # default `NaN > x` behavior), this would wrongly register as an edge at
    # i=2. It must not, since there is no prior *defined* state to compare
    # against.
    condition = pd.Series([float("nan"), float("nan"), True, True])
    assert detect_rising_edges(condition) == []


# ---------------------------------------------------------------------------
# Parity: rule_engine.run_rule_backtest reproduces ma_crossover.run_backtest
# exactly, on the hand-verified synthetic series (zero-cost and with-cost)
# ---------------------------------------------------------------------------

def test_parity_synthetic_zero_cost():
    dates, prices = _series()
    strategy = _crossover_strategy()

    specific = ma_crossover.run_backtest(dates, prices, short_window=3, long_window=5,
                                          cost_pct=0.0, starting_capital=100_000.0)
    general = run_rule_backtest(dates, prices, strategy, cost_pct=0.0, starting_capital=100_000.0)

    assert general.equity_curve == pytest.approx(specific.equity_curve)
    assert general.total_return_pct == pytest.approx(specific.total_return_pct)
    assert general.max_drawdown_pct == pytest.approx(specific.max_drawdown_pct)
    assert general.num_trades == specific.num_trades
    assert general.win_rate_pct == pytest.approx(specific.win_rate_pct)
    assert general.final_status == specific.final_status
    assert len(general.trades) == len(specific.trades)
    for g, s in zip(general.trades, specific.trades):
        assert g.entry_date == s.entry_date
        assert g.entry_price == pytest.approx(s.entry_price)
        assert g.exit_date == s.exit_date
        assert g.exit_price == (pytest.approx(s.exit_price) if s.exit_price is not None else None)
        assert g.pnl == (pytest.approx(s.pnl) if s.pnl is not None else None)
        assert g.status == s.status


def test_parity_synthetic_with_cost():
    dates, prices = _series()
    strategy = _crossover_strategy()
    cost_pct = 0.001

    specific = ma_crossover.run_backtest(dates, prices, short_window=3, long_window=5,
                                          cost_pct=cost_pct, starting_capital=100_000.0)
    general = run_rule_backtest(dates, prices, strategy, cost_pct=cost_pct, starting_capital=100_000.0)

    assert general.equity_curve == pytest.approx(specific.equity_curve)
    assert general.total_return_pct == pytest.approx(specific.total_return_pct)
    assert len(general.trades) == len(specific.trades)
    for g, s in zip(general.trades, specific.trades):
        assert g.entry_price == pytest.approx(s.entry_price)
        assert g.exit_price == pytest.approx(s.exit_price)
        assert g.pnl == pytest.approx(s.pnl)


def test_parity_open_position_not_force_closed():
    dates, prices = _series()
    dates, prices = dates.iloc[:10], prices.iloc[:10]  # golden cross at i=7, no death cross in range
    strategy = _crossover_strategy()

    specific = ma_crossover.run_backtest(dates, prices, short_window=3, long_window=5,
                                          cost_pct=0.0, starting_capital=100_000.0)
    general = run_rule_backtest(dates, prices, strategy, cost_pct=0.0, starting_capital=100_000.0)

    assert general.final_status == specific.final_status == "open"
    assert general.equity_curve == pytest.approx(specific.equity_curve)
    assert len(general.trades) == len(specific.trades) == 1
    assert general.trades[0].status == "open"


# ---------------------------------------------------------------------------
# Parity on real AAPL data (5000+ bars, 2006-2026): the real regression
# proof — the 18-bar synthetic case never exercises multiple crossovers,
# long warmup, or the open-position-at-end path the way 20 years of AAPL does.
# ---------------------------------------------------------------------------

def test_parity_real_aapl_data():
    df = load_price_history("AAPL")
    dates, prices = df["date"], df["adj_close"]
    strategy = _crossover_strategy(short_window=50, long_window=200)

    specific = ma_crossover.run_backtest(dates, prices, short_window=50, long_window=200)
    general = run_rule_backtest(dates, prices, strategy,
                                 cost_pct=specific.params["cost_pct"],
                                 starting_capital=specific.params["starting_capital"])

    assert general.equity_curve == pytest.approx(specific.equity_curve)
    assert general.total_return_pct == pytest.approx(specific.total_return_pct)
    assert general.max_drawdown_pct == pytest.approx(specific.max_drawdown_pct)
    assert general.num_trades == specific.num_trades
    assert general.win_rate_pct == pytest.approx(specific.win_rate_pct)
    assert general.final_status == specific.final_status
    assert len(general.trades) == len(specific.trades)
    for g, s in zip(general.trades, specific.trades):
        assert g.entry_date == s.entry_date
        assert g.entry_price == pytest.approx(s.entry_price)
        assert g.exit_date == s.exit_date
        assert g.status == s.status
        if s.status == "closed":
            assert g.exit_price == pytest.approx(s.exit_price)
            assert g.pnl == pytest.approx(s.pnl)
            assert g.pnl_pct == pytest.approx(s.pnl_pct)


# ---------------------------------------------------------------------------
# A second, genuinely different strategy the vocabulary now expresses:
# price crosses above/below its own 200-day SMA (classic trend-follow) —
# proof the model isn't just a crossover-in-disguise.
# ---------------------------------------------------------------------------

def test_price_vs_sma_strategy_runs_and_is_finite():
    df = load_price_history("AAPL")
    dates, prices = df["date"], df["adj_close"]
    price = Indicator("PRICE")
    sma200 = Indicator("SMA", 200)
    strategy = Strategy(
        entry=Rule(price, "CROSSES_ABOVE", sma200),
        exit=Rule(price, "CROSSES_BELOW", sma200),
    )

    result = run_rule_backtest(dates, prices, strategy)
    assert math.isfinite(result.total_return_pct)
    assert math.isfinite(result.max_drawdown_pct)
    assert all(math.isfinite(v) for v in result.equity_curve)
    assert result.num_trades > 0  # AAPL crosses its 200-SMA many times over 20y


# ---------------------------------------------------------------------------
# Rule against a fixed scalar value ("value or second indicator")
# ---------------------------------------------------------------------------

def test_rule_against_scalar_value():
    _, prices = _series()
    rule = Rule(Indicator("PRICE"), "CROSSES_ABOVE", 100.0)
    # Prices: 100,98,96,94,92,94,96,98,100,102,104,106,104,102,100,98,100,102.
    # Index 8 is exactly 100 (not > 100, no edge). First strictly-above bar is
    # index 9 (102). Price dips back to 98 (index 15) then rises through 100
    # (index 16, not > 100) to 102 (index 17) -- a second rising edge, since
    # the condition went false in between.
    edges = rule.evaluate(prices)
    assert edges == [9, 17]


# ---------------------------------------------------------------------------
# RSI: NaN-warmup discriminating edge test (mirrors the SMA-warmup
# discriminating tests above) and a full mean-reversion Strategy against
# real AAPL data.
# ---------------------------------------------------------------------------

def test_rsi_indicator_no_false_edge_at_warmup_boundary():
    # RSI(5)'s first defined value is at index 5 (see test_indicators.py).
    # A rule of RSI CROSSES_BELOW some threshold must not register a false
    # edge merely because the warmup NaNs end -- there must be a genuine
    # defined-to-defined transition.
    prices = pd.Series([100, 102, 101, 103, 105, 104, 106, 108], dtype=float)
    rule = Rule(Indicator("RSI", 5), "CROSSES_BELOW", 200.0)  # never true once defined
    assert rule.evaluate(prices) == []


def test_rsi_mean_reversion_strategy_runs_and_is_finite():
    df = load_price_history("AAPL")
    dates, prices = df["date"], df["adj_close"]
    rsi14 = Indicator("RSI", 14)
    strategy = Strategy(
        entry=Rule(rsi14, "CROSSES_BELOW", 30.0),
        exit=Rule(rsi14, "CROSSES_ABOVE", 70.0),
    )

    result = run_rule_backtest(dates, prices, strategy)
    assert math.isfinite(result.total_return_pct)
    assert math.isfinite(result.max_drawdown_pct)
    assert all(math.isfinite(v) for v in result.equity_curve)
    assert result.num_trades > 0  # AAPL crosses RSI 30/70 many times over 20y
