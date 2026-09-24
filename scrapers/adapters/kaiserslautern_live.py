"""Kaiserslautern's own live parking-guidance feed (kaiserslautern.de).

api.parkendd.de lists Kaiserslautern as "active_support" and this project's
legacy collector.py has been polling it for six weeks, but every single lot
it returns turned out frozen at one value the whole time -- api.parkendd.de
itself has gone stale (its own "last_downloaded" metadata reads 2024-08-01).
This adapter bypasses that dead proxy and goes straight to the city's XML
feed, which does carry genuinely live, varying readings.

No address or coordinates in this feed -- just id/name/capacity/free/status.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

FEED_URL = "https://www.kaiserslautern.de/live_tools/pls/pls.xml"


def _slug(name: str) -> str:
    s = name.lower()
    s = s.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


def _parse_timestamp(s: str | None) -> str | None:
    # e.g. "23.09.2026 16:25:00" -- Europe/Berlin local time, no offset given
    if not s:
        return None
    try:
        dt = datetime.strptime(s, "%d.%m.%Y %H:%M:%S").replace(tzinfo=ZoneInfo("Europe/Berlin"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


class KaiserslauternLiveAdapter(SourceAdapter):
    name = "kaiserslautern-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        text = fetcher.get_text(FEED_URL)
        root = ET.fromstring(text)
        ts = _parse_timestamp((root.findtext("Zeitstempel") or "").strip() or None)
        for lot in root.findall("Parkhaus"):
            lot_id = (lot.findtext("ID") or "").strip()
            name = (lot.findtext("Name") or "").strip()
            if not lot_id or not name:
                continue
            yield lot, lot_id, name, ts

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for lot, lot_id, name, _ts in self._rows(fetcher):
            gesamt = lot.findtext("Gesamt")
            if not gesamt:
                continue
            try:
                total = int(gesamt)
            except ValueError:
                continue
            records.append(
                CapacityRecord(
                    place_id=f"kaiserslautern-live-{lot_id}-{_slug(name)}",
                    place_name=name,
                    city_name="Kaiserslautern",
                    num_all=total,
                    source_id=self.name,
                    source_web_url="https://www.kaiserslautern.de/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for lot, lot_id, name, ts in self._rows(fetcher):
            if (lot.findtext("Status") or "").strip() != "Offen":
                continue
            aktuell = lot.findtext("Aktuell")
            if not aktuell or ts is None:
                continue
            try:
                free = int(aktuell)
            except ValueError:
                continue
            records.append(
                OccupancyRecord(place_id=f"kaiserslautern-live-{lot_id}-{_slug(name)}", ts=ts, free=free)
            )
        return records
