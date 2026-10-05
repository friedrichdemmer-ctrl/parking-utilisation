"""Live parking for Trier, via SWT (Stadtwerke Trier / SWT Parken GmbH)'s
XML feed parken-v2.xml -- the feed the defgsus community archive reads for
source_id "swt-trier-parken".

The SWT hosts refuse connections from outside Germany (tested 2026-10-05:
refused from the UK and the US, served normally from Fly's Frankfurt
region), so this adapter only works from a German IP -- which production is.

Format, from the archive scraper (defgsus/parking-scraper sources/
trier.py): a root element with one <parkhaus> per garage, carrying
<phname> (a short name -- "Basi", "City", "Hauptm", "Kons", "Osta",
"ParkPlaza", "Vieh", "Bahnhof"), <shortfree> (free short-term spaces)
and <shortmax> (short-term capacity). place_ids are
f"swt-trier-parken-{archive_slug(phname)}", the archive's rule, so all
eight currently-live garages keep their history. Capacity is shortmax --
already the value capacity_overrides uses for these garages.

Readings use the document's <datum>/<uhrzeit> (German local time) converted
to UTC, falling back to the fetch time if missing. Garages without a numeric
shortfree are skipped. shortmax moves over time (Basi read 436 in September
and 187 on 2026-10-05), so it is the short-term capacity at that moment; the
replace=yes rows in capacity_overrides/corrections_2026-09.csv still pin
four of these garages.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

FEED_URL = "https://service.swt.de/parken-v2.xml"
WEB_URL = "https://www.swt.de/"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _int(text: str | None) -> int | None:
    text = (text or "").strip()
    return int(text) if text.isdigit() else None


def _feed_time(root) -> str | None:
    """The document's <datum>/<uhrzeit> (German local time, e.g. 05.10.2026
    15:29:00) as UTC; None if missing, so the fetch time is used instead."""
    fields = {_local(el.tag): (el.text or "").strip() for el in root}
    try:
        local = datetime.strptime(f"{fields.get('datum')} {fields.get('uhrzeit')}", "%d.%m.%Y %H:%M:%S")
    except ValueError:
        return None
    return local.replace(tzinfo=ZoneInfo("Europe/Berlin")).astimezone(timezone.utc).isoformat(timespec="seconds")


class TrierLiveAdapter(SourceAdapter):
    name = "swt-trier-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _garages(self, fetcher) -> list[dict]:
        root = ET.fromstring(fetcher.get_bytes(FEED_URL))
        self._stamp = _feed_time(root)
        garages = []
        for el in root.iter():
            if _local(el.tag) != "parkhaus":
                continue
            fields = {_local(child.tag): (child.text or "").strip() for child in el}
            if fields.get("phname"):
                garages.append(fields)
        return garages

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for g in self._garages(fetcher):
            capacity = _int(g.get("shortmax"))
            if not capacity:
                continue
            records.append(
                CapacityRecord(
                    place_id=f"{self.name}-{archive_slug(g['phname'])}",
                    place_name=g["phname"],
                    city_name="Trier",
                    num_all=capacity,
                    source_id=self.name,
                    source_web_url=WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        garages = self._garages(fetcher)
        now = self._stamp or datetime.now(timezone.utc).isoformat(timespec="seconds")
        records = []
        for g in garages:
            free = _int(g.get("shortfree"))
            if free is None:
                continue
            records.append(OccupancyRecord(place_id=f"{self.name}-{archive_slug(g['phname'])}", ts=now, free=free))
        return records
