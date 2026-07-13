import pandas as pd
import pytest

from app.services.indicators import rsi, sma

# ---------------------------------------------------------------------------
# Wilder's RSI reference series (window=5), hand-computed and independently
# cross-checked with an isolated calculation before being trusted here (see
# PROGRESS.md's RSI session entry). i=5 and i=6 verify to exact fractions
# (75.0 and 400/21); i=7-11 verified to 6 decimal places.
# ---------------------------------------------------------------------------

PRICES = [100, 102, 101, 103, 105, 104, 106, 108, 107, 109, 111, 110]
WINDOW = 5

EXPECTED_RSI = {
    5: 75.0,
    6: 80.952381,
    7: 85.321101,
    8: 74.623872,
    9: 80.679649,
    10: 85.118741,
    11: 74.430416,
}


def _prices():
    return pd.Series(PRICES, dtype=float)


def test_rsi_reference_values():
    result = rsi(_prices(), WINDOW)
    for i, expected in EXPECTED_RSI.items():
        assert result.iloc[i] == pytest.approx(expected, abs=1e-5)


def test_rsi_warmup_boundary():
    # RSI needs one more warmup bar than an SMA of the same window: the
    # first `window` differences seed the first average, so the first
    # defined value lands at index `window`, not `window - 1`.
    result = rsi(_prices(), WINDOW)
    for i in range(WINDOW):
        assert pd.isna(result.iloc[i])
    assert not pd.isna(result.iloc[WINDOW])


def test_rsi_matches_sma_offset_by_one_extra_warmup_bar():
    prices = _prices()
    rsi_result = rsi(prices, WINDOW)
    sma_result = sma(prices, WINDOW)
    # SMA(window) is first defined at index window-1; RSI(window) at index
    # window -- confirms the "one extra bar" relationship stated above.
    assert not pd.isna(sma_result.iloc[WINDOW - 1])
    assert pd.isna(rsi_result.iloc[WINDOW - 1])


def test_rsi_avg_loss_zero_gives_100():
    # Strictly increasing prices over the window -> zero losses -> RSI = 100,
    # not a division-by-zero error.
    prices = pd.Series([100.0, 101, 102, 103, 104, 105])
    result = rsi(prices, 5)
    assert result.iloc[5] == pytest.approx(100.0)


def test_rsi_requires_more_than_window_bars():
    prices = pd.Series([100.0, 101, 102])
    result = rsi(prices, 5)
    assert result.isna().all()
