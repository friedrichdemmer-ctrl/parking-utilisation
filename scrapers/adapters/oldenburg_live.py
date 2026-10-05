"""Live parking for Oldenburg (Oldb), from the city's parking-guidance XML
feed on oldenburg-service.de (the data behind oldenburg-service.de/pls/).

Oldenburg used to arrive only via the defgsus community archive under
source_id "oldenburg-service-parken". The archive scraper reads this
same feed (at its old address, cros.php, which now redirects to
_cros.php), so this adapter takes over that source_id (its name).

The feed's names have grown longer since the archive's garages were first
recorded ("Parkhaus Am Waffenplatz" for the archive's "Waffenplatz");
LEGACY_SLUGS maps them back onto the existing place_ids -- the same
pairs sync_archive.py's RENAME_MAP applies to the archive's newer columns.
"City" (archive name "City-Parkhaus-Staulinie") is no longer in the feed.

"Aktuell" is the number of occupied spaces (the city's HTML table,
pls2.php, shows Gesamt - Aktuell as free), so free = Gesamt - Aktuell.
The feed's "Zeitstempel" is correct local time (Europe/Berlin; it matched
the fetch time to the minute) and is used as the reading time. Readings
are only kept for Status "Offen": "Geschlossen" garages keep their last
count and "Stoerung" ones report nonsense (Theatergarage 0 of 0).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

BERLIN = ZoneInfo("Europe/Berlin")
FEED_URL = "https://oldenburg-service.de/_cros.php"
WEB_URL = "https://oldenburg-service.de/pls/#/hauspark"

# archive_slug(current feed name) -> archive_slug(name on file)
LEGACY_SLUGS = {
    "Parkhaus-Am-Waffenplatz": "Waffenplatz",
    "Parkhaus-Galeria-Kaufhof": "Galeria-Kaufhof",
    "Parkplatz-Pferdemarkt": "Pferdemarkt",
    "Parkhaus-Bahnhof-ZOB": "Hbf-ZOB",
    "Parkplatz-Theaterwall": "Theaterwall",
    "Parkhaus-Theatergarage": "Theatergarage",
    "Parkhaus-Heiligengeist-Hoefe": "Heiligengeist-Hoefe",
    "Parkhaus-Schlosshoefe": "Schlosshoefe",
    "Parkhaus-Alter-Stadthafen-Cinemaxx": "Cinemaxx",
    "City-Parkhaus-Staulinie": "City",
}


def _place_id(name: str) -> str:
    slug = archive_slug(name)
    return f"oldenburg-service-parken-{LEGACY_SLUGS.get(slug, slug)}"


def _int(text: str | None) -> int | None:
    try:
        return int((text or "").strip())
    except ValueError:
        return None


class OldenburgLiveAdapter(SourceAdapter):
    name = "oldenburg-service-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _feed(self, fetcher) -> ET.Element:
        return ET.fromstring(fetcher.get_bytes(FEED_URL))

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for p in self._feed(fetcher).findall("Parkhaus"):
            name, capacity = (p.findtext("Name") or "").strip(), _int(p.findtext("Gesamt"))
            if not name or not capacity:
                continue
            records.append(
                CapacityRecord(
                    place_id=_place_id(name),
                    place_name=name,
                    city_name="Oldenburg",
                    num_all=capacity,
                    source_id=self.name,
                    source_web_url=WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        root = self._feed(fetcher)
        stamp = (root.findtext("Zeitstempel") or "").strip()
        if not stamp:
            return []
        ts = datetime.strptime(stamp, "%d.%m.%Y %H:%M:%S").replace(tzinfo=BERLIN)
        ts = ts.astimezone(timezone.utc).isoformat(timespec="seconds")
        records = []
        for p in root.findall("Parkhaus"):
            name = (p.findtext("Name") or "").strip()
            capacity, occupied = _int(p.findtext("Gesamt")), _int(p.findtext("Aktuell"))
            if not name or (p.findtext("Status") or "").strip() != "Offen":
                continue
            if not capacity or occupied is None or not 0 <= occupied <= capacity:
                continue
            records.append(OccupancyRecord(place_id=_place_id(name), ts=ts, free=capacity - occupied))
        return records
