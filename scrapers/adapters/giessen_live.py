"""Gießen's own live parking-guidance page (giessen.de).

Found via active discovery rather than any catalogue (GovData/Mobilithek
have nothing for Gießen) -- the city's "Parken" page server-renders live
occupancy directly into the HTML (no JS/API layer to reverse-engineer),
with a page-level "Zuletzt aktualisiert" timestamp and a per-garage
Standort link whose query string happens to carry lat/lng too. Regex
parsing (no HTML-parsing dependency in this project) against a simple,
consistently-structured block -- no need for BeautifulSoup/lxml for
something this regular.

The page's own banner ("Störung des Parkleitsystem: Momentan können nicht
alle Parkhäuser angezeigt werden") means the garage list here can be a
subset of the full system on any given fetch -- adapters elsewhere in this
project already treat a source returning fewer garages on some runs than
others as normal, not an error.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

PAGE_URL = "https://www.giessen.de/Leben/Verkehr-und-Mobilit%C3%A4t/Parken/"

SLOT_RE = re.compile(
    r'<span class="slot-name">(?P<name>[^<]+)</span>.*?'
    r'<span class="free">Frei:\s*(?P<free>\d+)</span>\s*\|\s*'
    r'<span class="max">Gesamt:\s*(?P<total>\d+)</span>.*?'
    # ArcGIS webmap URLs give "center=lon,lat", not "lat,lon" -- verified
    # against Gießen's real coordinates (~50.58N, 8.67E) before trusting it.
    r'href="[^"]*center=(?P<lon>[\d.]+),(?P<lat>[\d.]+)[^"]*"',
    re.DOTALL,
)
UPDATED_RE = re.compile(r"Zuletzt aktualisiert:\s*(\d{1,2}):(\d{2})\s*Uhr\s*-\s*(\d{2})\.(\d{2})\.(\d{4})")


def _slug(name: str) -> str:
    s = name.lower()
    s = s.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class GiessenLiveAdapter(SourceAdapter):
    name = "giessen-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _timestamp(self, html: str) -> str | None:
        m = UPDATED_RE.search(html)
        if not m:
            return None
        hh, mm, dd, mo, yyyy = m.groups()
        dt = datetime(int(yyyy), int(mo), int(dd), int(hh), int(mm), tzinfo=ZoneInfo("Europe/Berlin"))
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")

    def _rows(self, fetcher):
        html = fetcher.get_text(PAGE_URL)
        ts = self._timestamp(html)
        for m in SLOT_RE.finditer(html):
            name = m.group("name").strip()
            if not name:
                continue
            yield name, int(m.group("free")), int(m.group("total")), float(m.group("lat")), float(m.group("lon")), ts

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for name, _free, total, lat, lon, _ts in self._rows(fetcher):
            records.append(
                CapacityRecord(
                    place_id=f"giessen-live-{_slug(name)}",
                    place_name=name,
                    city_name="Gießen",
                    num_all=total,
                    source_id=self.name,
                    latitude=lat,
                    longitude=lon,
                    source_web_url=PAGE_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for name, free, _total, _lat, _lon, ts in self._rows(fetcher):
            if ts is None:
                continue
            records.append(OccupancyRecord(place_id=f"giessen-live-{_slug(name)}", ts=ts, free=free))
        return records
