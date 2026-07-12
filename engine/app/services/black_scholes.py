"""Pure Black-Scholes-Merton option pricing and Greeks. No cache/adapter/network
dependency — inputs are plain floats/datetimes, outputs are plain floats.

Convention: S=spot, K=strike, T=year fraction to expiration, r=risk-free rate
(annualized, decimal), sigma=annualized volatility (decimal), q=continuous
dividend yield (annualized, decimal).

Greek output units — NOT the units a standard retail options calculator
displays. Callers (Session B's service/schema layer) must convert explicitly
rather than pass these straight through to a UI:
- theta_call/theta_put are ANNUALIZED (value change per 1 year), not per
  calendar day. A typical calculator shows theta/365 (or /252).
- rho_call/rho_put are sensitivity to a full 1.0 (100 percentage points)
  change in r, not per 1% (0.01). A typical calculator shows rho/100.
Session B should either convert at that layer with clearly-named fields
(e.g. theta_per_day, rho_per_percent) or pass raw annualized/per-unit values
through with explicit unit labels in the schema — either way, the unit must
not be ambiguous by the time it reaches Session C's UI.
"""
import math
from datetime import datetime


def year_fraction(now: datetime, expiration: datetime) -> float:
    """Time to expiration in years, using a 365.25-day year (accounts for
    leap years without a calendar-aware day count)."""
    return (expiration - now).total_seconds() / (365.25 * 24 * 3600)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _d1(S: float, K: float, T: float, r: float, sigma: float, q: float) -> float:
    return (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))


def _d2(S: float, K: float, T: float, r: float, sigma: float, q: float) -> float:
    return _d1(S, K, T, r, sigma, q) - sigma * math.sqrt(T)


def call_price(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    d1 = _d1(S, K, T, r, sigma, q)
    d2 = _d2(S, K, T, r, sigma, q)
    return S * math.exp(-q * T) * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def put_price(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    d1 = _d1(S, K, T, r, sigma, q)
    d2 = _d2(S, K, T, r, sigma, q)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * math.exp(-q * T) * _norm_cdf(-d1)


def delta_call(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    return math.exp(-q * T) * _norm_cdf(_d1(S, K, T, r, sigma, q))


def delta_put(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    return -math.exp(-q * T) * _norm_cdf(-_d1(S, K, T, r, sigma, q))


def gamma(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    d1 = _d1(S, K, T, r, sigma, q)
    return math.exp(-q * T) * _norm_pdf(d1) / (S * sigma * math.sqrt(T))


def theta_call(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    d1 = _d1(S, K, T, r, sigma, q)
    d2 = _d2(S, K, T, r, sigma, q)
    term1 = -S * math.exp(-q * T) * _norm_pdf(d1) * sigma / (2 * math.sqrt(T))
    term2 = -r * K * math.exp(-r * T) * _norm_cdf(d2)
    term3 = q * S * math.exp(-q * T) * _norm_cdf(d1)
    return term1 + term2 + term3


def theta_put(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    d1 = _d1(S, K, T, r, sigma, q)
    d2 = _d2(S, K, T, r, sigma, q)
    term1 = -S * math.exp(-q * T) * _norm_pdf(d1) * sigma / (2 * math.sqrt(T))
    term2 = r * K * math.exp(-r * T) * _norm_cdf(-d2)
    term3 = -q * S * math.exp(-q * T) * _norm_cdf(-d1)
    return term1 + term2 + term3


def vega(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    d1 = _d1(S, K, T, r, sigma, q)
    return S * math.exp(-q * T) * _norm_pdf(d1) * math.sqrt(T)


def rho_call(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    d2 = _d2(S, K, T, r, sigma, q)
    return K * T * math.exp(-r * T) * _norm_cdf(d2)


def rho_put(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    d2 = _d2(S, K, T, r, sigma, q)
    return -K * T * math.exp(-r * T) * _norm_cdf(-d2)
