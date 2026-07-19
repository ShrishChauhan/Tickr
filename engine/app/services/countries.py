# Static country reference data — the ~7 Tickr-linked countries (Market ->
# Exchange/Currency is already supported; everything else is left for a
# future World Bank chunk to populate, using WB's own /v2/country response
# as the master ~217-country list instead of hand-curating one here).
from typing import Dict, List, Optional

from ..schema import Country, Market, Exchange
from .universes import load_universe

# Market -> its exchange(s). Not derived from adapters/yfinance.py's
# _SUFFIX_MAP (that dict is ticker-suffix-shaped for symbol parsing, not
# market grouping, and importing it here would invert the dependency
# direction — adapters depend on schema/services, not vice versa). Kept in
# sync with _SUFFIX_MAP by test_countries.py, not by import.
MARKET_EXCHANGES: Dict[Market, List[Exchange]] = {
    Market.US: [Exchange.NYSE, Exchange.NASDAQ, Exchange.AMEX],
    Market.UK: [Exchange.LSE],
    Market.DE: [Exchange.XETRA],
    Market.JP: [Exchange.TSE],
    Market.IN: [Exchange.NSE, Exchange.BSE],
    Market.BR: [Exchange.B3],
    Market.MX: [Exchange.BMV],
}

# Market -> universes.py keys representing "major companies" for that market.
# Hand-curated, not inferred from filenames — universe JSON entries carry no
# market/country field ({"ticker", "name"} only), so there is no safe general
# rule to infer "which country a universe key belongs to". Consistency with
# the actual files on disk is enforced by test_countries.py.
COUNTRY_UNIVERSE_KEYS: Dict[Market, List[str]] = {
    Market.US: ["dow30", "nasdaq100", "sp500"],
    Market.UK: [],
    Market.DE: [],
    Market.JP: [],
    Market.IN: ["nifty50"],
    Market.BR: [],
    Market.MX: [],
}


def _build_country(iso3: str, iso2: str, name: str, market: Market) -> Country:
    return Country(
        iso3=iso3,
        iso2=iso2,
        name=name,
        market=market,
        exchanges=MARKET_EXCHANGES[market],
        universe_keys=COUNTRY_UNIVERSE_KEYS[market],
    )


LINKED_COUNTRIES: Dict[str, Country] = {
    "USA": _build_country("USA", "US", "United States", Market.US),
    "GBR": _build_country("GBR", "GB", "United Kingdom", Market.UK),
    "DEU": _build_country("DEU", "DE", "Germany", Market.DE),
    "JPN": _build_country("JPN", "JP", "Japan", Market.JP),
    "IND": _build_country("IND", "IN", "India", Market.IN),
    "BRA": _build_country("BRA", "BR", "Brazil", Market.BR),
    "MEX": _build_country("MEX", "MX", "Mexico", Market.MX),
}


def get_country(iso3: str) -> Optional[Country]:
    """Look up a linked country by ISO3. Returns None for any of the ~210
    countries not yet onboarded — this does not fabricate stubs for them;
    that's a future World Bank chunk's job."""
    return LINKED_COUNTRIES.get(iso3.upper())


def list_linked_countries() -> List[Country]:
    return list(LINKED_COUNTRIES.values())


def get_major_companies(country: Country) -> List[dict]:
    """Flatten + de-dupe (by ticker, first-seen wins) every universe this
    country references. [] when country.has_company_data is False. Thin
    wrapper over services.universes.load_universe — no new company data."""
    seen: Dict[str, dict] = {}
    for key in country.universe_keys:
        for row in load_universe(key):
            seen.setdefault(row["ticker"], row)
    return list(seen.values())
