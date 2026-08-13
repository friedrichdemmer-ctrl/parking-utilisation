"""Registered adapters. Add a new source by importing it and appending an
instance here -- nothing else needs to change to wire it into the runner.
"""

from __future__ import annotations

from scrapers.adapters.berlin_viz import BerlinVizAdapter
from scrapers.adapters.frankfurt_mainziel import FrankfurtMainzielAdapter
from scrapers.adapters.hamburg_viz import HamburgVizAdapter
from scrapers.adapters.koeln_live import KoelnLiveAdapter
from scrapers.adapters.muenchen_parkraumwende import MuenchenParkraumwendeAdapter
from scrapers.base import SourceAdapter

ADAPTERS: list[SourceAdapter] = [
    KoelnLiveAdapter(),
    MuenchenParkraumwendeAdapter(),
    BerlinVizAdapter(),
    HamburgVizAdapter(),
    FrankfurtMainzielAdapter(),
]
