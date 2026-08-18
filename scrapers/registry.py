"""Registered adapters. Add a new source by importing it and appending an
instance here -- nothing else needs to change to wire it into the runner.
"""

from __future__ import annotations

from scrapers.adapters.berlin_viz import BerlinVizAdapter
from scrapers.adapters.db_bahnpark import DbBahnparkAdapter
from scrapers.adapters.frankfurt_mainziel import FrankfurtMainzielAdapter
from scrapers.adapters.hamburg_viz import HamburgVizAdapter
from scrapers.adapters.koeln_live import KoelnLiveAdapter
from scrapers.adapters.mobidata_bw_cities import (
    AalenMobidataBwAdapter,
    BietigheimBissingenMobidataBwAdapter,
    BuchenMobidataBwAdapter,
    FreiburgMobidataBwAdapter,
    HeilbronnMobidataBwAdapter,
    HerrenbergMobidataBwAdapter,
)
from scrapers.adapters.mobidata_bw_existing import (
    KarlsruheMobidataBwOccupancyAdapter,
    MannheimMobidataBwOccupancyAdapter,
    UlmMobidataBwOccupancyAdapter,
)
from scrapers.adapters.muenchen_parkraumwende import MuenchenParkraumwendeAdapter
from scrapers.adapters.qpark_fr import QParkFranceAdapter
from scrapers.adapters.qpark_nl import QParkNetherlandsAdapter
from scrapers.adapters.stuttgart_mobidata_bw import StuttgartMobidataBwAdapter
from scrapers.base import SourceAdapter

ADAPTERS: list[SourceAdapter] = [
    KoelnLiveAdapter(),
    MuenchenParkraumwendeAdapter(),
    BerlinVizAdapter(),
    HamburgVizAdapter(),
    FrankfurtMainzielAdapter(),
    StuttgartMobidataBwAdapter(),
    FreiburgMobidataBwAdapter(),
    AalenMobidataBwAdapter(),
    HerrenbergMobidataBwAdapter(),
    BietigheimBissingenMobidataBwAdapter(),
    BuchenMobidataBwAdapter(),
    HeilbronnMobidataBwAdapter(),
    MannheimMobidataBwOccupancyAdapter(),
    KarlsruheMobidataBwOccupancyAdapter(),
    UlmMobidataBwOccupancyAdapter(),
    DbBahnparkAdapter(),
    QParkNetherlandsAdapter(),
    QParkFranceAdapter(),
]
