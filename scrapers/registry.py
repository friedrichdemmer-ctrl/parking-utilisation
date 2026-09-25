"""Registered adapters. Add a new source by importing it and appending an
instance here -- nothing else needs to change to wire it into the runner.
"""

from __future__ import annotations

from scrapers.adapters.amp_metropole_live import AmpMetropoleLiveAdapter
from scrapers.adapters.amsterdam_live import AmsterdamLiveAdapter
from scrapers.adapters.assen_live import AssenLiveAdapter
from scrapers.adapters.berlin_viz import BerlinVizAdapter
from scrapers.adapters.bordeaux_metropole_live import BordeauxMetropoleLiveAdapter
from scrapers.adapters.copenhagen_qpark import CopenhagenQParkAdapter
from scrapers.adapters.cork_live import CorkLiveAdapter
from scrapers.adapters.db_bahnpark import DbBahnparkAdapter
from scrapers.adapters.frankfurt_mainziel import FrankfurtMainzielAdapter
from scrapers.adapters.galway_live import GalwayLiveAdapter
from scrapers.adapters.gent_live import GentLiveAdapter
from scrapers.adapters.giessen_live import GiessenLiveAdapter
from scrapers.adapters.grenoble_live import GrenobleLiveAdapter
from scrapers.adapters.hamburg_viz import HamburgVizAdapter
from scrapers.adapters.heidelberg_live import HeidelbergLiveAdapter
from scrapers.adapters.interparking_belgium import InterparkingBelgiumAdapter
from scrapers.adapters.kaiserslautern_live import KaiserslauternLiveAdapter
from scrapers.adapters.koeln_live import KoelnLiveAdapter
from scrapers.adapters.la_rochelle_live import LaRochelleLiveAdapter
from scrapers.adapters.liege_hors_voirie import LiegeHorsVoirieAdapter
from scrapers.adapters.lyon_parc_auto_live import LyonParcAutoLiveAdapter
from scrapers.adapters.lyon_qpark import LyonQParkAdapter
from scrapers.adapters.mobidata_bw_cities import (
    AalenMobidataBwAdapter,
    BietigheimBissingenMobidataBwAdapter,
    BuchenMobidataBwAdapter,
    FreiburgMobidataBwAdapter,
    HeilbronnMobidataBwAdapter,
    HerrenbergMobidataBwAdapter,
)
from scrapers.adapters.mel_lille_live import MelLilleLiveAdapter
from scrapers.adapters.nantes_naolib_live import NantesNaolibLiveAdapter
from scrapers.adapters.mobidata_bw_existing import (
    KarlsruheMobidataBwOccupancyAdapter,
    MannheimMobidataBwOccupancyAdapter,
    UlmMobidataBwOccupancyAdapter,
)
from scrapers.adapters.moers_live import MoersLiveAdapter
from scrapers.adapters.muenchen_parkraumwende import MuenchenParkraumwendeAdapter
from scrapers.adapters.other_operators_fr import OtherOperatorsFranceAdapter
from scrapers.adapters.other_operators_nl import OtherOperatorsNetherlandsAdapter
from scrapers.adapters.qpark_fr import QParkFranceAdapter
from scrapers.adapters.qpark_nl import QParkNetherlandsAdapter
from scrapers.adapters.rouen_qpark import RouenQParkAdapter
from scrapers.adapters.saint_etienne_qpark import SaintEtienneQParkAdapter
from scrapers.adapters.strasbourg_live import StrasbourgLiveAdapter
from scrapers.adapters.stuttgart_mobidata_bw import StuttgartMobidataBwAdapter
from scrapers.adapters.toulouse_qpark import ToulouseQParkAdapter
from scrapers.adapters.tours_live import ToursLiveAdapter
from scrapers.adapters.vejle_live import VejleLiveAdapter
from scrapers.adapters.verviers_live import VerviersLiveAdapter
from scrapers.base import SourceAdapter

ADAPTERS: list[SourceAdapter] = [
    KoelnLiveAdapter(),
    LyonQParkAdapter(),
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
    AmpMetropoleLiveAdapter(),
    AmsterdamLiveAdapter(),
    AssenLiveAdapter(),
    BordeauxMetropoleLiveAdapter(),
    CopenhagenQParkAdapter(),
    CorkLiveAdapter(),
    DbBahnparkAdapter(),
    GalwayLiveAdapter(),
    GentLiveAdapter(),
    GiessenLiveAdapter(),
    GrenobleLiveAdapter(),
    HeidelbergLiveAdapter(),
    InterparkingBelgiumAdapter(),
    KaiserslauternLiveAdapter(),
    LaRochelleLiveAdapter(),
    LiegeHorsVoirieAdapter(),
    LyonParcAutoLiveAdapter(),
    MelLilleLiveAdapter(),
    MoersLiveAdapter(),
    NantesNaolibLiveAdapter(),
    QParkNetherlandsAdapter(),
    RouenQParkAdapter(),
    SaintEtienneQParkAdapter(),
    StrasbourgLiveAdapter(),
    ToulouseQParkAdapter(),
    ToursLiveAdapter(),
    VejleLiveAdapter(),
    VerviersLiveAdapter(),
    QParkFranceAdapter(),
    OtherOperatorsNetherlandsAdapter(),
    OtherOperatorsFranceAdapter(),
]
