"""Live occupancy for Grenoble's garages, via the SMMAG (Syndicat Mixte des
Mobilités de l'Aire Grenobloise) API at data.mobilites-m.fr.

Pure occupancy upgrade, not a new source: all 17 Grenoble garages already
exist in lots_meta under the "bnls-qpark-fr"/"bnls-other-fr" source_ids,
imported from France's static, 2024-01-stale national parking registry
(BNLS) -- and this feed happens to use the *exact same* facility IDs
("38185-P-001" etc.), confirmed by cross-checking capacity numbers match
exactly. So rather than create new place_ids (which would duplicate these
17 garages under a second identity), this writes occupancy straight onto
the existing ones via PLACE_ID_MAP below. fetch_capacity is a no-op --
capacity already exists and this feed's own static companion
(data.mobilites-m.fr/api/points/json?types=parking) doesn't disagree with
it, so there's nothing to backfill.

Only a minority reliably report live data (3 of 17 as of writing:
CHAVANT -- the one BNLS already tagged as Q-Park's -- plus CATANE and
GRENOBLE-ESPLANADE); the rest show a null free-space value every time, not
occasionally, so likely never wired up rather than intermittently down.
Left in PLACE_ID_MAP anyway in case that changes -- the `if free is None`
check already skips them for free.
"""

from __future__ import annotations

from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

DYNAMIC_URL = "https://data.mobilites-m.fr/api/dyn/parking/json"

# SMMAG facility id -> existing lots_meta place_id (BNLS-derived, unchanged).
PLACE_ID_MAP = {
    "38185-P-001": "bnls-other-fr-38185-P-001-estacade",
    "38185-P-002": "bnls-other-fr-38185-P-002-gares-europole",
    "38185-P-003": "bnls-other-fr-38185-P-003-victor-hugo",
    "38185-P-004": "bnls-other-fr-38185-P-004-lafayette",
    "38185-P-005": "bnls-other-fr-38185-P-005-notre-dame-musee",
    "38185-P-006": "bnls-other-fr-38185-P-006-grenette-telepherique",
    "38185-P-007": "bnls-other-fr-38185-P-007-saint-bruno",
    "38185-P-008": "bnls-other-fr-38185-P-008-prefecture-les-halles",
    "38185-P-009": "bnls-qpark-fr-38185-P-009-chavant",
    "38185-P-010": "bnls-other-fr-38185-P-010-geants",
    "38185-P-011": "bnls-other-fr-38185-P-011-catane",
    "38185-P-012": "bnls-other-fr-38185-P-012-parc-mistral-mairie",
    "38185-P-013": "bnls-other-fr-38185-P-013-presqu-ile",
    "38185-P-014": "bnls-other-fr-38185-P-014-gares-palais-de-justice",
    "38185-P-015": "bnls-other-fr-38185-P-015-vaucanson",
    "38185-P-016": "bnls-other-fr-38185-P-016-gare-routiere",
    "38185-P-017": "bnls-other-fr-38185-P-017-grenoble-esplanade",
}


class GrenobleLiveAdapter(SourceAdapter):
    name = "grenoble-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600  # unused -- fetch_capacity is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        return []

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        data = fetcher.get_json(DYNAMIC_URL)
        records = []
        for smmag_id, place_id in PLACE_ID_MAP.items():
            entry = data.get(smmag_id)
            if not entry:
                continue
            free = entry.get("nb_places_libres")
            ts_ms = entry.get("time")
            if free is None or not ts_ms:
                continue
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")
            records.append(OccupancyRecord(place_id=place_id, ts=ts, free=int(free)))
        return records
