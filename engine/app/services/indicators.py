"""Indicator math shared across strategy front-ends (ma_crossover.py,
rule_engine.py). Extracted out once a second real indicator (RSI) needed a
home — same reasoning backtest_core.py used for the execution loop: shared
math gets a neutral module once a second genuine consumer exists.

RSI methodology (Phase 8 slice 2): "RSI" is not one universally-agreed
formula. This module implements Wilder's original RSI (from Wilder's *New
Concepts in Technical Trading Systems*) — the first average gain/loss is a
simple average of the first `window` price changes, and every subsequent
average uses Wilder's smoothing recurrence
`avg = (prev_avg * (window - 1) + current) / window` (equivalent to
exponential smoothing with alpha = 1/window). This is what every mainstream
charting platform and trading library computes by default when asked for
"RSI." The known alternative, Cutler's RSI, replaces the smoothing
recurrence with a plain SMA of gains/losses throughout — Cutler invented
this specifically to remove Wilder's "data length dependency" (the smoothed
average is contaminated by all history before it, so it depends on where in
a price series you start computing). That property doesn't matter here:
this backtester always computes RSI over one fixed, complete historical
series per run, never splices or resumes a series mid-history — so Wilder's
is used, deliberately, not Cutler's.

Warmup: RSI needs one more warmup bar than an SMA of the same window, because
it operates on price *differences* (which start at index 1, not index 0),
not raw prices. The first `window` differences (indices 1..window) seed the
first average, so the first *defined* RSI value lands at index `window`
(not `window - 1`, which is where an SMA(window) first becomes defined).
Indices before that are NaN.

Implemented as an explicit loop over the recurrence rather than a vectorized
pandas trick: pandas' `.ewm(alpha=1/window, adjust=False)` seeds from the
first raw value, not a simple average of the first `window` diffs, so it
does not reproduce Wilder's recurrence exactly. An explicit loop matches
this codebase's existing style for recurrence-shaped logic (detect_crossovers,
detect_rising_edges are both explicit loops, not vectorized).
"""
import pandas as pd


def sma(prices: pd.Series, window: int) -> pd.Series:
    return prices.rolling(window).mean()


def rsi(prices: pd.Series, window: int) -> pd.Series:
    """Wilder's RSI. NaN for i < window; defined from i == window onward.
    avg_loss == 0 -> RSI = 100.0 (standard convention: no losses in the
    window means RS is undefined/infinite, treated as maximally overbought).
    """
    n = len(prices)
    prices = prices.reset_index(drop=True)
    result = [float("nan")] * n
    if n <= window:
        return pd.Series(result)

    diffs = prices.diff()
    gains = diffs.clip(lower=0)
    losses = (-diffs).clip(lower=0)

    avg_gain = gains.iloc[1:window + 1].mean()
    avg_loss = losses.iloc[1:window + 1].mean()
    result[window] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)

    for i in range(window + 1, n):
        avg_gain = (avg_gain * (window - 1) + gains.iloc[i]) / window
        avg_loss = (avg_loss * (window - 1) + losses.iloc[i]) / window
        result[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)

    return pd.Series(result)
