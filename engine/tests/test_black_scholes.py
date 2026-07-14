from datetime import datetime

import pytest

from app.services.black_scholes import (
    call_price,
    put_price,
    delta_call,
    delta_put,
    gamma,
    theta_call,
    theta_put,
    vega,
    rho_call,
    rho_put,
    year_fraction,
    _d1,
    _d2,
)


# ---------------------------------------------------------------------------
# Reference value (Hull, Options, Futures & Other Derivatives)
# ---------------------------------------------------------------------------

def test_reference_value_hull_example():
    S, K, T, r, sigma, q = 42, 40, 0.5, 0.10, 0.20, 0.0
    assert call_price(S, K, T, r, sigma, q) == pytest.approx(4.76, abs=0.01)
    assert put_price(S, K, T, r, sigma, q) == pytest.approx(0.81, abs=0.01)


def test_reference_value_hull_example_with_dividend_yield():
    # Hull, Options, Futures & Other Derivatives — end-of-chapter problem
    # ("An index currently stands at 696 and has a volatility of 30% per
    # annum. The risk-free rate of interest is 7% per annum and the index
    # provides a dividend yield of 4% per annum. Calculate the value of a
    # three-month European put with an exercise price of 700.") Widely
    # reproduced published solution (e.g. Hull OFOD solutions manual, Ch.17):
    # d1 = 0.0868, d2 = -0.0632, N(-d1) = 0.4654, N(-d2) = 0.5252, put = 40.6.
    # This is the one numeric-anchor case in this file with q > 0 — every
    # other anchor (Hull's call/put example, all boundary checks) uses q=0,
    # and put-call parity alone can't validate the q term (it holds via the
    # N(x)+N(-x)=1 identity regardless of whether d1/d2 use q correctly).
    S, K, T, r, sigma, q = 696, 700, 0.25, 0.07, 0.30, 0.04
    assert _d1(S, K, T, r, sigma, q) == pytest.approx(0.0868, abs=0.0001)
    assert _d2(S, K, T, r, sigma, q) == pytest.approx(-0.0632, abs=0.0001)
    # Published answer is 40.6, itself rounded from 4-decimal N(d) values —
    # tolerance widened slightly to absorb that source-side rounding.
    assert put_price(S, K, T, r, sigma, q) == pytest.approx(40.6, abs=0.05)


# ---------------------------------------------------------------------------
# Put-call parity: C - P == S - K*exp(-r*T), across varied inputs
# ---------------------------------------------------------------------------

PARITY_CASES = [
    (42, 40, 0.5, 0.10, 0.20, 0.0),      # Hull reference case
    (100, 100, 1.0, 0.05, 0.30, 0.0),    # at-the-money, no dividend
    (150, 120, 0.25, 0.03, 0.45, 0.02),  # deep ITM call, short-dated, high vol, dividend
    (50, 80, 2.0, 0.08, 0.15, 0.01),     # deep OTM call, long-dated
    (200, 200, 0.01, 0.15, 0.60, 0.05),  # near-expiry, high vol, high dividend
]


@pytest.mark.parametrize("S,K,T,r,sigma,q", PARITY_CASES)
def test_put_call_parity(S, K, T, r, sigma, q):
    import math
    c = call_price(S, K, T, r, sigma, q)
    p = put_price(S, K, T, r, sigma, q)
    assert (c - p) == pytest.approx(S * math.exp(-q * T) - K * math.exp(-r * T), abs=1e-6)


# ---------------------------------------------------------------------------
# Boundary checks
# ---------------------------------------------------------------------------

def test_deep_itm_call_converges_to_intrinsic_as_sigma_shrinks():
    import math
    S, K, T, r, q = 100, 60, 1.0, 0.05, 0.0
    tiny_sigma = 1e-6
    intrinsic = S * math.exp(-q * T) - K * math.exp(-r * T)
    assert call_price(S, K, T, r, tiny_sigma, q) == pytest.approx(intrinsic, abs=0.01)


def test_call_delta_bounds_across_strike_sweep():
    S, T, r, sigma, q = 100, 1.0, 0.05, 0.25, 0.0
    for K in range(20, 401, 20):
        d = delta_call(S, K, T, r, sigma, q)
        assert 0.0 <= d <= 1.0


def test_put_delta_bounds_across_strike_sweep():
    S, T, r, sigma, q = 100, 1.0, 0.05, 0.25, 0.0
    for K in range(20, 401, 20):
        d = delta_put(S, K, T, r, sigma, q)
        assert -1.0 <= d <= 0.0


def test_gamma_and_vega_never_negative_across_strike_sweep():
    S, T, r, sigma, q = 100, 1.0, 0.05, 0.25, 0.0
    for K in range(20, 401, 20):
        assert gamma(S, K, T, r, sigma, q) >= 0.0
        assert vega(S, K, T, r, sigma, q) >= 0.0


# ---------------------------------------------------------------------------
# year_fraction: exact expected value, 365.25-day year convention
# ---------------------------------------------------------------------------

def test_year_fraction_known_dates():
    now = datetime(2026, 1, 1)
    expiration = datetime.fromisoformat("2026-07-02T00:00:00")
    # 182 calendar days / 365.25
    assert year_fraction(now, expiration) == pytest.approx(0.49828884325804246, abs=1e-9)


# ---------------------------------------------------------------------------
# Sanity: theta/rho are computable and finite (no NaN/inf from the reference case)
# ---------------------------------------------------------------------------

def test_theta_and_rho_are_finite():
    import math
    S, K, T, r, sigma, q = 42, 40, 0.5, 0.10, 0.20, 0.0
    for fn in (theta_call, theta_put, rho_call, rho_put):
        v = fn(S, K, T, r, sigma, q)
        assert math.isfinite(v)


# ---------------------------------------------------------------------------
# Phase 9.1 FRED cutover: the risk-free rate changes from ^IRX to FRED's DTB3,
# a genuinely (slightly) different but equally correct rate — not a bug to
# match exactly. This proves the resulting Greeks move by exactly the amount
# rho predicts for that rate gap, not by an unexplained/arbitrary amount.
# ---------------------------------------------------------------------------

def test_price_shift_from_irx_to_dtb3_rate_matches_rho_prediction():
    S, K, T, sigma, q = 100.0, 100.0, 0.25, 0.25, 0.0
    # 2026-07-08 live comparison (see Phase 9.1 plan): ^IRX 3.723% vs DTB3 3.73%.
    r_irx = 0.03723
    r_dtb3 = 0.0373
    delta_r = r_dtb3 - r_irx

    price_irx = call_price(S, K, T, r_irx, sigma, q)
    price_dtb3 = call_price(S, K, T, r_dtb3, sigma, q)
    rho_at_irx = rho_call(S, K, T, r_irx, sigma, q)  # dPrice/dr, decimal r

    actual_shift = price_dtb3 - price_irx
    predicted_shift = rho_at_irx * delta_r

    # First-order (rho) approximation over a ~0.7bp rate gap — second-order
    # curvature is negligible at this scale, so a tight tolerance is expected,
    # not just "close enough."
    assert actual_shift == pytest.approx(predicted_shift, abs=1e-6)
    # And the shift itself should be tiny in dollar terms, consistent with a
    # sub-basis-point rate change, not a meaningfully different price.
    assert abs(actual_shift) < 0.01
