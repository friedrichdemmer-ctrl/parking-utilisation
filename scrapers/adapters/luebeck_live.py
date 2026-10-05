"""Live parking for Lübeck and Travemünde, scraped from the location list
on parken-luebeck.de, the city's official parking site (operated by KWL).

Lübeck used to arrive only via the defgsus community archive under
source_id "parken-luebeck", which scrapes this same list. There is no
machine-readable feed (nothing on Schleswig-Holstein's open-data portal),
so this adapter reads the homepage's list -- the "parkmoeglichkeiten.html"
page the archive's source_web_url points to is a 404 since the site's
relaunch, but the homepage carries the same 54-entry list -- and takes
over that source_id.

place_ids: the archive builds them from the whole text of each entry's
"location-list-inner" div (name, type, then the hidden name/type/city
block, e.g. "Leuchtenfeld Parkplatz Leuchtenfeld Parkplatz Travemünde"),
slugified. Those verbose ids were mapped back onto the older numeric
lots_meta ids by sync_archive.RENAME_MAP ("...-MuK-Parkplatz-MuK-
Parkplatz-Lubeck" -> "parken-luebeck-46"); this adapter builds the same
verbose id and applies the same map, so every reading lands where the
archive's would. The site's own data-location-uid is a new numbering
(MuK is 38 there, 46 on file) and is deliberately not used.

Only the 13 entries flagged data-live="1" have a live count; the rest
show "Keine Live-Daten verfügbar" and are skipped. The page has no
capacity this adapter trusts enough to overwrite lots_meta with (its
"/ N" disagrees with on-file figures and is below the archive's observed
free count for Leuchtenfeld and Kanalstraße P2/P3), so this is
occupancy-only, and readings are only kept for garages already on file.
The page has no timestamp, so readings use the fetch time.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from scrapers.base import OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

PAGE_URL = "https://www.parken-luebeck.de/"

ITEM_SPLIT = 'class="location-list--item'
INNER_RE = re.compile(r'<div class="location-list-inner">(.*?)</div>\s*</div>\s*<div class="location--info"', re.S)
LIVE_RE = re.compile(r'data-live="1"')
FREE_RE = re.compile(r'<div class="free-live-spots">\s*(\d+)\s*</div>')


def _legacy_place_id(inner_html: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", inner_html))
    text = text.split("|")[0]
    return f"parken-luebeck-{archive_slug(text)}"


def _rename_map() -> dict[str, str]:
    try:
        from sync_archive import RENAME_MAP  # same lazy import as alerts.py
    except ImportError:
        return {}
    return RENAME_MAP


class LuebeckLiveAdapter(SourceAdapter):
    name = "parken-luebeck"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600  # no capacity written -- see module docstring

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        on_file = set(known_garages.values())
        renames = _rename_map()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        records = []
        for item in fetcher.get_text(PAGE_URL).split(ITEM_SPLIT)[1:]:
            if not LIVE_RE.search(item[:1000]):
                continue
            inner, free = INNER_RE.search(item), FREE_RE.search(item)
            if not (inner and free):
                continue
            legacy = _legacy_place_id(inner.group(1))
            place_id = renames.get(legacy, legacy)
            if place_id in on_file:
                records.append(OccupancyRecord(place_id=place_id, ts=now, free=int(free.group(1))))
        return records
