"""Live parking for Dresden, scraped from the city's own parking page
(www.dresden.de/freie-parkplaetze, which redirects to
/apps_ext/ParkplatzApp/index; run by the Straßen- und Tiefbauamt).

Dresden arrives via the defgsus community archive under source_id
"dresden-parken", which scrapes this same page; this adapter reads it
directly so the series does not depend on the archive, and keeps writing
into the archive's place_ids (its name is that legacy source_id). No
machine-readable feed was found: the city's OGC API (kommisdd.dresden.de)
has no live car-park layer, the open-data portal has none, and the
"ParkenDD" API for Dresden is a third-party scrape of this page.

The page is one table per district with name, capacity and free spaces, a
colour class per row, and one page-wide "Letzte Aktualisierung" time in
local German time (14:52:35 at a 12:55 UTC fetch), which is converted to
UTC and used for every row. Rows are skipped when marked closed
("park-closed"), when they have no current count (blue, empty "frei"),
and when the page lists their capacity as 0 (Kraftwerk Mitte and
Lindengasse, both "0 / 0", read as out of service).

Renames, matching sync_archive.py's RENAME_MAP: "GALERIA Karstadt Kaufhof"
is the archive's "Karstadt"; "MESSE DRESDEN Parkplatz P7" is taken to be the
archive's "Messe" (same 1200 spaces, same Messe site; that row has never had
a reading on file). Not on the page any more: Bühlau, City Center,
Zinzendorfstraße.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

PAGE_URL = "https://www.dresden.de/apps_ext/ParkplatzApp/index"
SOURCE_WEB_URL = "https://www.dresden.de/freie-parkplaetze"
BERLIN = ZoneInfo("Europe/Berlin")

LEGACY_NAMES = {
    "GALERIA Karstadt Kaufhof": "Karstadt",
    "MESSE DRESDEN Parkplatz P7": "Messe",
}

ROW_RE = re.compile(r'<tr>\s*<td class="(park-[^"]*)".*?</tr>', re.S)
CELL_RE = re.compile(r'<div class="content">(.*?)</div>\s*</td>', re.S)
DETAIL_RE = re.compile(r'href="\./(detail\?id=\d+)"')
UPDATED_RE = re.compile(r"<h3>Letzte Aktualisierung</h3>\s*<div>\s*(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2})\s*</div>")


def _text(cell: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", cell)).strip()


def _place_id(name: str) -> str:
    return f"dresden-parken-{archive_slug(LEGACY_NAMES.get(name, name))}"


def _parse(page: str) -> tuple[str | None, list[dict]]:
    updated = UPDATED_RE.search(page)
    ts = None
    if updated:
        local = datetime.strptime(updated.group(1), "%d.%m.%Y %H:%M:%S").replace(tzinfo=BERLIN)
        ts = local.astimezone(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for m in ROW_RE.finditer(page):
        cells = [_text(c) for c in CELL_RE.findall(m.group(0))]
        if len(cells) < 4 or not cells[1]:
            continue
        detail = DETAIL_RE.search(m.group(0))
        rows.append(
            {
                "name": cells[1],
                "capacity": int(cells[2]) if cells[2].isdigit() else None,
                "free": int(cells[3]) if cells[3].isdigit() else None,
                "closed": "park-closed" in m.group(1),
                "url": f"https://www.dresden.de/apps_ext/ParkplatzApp/{detail.group(1)}" if detail else None,
            }
        )
    return ts, rows


class DresdenLiveAdapter(SourceAdapter):
    name = "dresden-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        _ts, rows = _parse(fetcher.get_text(PAGE_URL))
        return [
            CapacityRecord(
                place_id=_place_id(r["name"]),
                place_name=LEGACY_NAMES.get(r["name"], r["name"]),
                city_name="Dresden",
                num_all=r["capacity"],
                source_id=self.name,
                place_url=r["url"],
                source_web_url=SOURCE_WEB_URL,
            )
            for r in rows
            if r["capacity"]
        ]

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        ts, rows = _parse(fetcher.get_text(PAGE_URL))
        if not ts:
            return []
        return [
            OccupancyRecord(place_id=_place_id(r["name"]), ts=ts, free=r["free"])
            for r in rows
            if r["free"] is not None and r["capacity"] and not r["closed"]
        ]
