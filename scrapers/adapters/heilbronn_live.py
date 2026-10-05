"""Live parking for Heilbronn's city-centre garages, scraped from the city's
own occupancy fragment (heilbronn.de, the AJAX block behind
/umwelt-mobilitaet/mobilitaet/parken/parkhaeuser.html).

Heilbronn arrives via the defgsus community archive under source_id
"heilbronn-parken", which scrapes this same fragment; this adapter reads it
directly and keeps writing into the archive's place_ids (its name is that
legacy source_id). No machine-readable feed covers these garages: MobiData
BW has Harmonie, Wollhaus and K3 (bb_parkhaus) and Kiliansplatz (apcoa) as
static records only, and its live heilbronn_goldbeck source has just
Bollwerksturm and the Neckarbogen garage of these (mobidata_bw_cities.py
already carries the Neckarbogen one and leaves Bollwerksturm to this
source).

The fragment lists name and free spaces only, under one "Datum ... Uhrzeit"
stamp in local German time (15:17:00 at a 13:21 UTC fetch), converted to
UTC. Rows without a number (P+R Karlsruher Straße) are skipped. Readings
are kept only for garages already on file, as with apag_live.py: the five
the archive added later (Bildungscampus Mitte, E-Quartiersgarage Neckarbogen,
P+R Karlsruher Straße, Parkhaus Experimenta, Parkplatz Hauptbahnhof) have no
capacity anywhere we can cite and no lots_meta row.

Four of the seven garages on file have no capacity. fetch_capacity fills
those four from the operators' figures in MobiData BW's static records
(read 2026-10-05) and leaves the other three alone.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

PAGE_URL = "https://www.heilbronn.de/allgemeine-inhalte/ajax-parkhausbelegung.html?type=1496993343"
SOURCE_WEB_URL = "https://www.heilbronn.de/umwelt-mobilitaet/mobilitaet/parken/parkhaeuser.html"
BERLIN = ZoneInfo("Europe/Berlin")

STAMP_RE = re.compile(r"Datum:\s*(\d{2}\.\d{2}\.\d{4})\s*-\s*Uhrzeit:\s*(\d{2}:\d{2}:\d{2})")
NAME_RE = re.compile(r'carparkLocation[^>]*>\s*(?:<a [^>]*>)?([^<]*)')
FREE_RE = re.compile(r"Freie Parkplätze:\s*(\d+)")

# place name -> (capacity, MobiData BW source of the figure)
MISSING_CAPACITIES = {
    "Harmonie": (435, "bb_parkhaus: Tiefgarage Harmonie"),
    "Theaterforum K3": (393, "bb_parkhaus: Tiefgarage K3 Theater"),
    "Kiliansplatz": (230, "apcoa: Heilbronn, Klosterhof - Kiliansplatz"),
    "Am Bollwerksturm": (304, "goldbeck: Cityparkhaus am Bollwerksturm"),
}


def _place_id(name: str) -> str:
    return f"heilbronn-parken-{archive_slug(name)}"


class HeilbronnLiveAdapter(SourceAdapter):
    name = "heilbronn-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        return [
            CapacityRecord(
                place_id=_place_id(name),
                place_name=name,
                city_name="Heilbronn",
                num_all=capacity,
                source_id=self.name,
                source_web_url=SOURCE_WEB_URL,
            )
            for name, (capacity, _origin) in MISSING_CAPACITIES.items()
        ]

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        page = fetcher.get_text(PAGE_URL)
        stamp = STAMP_RE.search(page)
        if not stamp:
            return []
        local = datetime.strptime(" ".join(stamp.groups()), "%d.%m.%Y %H:%M:%S").replace(tzinfo=BERLIN)
        ts = local.astimezone(timezone.utc).isoformat(timespec="seconds")
        on_file = set(known_garages.values())
        records = []
        for block in page.split('<div class="carpark">')[1:]:
            name, free = NAME_RE.search(block), FREE_RE.search(block)
            if not (name and free):
                continue
            place_id = _place_id(html.unescape(name.group(1)).strip())
            if place_id in on_file:
                records.append(OccupancyRecord(place_id=place_id, ts=ts, free=int(free.group(1))))
        return records
