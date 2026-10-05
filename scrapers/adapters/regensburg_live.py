"""Live parking for Regensburg, scraped from the parking list on
einkaufen-regensburg.de ("Parken & Anfahrt").

Regensburg used to arrive only via the defgsus community archive under
source_id "regensburg-parken", which scrapes this same page. No better
feed was found: the city has no open-data parking dataset, and
das Stadtwerk.Regensburg's own "Freie Parkplätze" page covers only its
four garages (TechCampus, Theater, Petersweg, Dachauplatz -- same numbers
as here). This page shows a live count for 10 sites, the same 10 the
archive has, so this adapter reads it and takes over that source_id.
place_ids are f"regensburg-parken-{archive_slug(h3 name)}", the archive's
rule.

Occupancy only: the page carries no capacity (on-file capacities come
from capacity_overrides/archive_gaps_2026-09.csv), and readings are only
kept for garages already on file. Sites without a "Freie Parkplätze"
box are skipped. The page has no timestamp (the old "zuletzt
aktualisiert" line is gone), so readings use the fetch time.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from scrapers.base import OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

PAGE_URL = "https://www.einkaufen-regensburg.de/service/parken-amp-anfahrt.html"

BLOCK_SPLIT = '<div class="accordeon parkmoeglichkeit">'
NAME_RE = re.compile(r'<div class="a-info">.*?<h3>(.*?)</h3>', re.S)
FREE_RE = re.compile(r'<div class="belegung">\s*<p>[^<]*<strong>\s*(\d+)\s*</strong>', re.S)


class RegensburgLiveAdapter(SourceAdapter):
    name = "regensburg-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600  # no capacity source -- see module docstring

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        on_file = set(known_garages.values())
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        records = []
        for block in fetcher.get_text(PAGE_URL).split(BLOCK_SPLIT)[1:]:
            name, free = NAME_RE.search(block), FREE_RE.search(block)
            if not (name and free):
                continue
            title = html.unescape(re.sub(r"<[^>]+>", "", name.group(1))).strip()
            place_id = f"{self.name}-{archive_slug(title)}"
            if place_id in on_file:
                records.append(OccupancyRecord(place_id=place_id, ts=now, free=int(free.group(1))))
        return records
