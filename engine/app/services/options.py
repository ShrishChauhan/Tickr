# Cache-orchestration for options chains + Greeks — mirrors services/price.py's
# shape. Underlying spot price is reused from services/price.py rather than
# re-fetched (per the approved plan: S is exactly what price.py already gets).
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..cache.base import CacheBackend
from ..cache.ttl_config import OPTIONS_CHAIN_TTL_SECONDS, RISK_FREE_RATE_TTL_SECONDS
from ..schema import (
    OptionChain, OptionContract, OptionExpirations,
    GreeksResult, GreeksInputs, GreeksExplanations,
)
from . import black_scholes
from . import price as price_service
from . import provider_registry
from .provider_registry import _yfinance_options_provider as _provider
from .provider_registry import _fred_risk_free_provider as _fred_provider


class OptionsLookupError(Exception):
    """Carries a message so routes.py can raise HTTPException(...) unchanged."""


async def get_expirations(cache: CacheBackend, ticker: str) -> OptionExpirations:
    ticker = ticker.upper()
    cache_key = f"options:expirations:{ticker}"

    raw = await cache.get(cache_key)
    if raw is not None:
        return OptionExpirations.model_validate(raw)

    try:
        expirations = await _provider.get_expirations(ticker)
    except Exception:
        expirations = []

    result = OptionExpirations(ticker=ticker, available=bool(expirations), expirations=list(expirations))
    await cache.set(cache_key, result.model_dump(mode="json"), OPTIONS_CHAIN_TTL_SECONDS,
                     data_type="options_expirations", ticker=ticker, source="yfinance")
    return result


async def get_chain(cache: CacheBackend, ticker: str, expiration: str) -> OptionChain:
    ticker = ticker.upper()
    cache_key = f"options:chain:{ticker}:{expiration}"

    raw = await cache.get(cache_key)
    if raw is not None:
        return OptionChain.model_validate(raw)

    try:
        chain = await _provider.get_chain(ticker, expiration)
    except Exception as e:
        raise OptionsLookupError(f"No options chain available for {ticker} {expiration}") from e

    result = OptionChain(
        ticker=ticker,
        expiration=expiration,
        calls=[OptionContract(**c) for c in chain["calls"]],
        puts=[OptionContract(**p) for p in chain["puts"]],
        fetched_at=chain["fetched_at"],
    )
    await cache.set(cache_key, result.model_dump(mode="json"), OPTIONS_CHAIN_TTL_SECONDS,
                     data_type="options_chain", ticker=ticker, source="yfinance")
    return result


async def _get_risk_free_rate(cache: CacheBackend) -> tuple[float, str, str]:
    """Returns (rate, r_as_of, source). Delegates the FRED-primary/yfinance-
    fallback chain to provider_registry.get_risk_free_rate() (Phase 9.1's
    resilience idiom, generalized in the Loader-registry refactor) — that
    walker re-raises if both providers fail, so a total outage surfaces as a
    hard error here too, rather than serving a stale/absent rate. r_as_of is
    FRED's own observation date when FRED served the rate (honest about the
    lag, not "now"); for the yfinance fallback it's still the fetch-time
    stamp, since ^IRX carries no finer-grained as-of of its own."""
    cache_key = "options:risk_free_rate"

    raw = await cache.get(cache_key)
    if raw is not None:
        rate, fetched_at = raw.get("rate"), raw.get("fetched_at")
        if rate is not None and fetched_at is not None:
            source = raw.get("source", "yfinance")
            r_as_of = raw.get("observation_date") or fetched_at
            return rate, r_as_of, source
        # Legacy/malformed cache entry missing a field this code now relies on
        # (e.g. written before `fetched_at` existed) — treat as a miss and refetch
        # rather than crash on every request until the TTL expires.

    rate, observation_date, source = await provider_registry.get_risk_free_rate()

    fetched_at = datetime.now(timezone.utc).isoformat()
    ticker = "DTB3" if source == "fred" else "^IRX"
    await cache.set(cache_key,
                     {"rate": rate, "fetched_at": fetched_at, "source": source, "observation_date": observation_date},
                     RISK_FREE_RATE_TTL_SECONDS,
                     data_type="risk_free_rate", ticker=ticker, source=source)
    r_as_of = observation_date or fetched_at
    return rate, r_as_of, source


def _find_contract(contracts: list[OptionContract], strike: float) -> Optional[OptionContract]:
    return next((c for c in contracts if abs(c.strike - strike) < 1e-6), None)


def _explanations(delta: float, gamma_val: float, theta_per_day: float,
                   vega_val: float, rho_per_percent: float) -> GreeksExplanations:
    return GreeksExplanations(
        delta=f"Delta of {delta:.3f} means the option's price moves ~${abs(delta):.2f} "
              f"for every $1 the underlying moves.",
        gamma=f"Gamma of {gamma_val:.4f} means delta itself shifts by ~{gamma_val:.4f} "
              f"for every $1 the underlying moves.",
        theta=f"Theta of ${theta_per_day:.2f}/day means this option loses about "
              f"${abs(theta_per_day):.2f} of value per day, all else equal.",
        vega=f"Vega of {vega_val:.3f} means a 1 percentage point rise in implied "
             f"volatility would change the price by ~${vega_val * 0.01:.2f}.",
        rho=f"Rho of {rho_per_percent:.3f} means a 1 percentage point rise in "
            f"interest rates would change the price by ~${rho_per_percent:.2f}.",
    )


async def calculate(
    cache: CacheBackend,
    ticker: str,
    expiration: str,
    strike: float,
    option_type: str,
    iv_override: Optional[float] = None,
) -> GreeksResult:
    ticker = ticker.upper()
    option_type = option_type.lower()
    if option_type not in ("call", "put"):
        raise OptionsLookupError(f"Invalid option type '{option_type}'. Valid: call, put")

    chain = await get_chain(cache, ticker, expiration)
    contract = _find_contract(chain.calls if option_type == "call" else chain.puts, strike)
    if contract is None:
        raise OptionsLookupError(f"No {option_type} contract at strike {strike} for {ticker} {expiration}")

    sigma = iv_override if iv_override is not None else contract.implied_volatility
    if sigma is None:
        raise OptionsLookupError("No implied volatility available for this contract and no override supplied")

    price_data = await price_service.get_price(cache, ticker)
    S = price_data.current_price
    if S is None:
        raise OptionsLookupError(f"No current price available for {ticker}")

    dividend_rate = await _provider.get_dividend_rate(ticker)
    q = (dividend_rate / S) if dividend_rate else 0.0

    r, r_as_of, r_source = await _get_risk_free_rate(cache)

    # Approximate expiration as market close (16:00) on the expiration date —
    # T is precise to within hours either way, immaterial for day/week-scale contracts.
    now = datetime.now(timezone.utc)
    expiration_dt = datetime.strptime(expiration, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(hours=16)
    T = black_scholes.year_fraction(now, expiration_dt)
    if T <= 0:
        raise OptionsLookupError(f"Expiration {expiration} has already passed")

    K = strike

    if option_type == "call":
        price = black_scholes.call_price(S, K, T, r, sigma, q)
        delta = black_scholes.delta_call(S, K, T, r, sigma, q)
        theta_annual = black_scholes.theta_call(S, K, T, r, sigma, q)
        rho_raw = black_scholes.rho_call(S, K, T, r, sigma, q)
    else:
        price = black_scholes.put_price(S, K, T, r, sigma, q)
        delta = black_scholes.delta_put(S, K, T, r, sigma, q)
        theta_annual = black_scholes.theta_put(S, K, T, r, sigma, q)
        rho_raw = black_scholes.rho_put(S, K, T, r, sigma, q)

    gamma_val = black_scholes.gamma(S, K, T, r, sigma, q)
    vega_val = black_scholes.vega(S, K, T, r, sigma, q)
    theta_per_day = theta_annual / 365
    rho_per_percent = rho_raw / 100

    return GreeksResult(
        ticker=ticker,
        expiration=expiration,
        option_type=option_type,
        price=price,
        delta=delta,
        gamma=gamma_val,
        theta_per_day=theta_per_day,
        vega=vega_val,
        rho_per_percent=rho_per_percent,
        explanations=_explanations(delta, gamma_val, theta_per_day, vega_val, rho_per_percent),
        inputs_used=GreeksInputs(
            S=S, K=K, T=T, r=r, q=q, sigma=sigma,
            price_as_of=price_data.fetched_at,
            iv_as_of=chain.fetched_at,
            r_as_of=r_as_of,
            r_source=r_source,
            contract_last_trade_at=contract.last_trade_date,
        ),
    )
