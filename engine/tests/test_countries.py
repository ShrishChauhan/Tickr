# Country entity spine tests — schema/country.py + services/countries.py.
# No network calls; this chunk is static reference data only.
from app.schema import Country, Exchange, Market
from app.services import countries
from app.services.countries import (
    COUNTRY_UNIVERSE_KEYS,
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


def test_list_linked_countries_returns_all_seven():
    assert len(list_linked_countries()) == 7
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
