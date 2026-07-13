"""General rule-based strategy model — Phase 8 slice 1. A composer will
eventually let a user assemble entry/exit rules from dropdowns:
[indicator] [comparator] [value or second indicator]. This module is the
backend data model + evaluation for that, proven against ma_crossover.py's
existing hand-verified MA-crossover as the first instance (see
test_rule_engine.py's parity tests).

Deliberately minimal vocabulary — three indicators (SMA, PRICE, RSI), two
comparators (CROSSES_ABOVE, CROSSES_BELOW). A bare "greater than" is not a
third comparator here: entry/exit are single-shot, edge-triggered trade
events (bar-timing, one signal per transition), not continuous position
filters, so "RSI greater than 70" is already expressible as
CROSSES_ABOVE(RSI, 70). A genuinely stateful filter
("only trade while price > 200-SMA", AND-ed with a separate trigger) is a
distinct future feature needing rule-combination logic not built here.

The execution loop (bar-timing, cost, sizing, drawdown) is NOT reimplemented
here — see backtest_core.run_signal_backtest, shared verbatim with
ma_crossover.py. Only signal DETECTION generalizes.
"""
from dataclasses import asdict, dataclass
from typing import Literal, Optional, Union

import pandas as pd

from . import backtest_core
from .backtest_core import BacktestResult
from .indicators import rsi, sma

IndicatorType = Literal["SMA", "PRICE", "RSI"]
ComparatorType = Literal["CROSSES_ABOVE", "CROSSES_BELOW"]


@dataclass(frozen=True)
class Indicator:
    type: IndicatorType
    window: Optional[int] = None  # required for SMA/RSI, unused for PRICE

    def compute(self, prices: pd.Series) -> pd.Series:
        if self.type == "PRICE":
            return prices
        if self.type == "SMA":
            if not self.window or self.window < 1:
                raise ValueError("SMA indicator requires window >= 1")
            return sma(prices, self.window)
        if self.type == "RSI":
            if not self.window or self.window < 1:
                raise ValueError("RSI indicator requires window >= 1")
            return rsi(prices, self.window)
        raise ValueError(f"Unknown indicator type: {self.type}")


def _safe_compare(left: pd.Series, right: Union[pd.Series, float], above: bool) -> pd.Series:
    """NaN in either operand -> NaN (undefined), never coerced to False.
    Plain pandas comparison gives `NaN > x == False`, which would silently
    treat an indicator's warmup period as "condition not met" instead of
    "unknown" — risking a false edge exactly at the warmup boundary. Mirrors
    ma_crossover.detect_crossovers's explicit `pd.isna(s) or pd.isna(l)` guard."""
    right_s = right if isinstance(right, pd.Series) else pd.Series(right, index=left.index)
    raw = left.gt(right_s) if above else left.lt(right_s)
    undefined = left.isna() | right_s.isna()
    return raw.astype(object).mask(undefined, other=float("nan"))


def detect_rising_edges(condition: pd.Series) -> list[int]:
    """condition: NaN = undefined (resets memory), else bool. Returns bar
    indices where it transitions False -> True. Same reset semantics as
    ma_crossover.detect_crossovers: a NaN bar clears the "previous state"
    memory so the first defined bar after a gap is never itself an edge."""
    edges: list[int] = []
    prev: Optional[bool] = None
    for i in range(len(condition)):
        c = condition.iloc[i]
        if pd.isna(c):
            prev = None
            continue
        if prev is not None and c and not prev:
            edges.append(i)
        prev = c
    return edges


@dataclass(frozen=True)
class Rule:
    left: Indicator
    comparator: ComparatorType
    right: Union[Indicator, float]  # "value or second indicator"

    def evaluate(self, prices: pd.Series) -> list[int]:
        """Bar indices where this rule's condition transitions from
        not-satisfied to satisfied."""
        left_series = self.left.compute(prices)
        right_series = self.right.compute(prices) if isinstance(self.right, Indicator) else self.right
        above = self.comparator == "CROSSES_ABOVE"
        condition = _safe_compare(left_series, right_series, above=above)
        return detect_rising_edges(condition)


@dataclass(frozen=True)
class Strategy:
    entry: Rule
    exit: Rule


def run_rule_backtest(
    dates: pd.Series,
    prices: pd.Series,
    strategy: Strategy,
    cost_pct: float = 0.001,
    starting_capital: float = 100_000.0,
) -> BacktestResult:
    entry_bars = set(strategy.entry.evaluate(prices))
    exit_bars = set(strategy.exit.evaluate(prices))
    params = {
        "entry_rule": asdict(strategy.entry),
        "exit_rule": asdict(strategy.exit),
        "cost_pct": cost_pct,
        "starting_capital": starting_capital,
    }
    return backtest_core.run_signal_backtest(
        dates, prices, entry_bars, exit_bars, cost_pct, starting_capital, params,
    )
