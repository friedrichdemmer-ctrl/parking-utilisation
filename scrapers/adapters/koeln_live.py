"""Köln's live parking occupancy feed (stadt-koeln.de, city-hosted).

Resumes what the original ParkAPI/koeln-apps-parken source stopped doing in
May 2026 -- we already backfilled real capacity for these 46 garages
(capacity_overrides/koeln.csv), so this adapter only needs to supply fresh
free-space readings against the place_ids that already exist. No capacity
fetch needed here.
"""

from __future__ import annotations

from datetime import datetime, timezone

from scrapers.base import OccupancyRecord, SourceAdapter
from scrapers.util import normalize_name

FEED_URL = "https://www.stadt-koeln.de/externe-dienste/open-data/parking.php"

# This feed names garages differently from the ParkAPI archive it's meant to
# resume (e.g. "Galeria Kaufhof" vs our "Kaufhof"); verified by diffing the
# feed's distinct names against known koeln-apps-parken place_names by hand.
# Left-hand side is the feed's raw "parkhaus" string, normalized the same way
# as everything else before lookup.
NAME_ALIASES = {
    "Am Dom": "Dom",
    "Galeria Karstadt": "Karstadt",
    "Galeria Kaufhof": "Kaufhof",
    "Gerling Ring Karree": "Ringkarree",
    "Groß Sankt Martin": "Groß St. Martin",
    "LANXESS arena 1": "Lanxess-Arena P1",
    "LANXESS arena 2": "Lanxess-Arena P2",
    "LANXESS arena 4": "Lanxess-Arena P4",
    "Lungengasse": "BP Lungengasse",
    "P+R Marsdorf": "Marsdorf P+R",
    "REWE": "REWE City",
    "Sparkasse KölnBonn": "Sparkasse / Schaafenstr.",
    "Stadion P1 - nur bei Veranstaltungen geöffnet": "Stadion P1",
    "Stadion P3  - nur bei Veranstaltungen geöffnet": "Stadion P3",
    "Stadion P4 - nur bei Veranstaltungen geöffnet": "Stadion P4",
    "Stadion P6 - nur bei Veranstaltungen geöffnet": "Stadion P6",
    "Stadion P7 - nur bei Veranstaltungen geöffnet": "Stadion P7",
    "Stadion P8 Bus - nur bei Veranstaltungen geöffnet": "Stadion P8 Bus",
    "Stadion P8 PKW - nur bei Veranstaltungen geöffnet": "Stadion P8 PKW",
    "Stadtmitte": "Cäcilienstraße",
    "Theater-Parkhaus": "Theater/ Krebsgasse",
}
# Genuinely not in the archive at all (no capacity on file yet): Quincy,
# Schildergasse, Rheinauhafen Bayenturm/Museen/Oberländer Wall. Left
# unmatched on purpose -- adding them needs a capacity source first, same as
# any new garage.


class KoelnLiveAdapter(SourceAdapter):
    name = "koeln-apps-parken"  # matches the existing source_id in lots_meta
    fetcher_type = "http"
    occupancy_interval_seconds = 1800  # feed itself updates every 5-10 min; we don't need finer than our other sources

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        data = fetcher.get_json(FEED_URL)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        records = []
        unmatched = []
        for feature in data.get("features", []):
            attrs = feature.get("attributes", {})
            parkhaus = attrs.get("parkhaus")
            kapazitaet = attrs.get("kapazitaet")  # this feed's "kapazitaet" is actually FREE spaces, not total
            if not parkhaus or kapazitaet is None or kapazitaet < 0:
                continue  # -1 = "no data available" per the feed's own convention

            parkhaus = parkhaus.strip()
            lookup_name = NAME_ALIASES.get(parkhaus, parkhaus)
            place_id = known_garages.get(normalize_name(lookup_name))
            if place_id is None:
                unmatched.append(parkhaus)
                continue

            records.append(OccupancyRecord(place_id=place_id, ts=now, free=int(kapazitaet)))

        if unmatched:
            print(f"  koeln_live: {len(unmatched)} feed entries unmatched to a known place_id: {unmatched}")

        return records
