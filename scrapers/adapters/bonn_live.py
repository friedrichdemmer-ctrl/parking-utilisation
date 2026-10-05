"""Live parking for the BCP (Bonner City Parkraum GmbH) garages in Bonn,
from the operator's XML feed bcpext.xml -- the resource behind the Bonn
open-data portal's dataset "Parkhäuser und Parkplätze Realtime-Belegung"
(opendata.bonn.de; licence CC BY-NC 4.0, i.e. non-commercial use only).

Bonn used to arrive only via the defgsus community archive under
source_id "bonn-bcp-parken", which reads this same feed; this adapter
takes over that source_id (its name). place_ids are the archive's:
f"bonn-bcp-parken-{archive_slug(bezeichnung)}" (lower-case names such as
"stadthaus_unten" -> "stadthaus-unten"), except that the feed's
"hauptbahnhof" was "bahnhof" when the archive first recorded it (the
same rename sync_archive.py's RENAME_MAP applies).

Each garage carries its own "zeitstempel" in correct local time
(Europe/Berlin; it matched the fetch time), used as the reading time.
Readings are skipped when "status" is not 0 (the archive keeps only
status 0; e.g. "stadthaus_unten" shows status 2 with 0 free) and when the
timestamp is more than STALE_AFTER old -- "karstadt" has been frozen at
25.07.2018 09:13 while still being listed.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

BERLIN = ZoneInfo("Europe/Berlin")
FEED_URL = "https://www.bcp-bonn.de/stellplatz/bcpext.xml"
WEB_URL = "https://www.bcp-bonn.de/"
STALE_AFTER = timedelta(hours=6)

LEGACY_SLUGS = {"hauptbahnhof": "bahnhof"}


def _place_id(name: str) -> str:
    slug = archive_slug(name)
    return f"bonn-bcp-parken-{LEGACY_SLUGS.get(slug, slug)}"


def _int(text: str | None) -> int | None:
    try:
        return int((text or "").strip())
    except ValueError:
        return None


class BonnLiveAdapter(SourceAdapter):
    name = "bonn-bcp-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _garages(self, fetcher) -> list[ET.Element]:
        return ET.fromstring(fetcher.get_bytes(FEED_URL)).findall("parkhaus")

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for p in self._garages(fetcher):
            name, capacity = (p.findtext("bezeichnung") or "").strip(), _int(p.findtext("gesamt"))
            if not name or not capacity:
                continue
            records.append(
                CapacityRecord(
                    place_id=_place_id(name),
                    place_name=name,
                    city_name="Bonn",
                    num_all=capacity,
                    source_id=self.name,
                    source_web_url=WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        now = datetime.now(timezone.utc)
        records = []
        for p in self._garages(fetcher):
            name = (p.findtext("bezeichnung") or "").strip()
            capacity, free = _int(p.findtext("gesamt")), _int(p.findtext("frei"))
            if not name or _int(p.findtext("status")) != 0 or free is None or not capacity or not 0 <= free <= capacity:
                continue
            try:
                ts = datetime.strptime((p.findtext("zeitstempel") or "").strip(), "%d.%m.%Y %H:%M")
            except ValueError:
                continue
            ts = ts.replace(tzinfo=BERLIN).astimezone(timezone.utc)
            if now - ts > STALE_AFTER:
                continue
            records.append(OccupancyRecord(place_id=_place_id(name), ts=ts.isoformat(timespec="seconds"), free=free))
        return records
