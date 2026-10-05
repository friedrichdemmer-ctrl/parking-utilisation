"""Live parking for Frankfurt, Wiesbaden, Kassel and Bad Homburg, scraped
from radio FFH's per-city garage pages
(www.ffh.de/verkehr/parkhaeuser/parkhaus-info-<city>.html).

These cities arrive via the defgsus community archive under source_id
"ffh-parken", which scrapes these same pages; this adapter reads them
directly and keeps writing into the archive's place_ids (its name is that
legacy source_id). FFH is an aggregator, not the cities' own feed, but for
three of the four cities it is the only reachable one:
- Wiesbaden: the city's map (geoportal.wiesbaden.de/parkleitsystem/, framed
  on wiesbaden.de/parken) refused connections from outside Germany on
  2026-10-05, and parken-in-wiesbaden.de failed the TLS handshake. Both may
  work from Fly's fra region; untested. A 2021 council question records the
  city stopping its open parking data.
- Kassel: the city's geoportal parking layer has capacities only.
- Bad Homburg: bad-homburg.de/de/erleben/informieren/parken shows the same
  numbers for 6 of the 9 garages; FFH has all 9 plus capacities.
- Frankfurt: the city's own feed is mainziel.de, already read by
  frankfurt_mainziel.py under its own place_ids; FFH shows the same counts
  (same values on 2026-10-05). It is kept here so the ffh-parken-frankfurt
  history continues -- a duplicate of those garages, as it already was via
  the archive. Drop "Frankfurt" from CITIES to end it.
Mannheim is left out: FFH's Mannheim page showed 0 free for every garage on
2026-10-05, and mannheim_live.py fills the ffh-parken-mannheim place_ids
from the operator's own feed.

Place ids are the archive's: f"ffh-parken-{archive_slug(city.lower() + ' ' + name)}",
then the archive renames that sync_archive.py's RENAME_MAP already maps
(FFH's "PH "/"TG " Wiesbaden names, Kassel "Galeria", Frankfurt "MyZeil /
PalaisQuartier"). Unmatched garages get new rows (Bad Homburg "Parkhaus La
Vie").

Frankfurt, Wiesbaden and Kassel give a per-garage "Stand" in local German
time (15:05 at a 13:08 UTC fetch), converted to UTC; Bad Homburg has none,
so its readings use the fetch time. A Stand more than a day old is skipped
(Wiesbaden's Karstadt and Galeria Kaufhof were stuck at 2026-09-24); a
younger stale one simply repeats its timestamp and write_occupancy drops it.
"belegt" is read as 0 free; "keine Daten", "geschlossen" and other text are
skipped.
"""

from __future__ import annotations

import html
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

BASE_URL = "https://www.ffh.de/verkehr/parkhaeuser/"
BERLIN = ZoneInfo("Europe/Berlin")
MAX_AGE = timedelta(hours=24)

# archive city segment as used in the place_ids -> display city name
CITIES = {
    "frankfurt": "Frankfurt",
    "wiesbaden": "Wiesbaden",
    "kassel": "Kassel",
    "bad-homburg": "Bad Homburg",
}

# raw archive place_id -> the place_id on file (subset of sync_archive.RENAME_MAP)
RENAMES = {
    "ffh-parken-wiesbaden-PH-City-II": "ffh-parken-wiesbaden-City-2",
    "ffh-parken-wiesbaden-PH-Coulinstr": "ffh-parken-wiesbaden-Coulinstrasse",
    "ffh-parken-wiesbaden-PH-Galeria-Kaufhof": "ffh-parken-wiesbaden-Galeria-Kaufhof",
    "ffh-parken-wiesbaden-PH-Karstadt": "ffh-parken-wiesbaden-Karstadt",
    "ffh-parken-wiesbaden-PH-Kurhaus-Casino": "ffh-parken-wiesbaden-Kurhaus-Casino",
    # Liliencarré is matched by size, not by the PH-/TG- prefix that
    # sync_archive.RENAME_MAP follows: FFH's "TG Lili" has 150 spaces like the
    # 150-space row on file (whose 2020-21 readings top out at 150), and
    # "PH Lili" 370 like the 530-space row (readings up to ~480). The prefix
    # mapping had each garage reporting into the other's row since 2025.
    "ffh-parken-wiesbaden-PH-Lili": "ffh-parken-wiesbaden-Tiefgarage-Liliencarre",
    "ffh-parken-wiesbaden-TG-Lili": "ffh-parken-wiesbaden-Parkhaus-Liliencarre",
    "ffh-parken-wiesbaden-TG-RMCC": "ffh-parken-wiesbaden-RMCC",
    "ffh-parken-wiesbaden-PH-Luisenforum": "ffh-parken-wiesbaden-Luisenforum",
    "ffh-parken-wiesbaden-PH-Luisenplatz": "ffh-parken-wiesbaden-Luisenplatz",
    "ffh-parken-wiesbaden-PH-Markt": "ffh-parken-wiesbaden-Markt",
    "ffh-parken-wiesbaden-PH-Mauritius": "ffh-parken-wiesbaden-Mauritius-Galerie",
    "ffh-parken-wiesbaden-PH-Theater": "ffh-parken-wiesbaden-Theater",
    "ffh-parken-frankfurt-MyZeil-PalaisQuartier": "ffh-parken-frankfurt-MyZeil",
    "ffh-parken-kassel-Galeria": "ffh-parken-kassel-Galeria-Kaufhof",
}

ROW_START_RE = re.compile(r'<tr class="[^"]*\bfacility" data-facilityid="([^"]*)" data-lat="([^"]*)" data-lng="([^"]*)"')
NAME_RE = re.compile(r"<a [^>]*>(.*?)</a>", re.S)
CAPACITY_RE = re.compile(r"Plätze(?:\s|&nbsp;)+insgesamt:</td>\s*<td>\s*(\d+)")
STAND_RE = re.compile(r"Stand:</td>\s*<td>\s*(\d{2}\.\d{2}\.\d{4}, \d{2}:\d{2}) Uhr")
FREE_CELL_RE = re.compile(r"</div>\s*</td>\s*<td>(.*?)</td>\s*</tr>", re.S)


def _place_id(city_slug: str, name: str) -> str:
    raw = f"ffh-parken-{archive_slug(f'{city_slug} {name}')}"
    return RENAMES.get(raw, raw)


def _float(s: str) -> float | None:
    try:
        return float(s)
    except ValueError:
        return None


def _rows(page: str) -> list[dict]:
    starts = list(ROW_START_RE.finditer(page))
    rows = []
    for i, m in enumerate(starts):
        chunk = page[m.end(): starts[i + 1].start() if i + 1 < len(starts) else len(page)]
        name, free_cell = NAME_RE.search(chunk), FREE_CELL_RE.search(chunk)
        if not (name and free_cell):
            continue
        capacity, stand = CAPACITY_RE.search(chunk), STAND_RE.search(chunk)
        rows.append(
            {
                "name": html.unescape(re.sub(r"<[^>]+>", "", name.group(1))).strip(),
                "lat": _float(m.group(2)),
                "lon": _float(m.group(3)),
                "capacity": int(capacity.group(1)) if capacity else None,
                "free_text": html.unescape(re.sub(r"<[^>]+>", "", free_cell.group(1))).strip(),
                "stand": stand.group(1) if stand else None,
            }
        )
    return rows


class FfhLiveAdapter(SourceAdapter):
    name = "ffh-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _pages(self, fetcher):
        for n, (city_slug, city_name) in enumerate(CITIES.items()):
            if n:
                time.sleep(1)  # four pages from one host -- space them out a little
            url = f"{BASE_URL}parkhaus-info-{city_slug}.html"
            yield city_slug, city_name, url, _rows(fetcher.get_text(url))

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for city_slug, city_name, url, rows in self._pages(fetcher):
            for r in rows:
                if not r["name"] or not r["capacity"]:
                    continue
                records.append(
                    CapacityRecord(
                        place_id=_place_id(city_slug, r["name"]),
                        place_name=r["name"],
                        city_name=city_name,
                        num_all=r["capacity"],
                        source_id=self.name,
                        latitude=r["lat"] or None,
                        longitude=r["lon"] or None,
                        source_web_url=url,
                    )
                )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        now = datetime.now(timezone.utc)
        records = []
        for city_slug, _city_name, _url, rows in self._pages(fetcher):
            for r in rows:
                text = r["free_text"]
                if text.isdigit():
                    free = int(text)
                elif text.lower() == "belegt":
                    free = 0
                else:
                    continue
                if r["stand"]:
                    local = datetime.strptime(r["stand"], "%d.%m.%Y, %H:%M").replace(tzinfo=BERLIN)
                    ts = local.astimezone(timezone.utc)
                    if now - ts > MAX_AGE:
                        continue
                else:
                    ts = now
                records.append(
                    OccupancyRecord(
                        place_id=_place_id(city_slug, r["name"]),
                        ts=ts.isoformat(timespec="seconds"),
                        free=free,
                    )
                )
        return records
