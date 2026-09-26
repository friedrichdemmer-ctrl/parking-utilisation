"""Live parking for Münster, via the city's parking-guidance XML
(stadt-muenster.de PLS-INet.xml, published as "Parkleitsystem -
Parkhausbelegung aktuell" on opendata.stadt-muenster.de, dl-de/by-2-0).

Münster used to arrive only via the defgsus community archive under
source_id "stadt-muenster-parken"; the archive has had nothing since
2025-01-13 because its scraper's page (index.php?id=10910) now 404s. This
reads the city's feed directly and keeps writing into the archive's
place_ids (its name is that legacy source_id). The gap from 2025-01-13
was backfilled once from Code for Münster's 15-minute history
(github.com/codeformuenster/parking-decks-muenster).

20 sites on 2026-09-26. Two renamed ones are mapped back to their archive
names: "Parkhaus Galeria" is the former "Parkhaus Karstadt" (Code for
Münster's history still labels it "PH Karstadt"). Readings for sites the
feed marks closed ("geschlossen") or without data ("keine Angabe") are
skipped -- their free count reads 0, which would look like a full garage.
Timestamps are German local time without an offset.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

FEED_URL = "https://www.stadt-muenster.de/ms/tiefbauamt/pls/PLS-INet.xml"
SOURCE_WEB_URL = "https://opendata.stadt-muenster.de/dataset/parkleitsystem-parkhausbelegung-aktuell"
BERLIN = ZoneInfo("Europe/Berlin")

LEGACY_NAMES = {
    "Parkhaus Stadthaus 3": "Parkhaus PH Stadthaus 3",
    "Parkhaus Galeria": "Parkhaus Karstadt",
}
NOT_REPORTING = {"geschlossen", "keine angabe"}


def place_id(name: str) -> str:
    return f"stadt-muenster-parken-{archive_slug(LEGACY_NAMES.get(name, name))}"


class MuensterLiveAdapter(SourceAdapter):
    name = "stadt-muenster-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _sites(self, fetcher) -> list[dict]:
        root = ET.fromstring(fetcher.get_bytes(FEED_URL))
        return [{child.tag: (child.text or "").strip() for child in p} for p in root.findall("parkhaus")]

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for s in self._sites(fetcher):
            name, total = s.get("bezeichnung"), s.get("gesamt", "")
            if not name or not total.isdigit() or int(total) <= 0:
                continue
            records.append(
                CapacityRecord(
                    place_id=place_id(name),
                    place_name=name,
                    city_name="Münster",
                    num_all=int(total),
                    source_id=self.name,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for s in self._sites(fetcher):
            name, free, stamp = s.get("bezeichnung"), s.get("frei", ""), s.get("zeitstempel")
            if not name or not free.isdigit() or not stamp or s.get("status", "").lower() in NOT_REPORTING:
                continue
            ts = datetime.strptime(stamp, "%d.%m.%Y %H:%M").replace(tzinfo=BERLIN).astimezone(timezone.utc)
            records.append(OccupancyRecord(place_id=place_id(name), ts=ts.isoformat(timespec="seconds"), free=int(free)))
        return records
