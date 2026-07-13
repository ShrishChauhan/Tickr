"""MA-crossover-specific signal detection. No cache/adapter/network/DuckDB
dependency — inputs are a dates Series and a prices Series (must already be
Adjusted Close, ascending by date), outputs are plain dataclasses re-exported
from backtest_core.

Bar-timing convention (look-ahead avoidance): a crossover signal detected at
bar T (using T's fully-defined short/long SMA) fills at bar T+1's price —
never at bar T's own price, which would require knowing that bar's close
before it happened. Signal and execution both use Adjusted Close rather than
raw Open/Close: there is no "Adjusted Open" in the source data, and keeping
signal + execution on one single, already dividend/split-consistent series
avoids any risk of a mismatch between a dividend-adjusted signal series and
a synthetically-adjusted execution series (which could produce spurious
jumps right around ex-dividend dates near a crossover).

Documented limitation, not fixed here: Adjusted Close for a given historical
date is retroactively recomputed every time a *later* dividend is paid
(adjustment factors are cumulative-backward). A signal on an old bar,
computed from a present-day-adjusted series, technically reflects dividends
paid after that date — a small, inherent form of look-ahead in any backtest
that uses a single present-day-adjusted price series across a long
historical window. Fixing this needs point-in-time-vintage adjustment
factors, which the historical data pipeline (Phase 7.1) doesn't store.

The execution loop (bar-timing fill, cost, sizing, running-max drawdown) now
lives in backtest_core.py, shared with the general rule_engine.py path — this
module only detects MA-crossover signals and hands precomputed entry/exit
bars to that shared loop. See rule_engine.py for the generalized
[indicator] [comparator] [value or indicator] model this crossover is also
expressible in (proven equivalent in test_rule_engine.py).
"""
from typing import Optional

import pandas as pd

from . import backtest_core
from .backtest_core import BacktestResult, Trade, max_drawdown
from .indicators import sma

__all__ = ["Trade", "BacktestResult", "max_drawdown", "sma", "detect_crossovers", "run_backtest"]


def detect_crossovers(short_ma: pd.Series, long_ma: pd.Series) -> list[tuple[int, str]]:
    """Returns (index, "golden"|"death") for each bar where both MAs are
    defined at that bar and at the immediately preceding defined bar, and
    the short/long relative order flips. The first bar where both MAs
    become defined can never itself be a crossover — there's no prior
    defined state to compare against."""
    events = []
    prev_above: Optional[bool] = None
    for i in range(len(short_ma)):
        s, l = short_ma.iloc[i], long_ma.iloc[i]
        if pd.isna(s) or pd.isna(l):
            prev_above = None
            continue
        above = s > l
        if prev_above is not None and above != prev_above:
            events.append((i, "golden" if above else "death"))
        prev_above = above
    return events


def run_backtest(
    dates: pd.Series,
    prices: pd.Series,
    short_window: int = 50,
    long_window: int = 200,
    cost_pct: float = 0.001,
    starting_capital: float = 100_000.0,
) -> BacktestResult:
    if short_window < 1:
        raise ValueError("short_window must be >= 1")
    if long_window <= short_window:
        raise ValueError("long_window must be > short_window")
    if not (0 <= cost_pct < 1):
        raise ValueError("cost_pct must be in [0, 1)")
    if starting_capital <= 0:
        raise ValueError("starting_capital must be > 0")
    if len(dates) != len(prices):
        raise ValueError("dates and prices must be the same length")

    params = {
        "short_window": short_window, "long_window": long_window,
        "cost_pct": cost_pct, "starting_capital": starting_capital,
    }

    short_ma = sma(prices, short_window)
    long_ma = sma(prices, long_window)
    events = detect_crossovers(short_ma, long_ma)
    entry_bars = {i for i, kind in events if kind == "golden"}
    exit_bars = {i for i, kind in events if kind == "death"}

    return backtest_core.run_signal_backtest(
        dates, prices, entry_bars, exit_bars, cost_pct, starting_capital, params,
    )
