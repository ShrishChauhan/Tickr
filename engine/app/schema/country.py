# Country entity — links ISO3 country codes to Tickr's existing Market/Exchange
# model, with coverage-completeness computed (never hand-set) from linked data.
# Population of the ~7 linked countries lives in services/countries.py; this
# file only defines the shape, so a future World Bank adapter (or anything
# else) can build ~210 unlinked Country instances without depending on
# services/.
from typing import List, Optional
from pydantic import BaseModel, computed_field
from .company import Market, Exchange


class Country(BaseModel):
    iso3: str                          # ISO 3166-1 alpha-3, primary key — e.g. "IND"
    iso2: Optional[str] = None         # populated for the 7 linked markets now; joined from World Bank's iso2Code for the rest in a later chunk
    name: str
    market: Optional[Market] = None    # None outside Tickr's 7 supported markets — stays Optional so the ~210 unlinked countries fit this same shape later
    exchanges: List[Exchange] = []
    universe_keys: List[str] = []      # keys into services.universes.load_universe()
    macro_data_available: bool = False # placeholder; no macro fetch exists yet — flips once a later chunk's World Bank adapter lands

    @computed_field
    @property
    def is_linked(self) -> bool:
        """True once this country has a Tickr Market assigned — independent
        of whether exchange or company data has actually been filled in."""
        return self.market is not None

    @computed_field
    @property
    def has_exchange_data(self) -> bool:
        return bool(self.exchanges)

    @computed_field
    @property
    def has_company_data(self) -> bool:
        return bool(self.universe_keys)
