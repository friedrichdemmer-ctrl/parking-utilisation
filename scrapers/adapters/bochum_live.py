"""Live parking for Bochum, scraped from the garage list on
parken-in-bochum.de (run by the city's economic-development company,
WirtschaftsEntwicklungsGesellschaft Bochum), which shows each garage's
free spaces.

Bochum used to arrive only via the defgsus community archive under
source_id "parken-in-bochum", which scrapes this same page; this adapter
takes over that source_id (its name). There is no JSON behind the page
(the free counts are rendered server-side). place_ids are the archive's,
f"parken-in-bochum-{archive_slug(name)}", except for three garages whose
names have changed since the archive first recorded them; LEGACY_SLUGS
maps those back (the same renames sync_archive.py's RENAME_MAP applies).

The list carries no capacity, so fetch_capacity reads each garage's
detail page ("Stellplätze: ca. 2000, davon ..."), once a week. The page
has no timestamp, so readings use the fetch time. Readings are skipped
for garages without a free count (Westpark/Jahrhunderthalle, Alter Markt
Wattenscheid and Quartiersgarage Ostpark have none) and for garages
flagged closed today (the opening-hours span's "data-closed"; e.g. P9
Schauspielhaus on Mondays still shows a stale count).
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from urllib.parse import unquote_plus, urljoin

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

PAGE_URL = "https://www.parken-in-bochum.de/parkhaeuser/"

# archive_slug(current name) -> archive_slug(name on file)
LEGACY_SLUGS = {
    "P8-Konrad-Adenauer-Platz-Bermuda3Eck": "P8-Konrad-Adenauer-Platz",
    "PH-Bochumer-Fenster": "PF-Bochumer-Fenster",
    "PH-Massenbergstrasse": "PM-Massenbergstrasse",
    "PH-Alter-Markt-Wattenscheid": "P1-WAT-Alter-Markt-Wattenscheid",
}

LOT_RE = re.compile(r'<article class="lot"\s+data-lat="([^"]*)"\s+data-lng="([^"]*)"\s+data-uid="\d+">(.*?)</article>', re.S)
NAME_RE = re.compile(r"<h3>\s*(.*?)\s*</h3>", re.S)
HREF_RE = re.compile(r'class="title"[^>]*href="([^"]*)"')
CLOSED_RE = re.compile(r'\sdata-closed="([^"]*)"')
FREE_RE = re.compile(r'<div class="spaces">.*?<strong>(\d+)</strong>', re.S)
CAPACITY_RE = re.compile(r"Stellplätze:?\s*</strong>(?:\s|&nbsp;)*(?:ca\.(?:\s|&nbsp;)*)?(\d[\d.]*)")
ADDRESS_RE = re.compile(r'href="https://www\.google\.de/maps/dir//([^"]+)"')


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _place_id(name: str) -> str:
    slug = archive_slug(name)
    return f"parken-in-bochum-{LEGACY_SLUGS.get(slug, slug)}"


class BochumLiveAdapter(SourceAdapter):
    name = "parken-in-bochum"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _lots(self, fetcher) -> list[tuple[str, str, str, str]]:
        lots = []
        for lat, lng, body in LOT_RE.findall(fetcher.get_text(PAGE_URL)):
            name = NAME_RE.search(body)
            if name and _text(name.group(1)):
                lots.append((_text(name.group(1)), lat, lng, body))
        return lots

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for name, lat, lng, body in self._lots(fetcher):
            href = HREF_RE.search(body)
            if not href:
                continue
            url = urljoin(PAGE_URL, html.unescape(href.group(1)))
            try:
                detail = fetcher.get_text(url)
            except Exception:  # one broken detail page shouldn't drop the rest
                continue
            capacity = CAPACITY_RE.search(detail)
            if not capacity or not int(capacity.group(1).replace(".", "")):
                continue
            address = ADDRESS_RE.search(body)
            address = unquote_plus(html.unescape(address.group(1))).strip() if address else ""
            records.append(
                CapacityRecord(
                    place_id=_place_id(name),
                    place_name=name,
                    city_name="Bochum",
                    num_all=int(capacity.group(1).replace(".", "")),
                    source_id=self.name,
                    address=address if "Bochum" in address else None,  # some links are bare coordinates
                    latitude=float(lat) if lat else None,
                    longitude=float(lng) if lng else None,
                    place_url=url,
                    source_web_url=PAGE_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        records = []
        for name, _lat, _lng, body in self._lots(fetcher):
            free, closed = FREE_RE.search(body), CLOSED_RE.search(body)
            if not free or (closed and closed.group(1).strip()):
                continue
            records.append(OccupancyRecord(place_id=_place_id(name), ts=now, free=int(free.group(1))))
        return records
