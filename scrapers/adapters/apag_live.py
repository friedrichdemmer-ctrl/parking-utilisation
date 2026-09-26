"""Live parking for APAG (Aachener Parkhaus GmbH) garages in Aachen,
Berlin, Dülmen and Würselen, scraped from the facility list on apag.de.

APAG used to arrive only via the defgsus community archive under
source_id "apag-parken", which has had nothing since 2022-08-10. The
homepage's facility list still shows each garage's free car spaces
("availability-car-parking"; the second number, where present, is free
EV-charging bays), so this adapter reads it and keeps writing into the
archive's place_ids (its name is that legacy source_id).

The list carries no capacity and neither do the facility pages, so
readings are only kept for garages already on file with a capacity from
the archive; new facilities (EBV Carré, the RWTH Uniklinik sites,
Würselen's Rhein-Maas Klinikum) are skipped rather than stored without
one. The page has no timestamp, so readings use the fetch time.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from scrapers.base import OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

PAGE_URL = "https://www.apag.de/"

ITEM_RE = re.compile(
    r'<li\s+data-facility-uuid="[^"]*"\s+data-facility-id="\d+"\s+data-facility-type="ParkingFacility"'
    r'\s+data-capacitytypes="[^"]*"\s+data-city="([^"]*)"(.*?)</li>',
    re.S,
)
TYPE_RE = re.compile(r'class="facility-type">([^<]*)<')
NAME_RE = re.compile(r'class="facility-type">[^<]*</span>\s*<span>([^<]*)</span>')
FREE_RE = re.compile(r'availability-car-parking[^>]*>\s*([^<]*?)\s*<')


class ApagLiveAdapter(SourceAdapter):
    name = "apag-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600  # no capacity source -- see module docstring

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        on_file = set(known_garages.values())
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        records = []
        for city, body in ITEM_RE.findall(fetcher.get_text(PAGE_URL)):
            kind, name, free = TYPE_RE.search(body), NAME_RE.search(body), FREE_RE.search(body)
            if not (kind and name and free and free.group(1).isdigit()):
                continue
            full_name = f"{html.unescape(kind.group(1)).strip()} {html.unescape(name.group(1)).strip()}"
            place_id = f"apag-parken-{archive_slug(html.unescape(city))}-{archive_slug(full_name)}"
            if place_id in on_file:
                records.append(OccupancyRecord(place_id=place_id, ts=now, free=int(free.group(1))))
        return records
