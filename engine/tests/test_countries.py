# Country entity spine tests — schema/country.py + services/countries.py.
# No network calls; this chunk is static reference data only.
import pytest

from app.adapters.yfinance import _SUFFIX_MAP, _CURRENCY_MAP, _subunit_scale
from app.schema import Country, Currency, Exchange, Market
from app.services import countries
from app.services.countries import (
    COUNTRY_UNIVERSE_KEYS,
    LINKED_COUNTRIES,
    MARKET_EXCHANGES,
    get_country,
    get_major_companies,
    list_linked_countries,
)
from app.services.universes import known_universe_keys


# ---------------------------------------------------------------------------
# Linked lookups
# ---------------------------------------------------------------------------

def test_usa_has_three_universes_and_full_coverage():
    usa = get_country("USA")
    assert usa.market == Market.US
    assert usa.universe_keys == ["dow30", "nasdaq100", "sp500"]
    assert usa.has_company_data is True
    assert usa.has_exchange_data is True
    assert usa.is_linked is True


def test_india_has_two_exchanges():
    india = get_country("IND")
    assert india.exchanges == [Exchange.NSE, Exchange.BSE]
    assert india.has_exchange_data is True
    assert india.has_company_data is True


def test_germany_has_exchange_but_no_company_data():
    germany = get_country("DEU")
    assert germany.has_exchange_data is True
    assert germany.has_company_data is False


def test_unknown_iso3_returns_none_not_a_fabricated_stub():
    assert get_country("XYZ") is None


def test_lowercase_iso3_is_normalized():
    assert get_country("ind") is get_country("IND")


def test_list_linked_countries_returns_all_linked():
    assert len(list_linked_countries()) == 16
    assert {c.market for c in list_linked_countries()} == set(Market)


# ---------------------------------------------------------------------------
# Unlinked-country shape (proves the schema fits the future ~210 countries
# without a breaking change, even though this chunk doesn't populate them)
# ---------------------------------------------------------------------------

def test_directly_constructed_unlinked_country():
    nigeria = Country(iso3="NGA", name="Nigeria")
    assert nigeria.market is None
    assert nigeria.is_linked is False
    assert nigeria.has_exchange_data is False
    assert nigeria.has_company_data is False
    assert nigeria.macro_data_available is False


def test_computed_fields_round_trip_through_model_dump():
    usa = get_country("USA")
    dumped = usa.model_dump()
    assert dumped["is_linked"] is True
    assert dumped["has_company_data"] is True


# ---------------------------------------------------------------------------
# Consistency between the static registry and what's actually on disk /
# in the Market enum — catches orphaned universe files and forgotten markets.
# ---------------------------------------------------------------------------

def test_every_market_has_exchange_and_universe_entries():
    assert set(MARKET_EXCHANGES.keys()) == set(Market)
    assert set(COUNTRY_UNIVERSE_KEYS.keys()) == set(Market)


def test_universe_keys_are_a_subset_of_known_universe_keys():
    referenced = {key for keys in COUNTRY_UNIVERSE_KEYS.values() for key in keys}
    assert referenced.issubset(set(known_universe_keys()))


def test_every_known_universe_is_referenced_by_some_market():
    referenced = {key for keys in COUNTRY_UNIVERSE_KEYS.values() for key in keys}
    assert referenced == set(known_universe_keys())


# ---------------------------------------------------------------------------
# Bucket-A market correctness (9 markets added in commit 18cdeb9). The checks
# above only assert "some entry exists" for every Market; these assert the
# entry is the SPECIFIC Exchange/Market/Currency combination live-verified
# that session — a typo in any of these would previously pass CI silently.
# ---------------------------------------------------------------------------

_NEW_MARKET_SUFFIXES = [
    (".TO", Exchange.TSX,     Market.CA, Currency.CAD),
    (".AX", Exchange.ASX,     Market.AU, Currency.AUD),
    (".SW", Exchange.SIX,     Market.CH, Currency.CHF),
    (".KS", Exchange.KOSPI,   Market.KR, Currency.KRW),
    (".KQ", Exchange.KOSDAQ,  Market.KR, Currency.KRW),
    (".TW", Exchange.TWSE,    Market.TW, Currency.TWD),
    (".HK", Exchange.HKEX,    Market.HK, Currency.HKD),
    (".SS", Exchange.SSE,     Market.CN, Currency.CNY),
    (".SZ", Exchange.SZSE,    Market.CN, Currency.CNY),
    (".SR", Exchange.TADAWUL, Market.SA, Currency.SAR),
    (".JO", Exchange.JSE,     Market.ZA, Currency.ZAR),
]


@pytest.mark.parametrize("suffix,expected_exchange,expected_market,expected_currency", _NEW_MARKET_SUFFIXES)
def test_new_market_suffix_resolves_correctly(suffix, expected_exchange, expected_market, expected_currency):
    exchange, market, currency = _SUFFIX_MAP[suffix]
    assert exchange == expected_exchange
    assert market == expected_market
    assert currency == expected_currency


_NEW_MARKET_EXCHANGES = [
    (Market.CA, [Exchange.TSX]),
    (Market.AU, [Exchange.ASX]),
    (Market.CH, [Exchange.SIX]),
    (Market.KR, [Exchange.KOSPI, Exchange.KOSDAQ]),
    (Market.TW, [Exchange.TWSE]),
    (Market.HK, [Exchange.HKEX]),
    (Market.CN, [Exchange.SSE, Exchange.SZSE]),
    (Market.SA, [Exchange.TADAWUL]),
    (Market.ZA, [Exchange.JSE]),
]


@pytest.mark.parametrize("market,expected_exchanges", _NEW_MARKET_EXCHANGES)
def test_new_market_exchanges_are_correct(market, expected_exchanges):
    assert MARKET_EXCHANGES[market] == expected_exchanges


_NEW_LINKED_COUNTRIES = [
    ("CAN", "CA", "Canada", Market.CA, [Exchange.TSX]),
    ("AUS", "AU", "Australia", Market.AU, [Exchange.ASX]),
    ("CHE", "CH", "Switzerland", Market.CH, [Exchange.SIX]),
    ("KOR", "KR", "South Korea", Market.KR, [Exchange.KOSPI, Exchange.KOSDAQ]),
    ("TWN", "TW", "Taiwan", Market.TW, [Exchange.TWSE]),
    ("HKG", "HK", "Hong Kong", Market.HK, [Exchange.HKEX]),
    ("CHN", "CN", "China", Market.CN, [Exchange.SSE, Exchange.SZSE]),
    ("SAU", "SA", "Saudi Arabia", Market.SA, [Exchange.TADAWUL]),
    ("ZAF", "ZA", "South Africa", Market.ZA, [Exchange.JSE]),
]


@pytest.mark.parametrize("iso3,iso2,name,market,expected_exchanges", _NEW_LINKED_COUNTRIES)
def test_new_linked_country_is_correct(iso3, iso2, name, market, expected_exchanges):
    country = LINKED_COUNTRIES[iso3]
    assert country.iso2 == iso2
    assert country.name == name
    assert country.market == market
    assert country.exchanges == expected_exchanges


# ---------------------------------------------------------------------------
# JSE ZAc -> ZAR conversion mechanism (Chunk 2). yfinance reports JSE prices
# in South African cents, not Rand — _subunit_scale and _CURRENCY_MAP's ZAc
# entry are the two pieces of logic that fix this. Tested directly here
# (pure functions, no network) rather than only via shape checks, since a
# typo in the divisor or the trigger condition would silently produce prices
# 100x too large/small without ever failing a "does the key exist" check.
# ---------------------------------------------------------------------------

def test_subunit_scale_applies_to_jse_tickers():
    assert _subunit_scale("NPN.JO") == 100.0
    assert _subunit_scale("AGL.JO") == 100.0


def test_subunit_scale_is_case_insensitive():
    assert _subunit_scale("npn.jo") == 100.0


def test_subunit_scale_defaults_to_one_for_other_markets():
    assert _subunit_scale("AAPL") == 1.0
    assert _subunit_scale("RY.TO") == 1.0
    assert _subunit_scale("TSM.TW") == 1.0


def test_subunit_scale_divides_raw_cents_to_plausible_rand():
    # Naspers dayLow live-observed as 84000.0 (ZAc) this session -> should
    # resolve to 840.00 (ZAR), not stay at 84000.0 or become something else.
    raw_cents = 84000.0
    assert raw_cents / _subunit_scale("NPN.JO") == 840.0


def test_currency_map_resolves_zac_to_zar():
    assert _CURRENCY_MAP["ZAc"] == Currency.ZAR


# ---------------------------------------------------------------------------
# get_major_companies
# ---------------------------------------------------------------------------

def test_get_major_companies_dedupes_across_universes():
    usa = get_country("USA")
    companies = get_major_companies(usa)
    naive_total = sum(len(load) for load in (
        countries.load_universe("dow30"),
        countries.load_universe("nasdaq100"),
        countries.load_universe("sp500"),
    ))
    tickers = [row["ticker"] for row in companies]
    assert len(tickers) == len(set(tickers))
    assert len(companies) < naive_total


def test_get_major_companies_empty_when_no_company_data():
    germany = get_country("DEU")
    assert get_major_companies(germany) == []
