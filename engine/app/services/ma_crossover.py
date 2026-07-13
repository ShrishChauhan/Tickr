"""Pure moving-average crossover backtest engine. No cache/adapter/network/
DuckDB dependency — inputs are a dates Series and a prices Series (must
already be Adjusted Close, ascending by date), outputs are plain dataclasses.
Named for the specific strategy implemented here, not a general "backtest
engine" abstraction — that genericization is for whenever a second strategy
type actually exists to justify it.

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
"""
from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional

import pandas as pd


@dataclass(frozen=True)
class Trade:
    entry_date: date
    entry_price: float
    exit_date: Optional[date]
    exit_price: Optional[float]
    pnl: Optional[float]        # None while the position is still open (unrealized)
    pnl_pct: Optional[float]
    status: Literal["closed", "open"]


@dataclass(frozen=True)
class BacktestResult:
    dates: list
    equity_curve: list[float]
    trades: list[Trade]
    total_return_pct: float
    max_drawdown_pct: float
    num_trades: int                      # closed trades only
    win_rate_pct: Optional[float]        # None if num_trades == 0 (undefined, not 0%)
    final_status: Literal["flat", "open"]
    params: dict                         # transparency echo of the inputs used


def sma(prices: pd.Series, window: int) -> pd.Series:
    return prices.rolling(window).mean()


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


def max_drawdown(equity_curve: list[float]) -> float:
    """Positive percent (e.g. 7.55 means a 7.55% peak-to-trough decline).
    Computed via a running maximum, not global min/max — the naive
    (max(curve)-min(curve))/max(curve) formula overstates or misstates
    drawdown whenever the global min occurs chronologically before the
    global max."""
    if not equity_curve:
        return 0.0
    running_max = equity_curve[0]
    worst = 0.0
    for v in equity_curve:
        running_max = max(running_max, v)
        if running_max > 0:
            worst = max(worst, (running_max - v) / running_max * 100)
    return worst


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

    n = len(prices)
    if n == 0:
        return BacktestResult(
            dates=[], equity_curve=[], trades=[],
            total_return_pct=0.0, max_drawdown_pct=0.0,
            num_trades=0, win_rate_pct=None, final_status="flat", params=params,
        )

    dates = pd.Series(dates).reset_index(drop=True)
    prices = pd.Series(prices).reset_index(drop=True)

    short_ma = sma(prices, short_window)
    long_ma = sma(prices, long_window)
    event_at = dict(detect_crossovers(short_ma, long_ma))

    equity_curve: list[float] = [0.0] * n
    trades: list[Trade] = []

    capital = starting_capital
    shares = 0.0
    position_open = False
    entry_date = None
    entry_price = None
    pending_action: Optional[str] = None  # signal fired at bar i-1, fills at bar i

    for i in range(n):
        price = prices.iloc[i]

        if pending_action == "buy" and not position_open:
            fill_price = price * (1 + cost_pct)
            shares = capital / fill_price
            entry_date = dates.iloc[i]
            entry_price = fill_price
            capital = 0.0
            position_open = True
        elif pending_action == "sell" and position_open:
            fill_price = price * (1 - cost_pct)
            proceeds = shares * fill_price
            pnl = proceeds - shares * entry_price
            pnl_pct = (fill_price / entry_price - 1) * 100
            trades.append(Trade(
                entry_date=entry_date, entry_price=entry_price,
                exit_date=dates.iloc[i], exit_price=fill_price,
                pnl=pnl, pnl_pct=pnl_pct, status="closed",
            ))
            capital = proceeds
            shares = 0.0
            position_open = False
            entry_date = None
            entry_price = None
        pending_action = None

        equity_curve[i] = shares * price if position_open else capital

        kind = event_at.get(i)
        if kind == "golden" and not position_open:
            pending_action = "buy"
        elif kind == "death" and position_open:
            pending_action = "sell"

    final_status: Literal["flat", "open"] = "open" if position_open else "flat"
    if position_open:
        trades.append(Trade(
            entry_date=entry_date, entry_price=entry_price,
            exit_date=None, exit_price=None, pnl=None, pnl_pct=None, status="open",
        ))

    closed_trades = [t for t in trades if t.status == "closed"]
    num_trades = len(closed_trades)
    win_rate_pct = (
        sum(1 for t in closed_trades if t.pnl > 0) / num_trades * 100
        if num_trades > 0 else None
    )

    return BacktestResult(
        dates=list(dates),
        equity_curve=equity_curve,
        trades=trades,
        total_return_pct=(equity_curve[-1] / starting_capital - 1) * 100,
        max_drawdown_pct=max_drawdown(equity_curve),
        num_trades=num_trades,
        win_rate_pct=win_rate_pct,
        final_status=final_status,
        params=params,
    )
