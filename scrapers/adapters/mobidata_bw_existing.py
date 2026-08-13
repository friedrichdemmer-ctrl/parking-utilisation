"""Live occupancy for Mannheim, Karlsruhe, and Ulm garages already on file
from earlier ParkAPI-era sources, matched by name onto MobiData BW's
per-city feeds (see mobidata_bw_common.py).

Unlike mobidata_bw_cities.py, these three write NO new lots_meta rows.
Their MobiData BW entries turned out to be the *same physical garages* we
already carry (confirmed while researching a Mannheim/Karlsruhe capacity
backfill -- e.g. MobiData's "H6" is the same garage as our existing "H6"
and "H6, Tiefgarage" rows from two separate legacy sources), so adding a
third source with new place_ids would have compounded an existing
duplication problem instead of fixing anything. The name maps below were
built and verified by hand, the same way capacity_overrides/mannheim.csv
and karlsruhe.csv were -- garages with no confident match are simply
skipped, not guessed at.
"""

from __future__ import annotations

from scrapers.adapters.mobidata_bw_common import fetch_items
from scrapers.base import OccupancyRecord, SourceAdapter

# MobiData BW facility name -> existing place_id(s) it corresponds to.
# Some garages are represented twice in our archive under two different
# legacy sources (e.g. Mannheim's "ffh-parken" and "parken-mannheim"), so a
# single MobiData match can fan out to more than one place_id.
MANNHEIM_NAME_MAP: dict[str, tuple[str, ...]] = {
    "Hauptbahnhof P5": ("parken-mannheim-Hauptbahnhof-P5-Parkhaus",),
    "Kunsthalle": ("parken-mannheim-Kunsthalle-Tiefgarage",),
    "U2 Tiefgarage": ("ffh-parken-mannheim-U2", "parken-mannheim-U2-Tiefgarage"),
    "D5 Reiß-Museum": ("ffh-parken-mannheim-D5-Reiss-Museum", "parken-mannheim-D5-Reiss-Museum-Tiefgarage"),
    "Marktplatz G1": ("ffh-parken-mannheim-G1-Marktplatz", "parken-mannheim-G1-Marktplatz-Tiefgarage"),
    "Hauptbahnhof P1": ("ffh-parken-mannheim-Hbf-P1", "parken-mannheim-Hauptbahnhof-P1-Tiefgarage"),
    "N6 Komforthaus": ("ffh-parken-mannheim-N6-Komfort", "parken-mannheim-N6-Komforthaus"),
    "N6 Standardhaus": ("ffh-parken-mannheim-N6-Standard-Holiday-Inn", "parken-mannheim-N6-Standardhaus"),
    "Hauptbahnhof P3": ("ffh-parken-mannheim-Hbf-P3",),  # parken-mannheim's "P3/P4" is a combined row, skipped
    "H6": ("ffh-parken-mannheim-H6", "parken-mannheim-H6-Tiefgarage"),
    "M4a": ("ffh-parken-mannheim-Parkplatz-M4a", "parken-mannheim-M4a-Parkplatz"),
    "D3": ("ffh-parken-mannheim-D3", "parken-mannheim-D3-Tiefgarage"),
    "N1 Stadthaus": ("ffh-parken-mannheim-N1-Stadthaus",),  # parken-mannheim's "N1/N2" is a combined row, skipped
    "N2 Stadthaus": ("ffh-parken-mannheim-N2-Stadthaus",),
    "Hauptbahnhof P2": ("ffh-parken-mannheim-Hbf-P2", "parken-mannheim-Hauptbahnhof-P2-Parkhaus"),
}

KARLSRUHE_NAME_MAP: dict[str, tuple[str, ...]] = {
    "Kongresszentrum PH1": ("karlsruhe-parken-Kongresszentrum-PH1",),
    "Kongresszentrum PH2": ("karlsruhe-parken-Kongresszentrum-PH2",),
    "Luisenstraße": ("karlsruhe-parken-Luisenstrasse",),
    "Herrenstraße / Zirkel": ("karlsruhe-parken-Herrenstrasse-Zirkel",),
    "Passagehof": ("karlsruhe-parken-Passagehof",),
    "Schlossplatz": ("karlsruhe-parken-Schlossplatz",),
    "Kreuzstraße": ("karlsruhe-parken-Kreuzstrasse-C-A",),
    "Kronenplatz": ("karlsruhe-parken-Kronenplatz",),
    "Friedrichsplatz": ("karlsruhe-parken-Friedrichsplatz",),
    "Karstadt": ("karlsruhe-parken-Karstadt",),
    "IHK": ("karlsruhe-parken-Industrie-und-Handelskammer",),
    "Marktplatz": ("karlsruhe-parken-Marktplatz",),
    "Mendelssohnplatz": ("karlsruhe-parken-Mendelssohnplatz-Scheck-In",),
    "Ettlinger Tor": ("karlsruhe-parken-Ettlinger-Tor",),
    "Stephanplatz": ("karlsruhe-parken-Stephanplatz",),
    "Akademiestraße": ("karlsruhe-parken-Akademiestrasse",),
    "Postgalerie": ("karlsruhe-parken-Post-Galerie",),
    "Ludwigsplatz": ("karlsruhe-parken-Ludwigsplatz",),
}

ULM_NAME_MAP: dict[str, tuple[str, ...]] = {
    "Parkhaus Salzstadel": ("parken-in-ulm-Salzstadel",),
    "Parkhaus Deutschhaus": ("parken-in-ulm-Deutschhaus",),
    "Parkhaus Fischerviertel": ("parken-in-ulm-Fischerviertel",),
    "Congresscentrum Nord": ("parken-in-ulm-Congress-Centrum-Nord-Basteicenter",),
    "Parkhaus am Rathaus": ("parken-in-ulm-Am-Rathaus",),
    "Parkhaus Theater": ("parken-in-ulm-Theater",),
    # "Parkhaus am Bahnhof" has no existing counterpart -- not in the map, skipped.
}


class _MobidataBwExistingOccupancyAdapter(SourceAdapter):
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600  # unused -- fetch_capacity is a no-op, capacity already on file
    occupancy_interval_seconds = 30 * 60

    source_uids: tuple[str, ...] = ()
    name_map: dict[str, tuple[str, ...]] = {}

    def fetch_capacity(self, fetcher):
        return []

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for uid in self.source_uids:
            for item in fetch_items(fetcher, uid):
                if not item.get("has_realtime_data"):
                    continue
                place_ids = self.name_map.get((item.get("name") or "").strip())
                if not place_ids:
                    continue
                free = item.get("realtime_free_capacity")
                ts = item.get("realtime_data_updated_at")
                capacity = item.get("capacity")
                if free is None or not ts:
                    continue
                if capacity and free > capacity * 1.1:
                    continue  # same tolerance as scrapers/validate.py; this source's own capacity isn't in known_capacities
                for place_id in place_ids:
                    records.append(OccupancyRecord(place_id=place_id, ts=ts, free=int(free)))
        return records


class MannheimMobidataBwOccupancyAdapter(_MobidataBwExistingOccupancyAdapter):
    name = "mobidata-bw-mannheim-occupancy"
    source_uids = ("mannheim",)
    name_map = MANNHEIM_NAME_MAP


class KarlsruheMobidataBwOccupancyAdapter(_MobidataBwExistingOccupancyAdapter):
    name = "mobidata-bw-karlsruhe-occupancy"
    source_uids = ("karlsruhe",)
    name_map = KARLSRUHE_NAME_MAP


class UlmMobidataBwOccupancyAdapter(_MobidataBwExistingOccupancyAdapter):
    name = "mobidata-bw-ulm-occupancy"
    source_uids = ("ulm_sensors",)
    name_map = ULM_NAME_MAP
