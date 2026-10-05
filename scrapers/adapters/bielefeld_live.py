"""Live parking for Bielefeld, scraped from the city's parking page
(bielefeld.de/parken, formerly /de/sv/verkehr/parken/park/), which lists
every garage and car park with capacity and, for those on the
parking-guidance system, the free count and a "Stand" time.

Bielefeld used to arrive only via the defgsus community archive under
source_id "sw-bielefeld-parken", which scrapes this same page; this
adapter takes over that source_id (its name). place_ids are the
archive's, f"sw-bielefeld-parken-{archive_slug(name)}", except that
Marktpassage has since gained a "(nicht für gasbetriebene Fahrzeuge!)"
suffix and is mapped back (the same rename sync_archive.py's RENAME_MAP
applies).

There is no machine-readable live feed: the city's open-data WFS layer
"parkplaetze_p" (bielefeld01.de, dataset "Parkplätze") has b_pls_rest /
b_pls_zeit / b_pls_status columns for the same 21 sites, but on
2026-10-05 they were hours behind the page (Stand 08:05 while the page
showed 15:15, and a garage the WFS called GESCHLOSSEN was open on the
page), so the page is used.

Each site's "Stand" (title of its colour dot) is correct local time
(Europe/Berlin; it matched the fetch time) and is used as the reading
time. The dot's colour is the status: green/yellow/red have a free count,
grey means "Parkhaus geschlossen" and is skipped, as are sites without a
dot (not on the guidance system).
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

BERLIN = ZoneInfo("Europe/Berlin")
PAGE_URL = "https://www.bielefeld.de/parken"

LEGACY_SLUGS = {
    "Tiefgarage-Marktpassage-nicht-fur-gasbetriebene-Fahrzeuge": "Tiefgarage-Marktpassage",
}

BLOCK_RE = re.compile(r'<h3 id="pnr\d+">(.*?)</h3>(.*?)</table>', re.S)
STATUS_RE = re.compile(r'class="pls-status-info">(.*?)</div>', re.S)
CAPACITY_RE = re.compile(r"(\d+)\s*Plätze")
FREE_RE = re.compile(r"(\d+)\s*frei")
STAND_RE = re.compile(r'title="Stand: (\d\d\.\d\d\.\d{4} \d\d:\d\d) Uhr" class="pls-farbcode pls-farbcode-(\w+)"')
COORD_RE = re.compile(r"map=\d+,([\d.]+),([\d.]+),EPSG:4326")
ADDRESS_RE = re.compile(r"^\s*<div><p>\s*Zufahrt(?:en)?\s+(.*?)</p>", re.S)
OPEN_COLOURS = {"gruen", "gelb", "rot"}


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _place_id(name: str) -> str:
    slug = archive_slug(name)
    return f"sw-bielefeld-parken-{LEGACY_SLUGS.get(slug, slug)}"


class BielefeldLiveAdapter(SourceAdapter):
    name = "sw-bielefeld-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _sites(self, fetcher) -> list[tuple[str, str]]:
        return [(_text(title), body) for title, body in BLOCK_RE.findall(fetcher.get_text(PAGE_URL))]

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for name, body in self._sites(fetcher):
            status = STATUS_RE.search(body)
            capacity = CAPACITY_RE.search(status.group(1)) if status else None
            if not name or not capacity or not int(capacity.group(1)):
                continue
            coords, address = COORD_RE.search(body), ADDRESS_RE.search(body)
            records.append(
                CapacityRecord(
                    place_id=_place_id(name),
                    place_name=name,
                    city_name="Bielefeld",
                    num_all=int(capacity.group(1)),
                    source_id=self.name,
                    address=_text(address.group(1)) or None if address else None,
                    latitude=float(coords.group(2)) if coords else None,
                    longitude=float(coords.group(1)) if coords else None,
                    source_web_url=PAGE_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for name, body in self._sites(fetcher):
            status = STATUS_RE.search(body)
            if not name or not status:
                continue
            stand, capacity, free = STAND_RE.search(status.group(1)), CAPACITY_RE.search(status.group(1)), FREE_RE.search(status.group(1))
            if not (stand and capacity and free) or stand.group(2) not in OPEN_COLOURS:
                continue
            if not 0 <= int(free.group(1)) <= int(capacity.group(1)):
                continue
            ts = datetime.strptime(stand.group(1), "%d.%m.%Y %H:%M").replace(tzinfo=BERLIN).astimezone(timezone.utc)
            records.append(
                OccupancyRecord(place_id=_place_id(name), ts=ts.isoformat(timespec="seconds"), free=int(free.group(1)))
            )
        return records
