"""Live parking for Ingolstadt, scraped from the city's "Derzeit freie
Parkplätze" page (ingolstadt.de, data from IFG Ingolstadt's parkIN
guidance system).

Ingolstadt used to arrive only via the defgsus community archive under
source_id "ingolstadt-parken", which scrapes this same page. No
machine-readable feed exists (open.bydata lists only Ingolstadt weather
stations; IFG's parkIN site has no live data), so this adapter reads the
page's table and takes over that source_id. place_ids are
f"ingolstadt-parken-{archive_slug(short name)}", the archive's rule.

Occupancy only: each row's title says "N freie Plätze von M", but M is
not the garage's capacity -- it moves over time (Hallenbad showed 571 in
September, 476 today, while IFG lists 852 spaces) and is regularly
*below* the free count the archive records at night. Capacities already
on file (capacity_overrides/archive_gaps_2026-09.csv) are left alone, and
readings are only kept for garages already on file -- which leaves out
"Arena", present on the page and in the archive but not in lots_meta.

Rows with an empty count or an info text such as "geschlossen" (the
Festplatz is closed during the Volksfest) are skipped -- the page shows
them as "0 freie Plätze von 0".

Timestamp: the page header's "Stand: DD.MM.YYYY, HH.MM Uhr" -- local
German time (15.11 shown at 13:11 UTC), converted to UTC.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

BERLIN = ZoneInfo("Europe/Berlin")
PAGE_URL = "https://www.ingolstadt.de/Wirtschaft/parkIN/Derzeit-freie-Parkpl%C3%A4tze"

ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
COUNT_RE = re.compile(r'<td class="parkplatz-anzahl"[^>]*>\s*(\d*)\s*</td>', re.S)
NAME_RE = re.compile(r'<span class="parkplatz-name-kurz">([^<]*)</span>')
INFO_RE = re.compile(r'<span class="parkplatz-infotext"[^>]*>([^<]*)</span>')
STAND_RE = re.compile(r"Stand:\s*(\d{1,2})\.(\d{1,2})\.(\d{4}),\s*(\d{1,2})\.(\d{2})")


class IngolstadtLiveAdapter(SourceAdapter):
    name = "ingolstadt-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600  # no capacity written -- see module docstring

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        page = fetcher.get_bytes(PAGE_URL).decode("iso-8859-1")  # page is Latin-1, not UTF-8
        start = page.find('id="parkplatzauskunft"')
        if start < 0:
            return []
        page = page[start:]
        m = STAND_RE.search(page)
        if m:
            d, mo, y, h, mi = map(int, m.groups())
            ts = datetime(y, mo, d, h, mi, tzinfo=BERLIN).astimezone(timezone.utc)
        else:
            ts = datetime.now(timezone.utc)
        ts_iso = ts.isoformat(timespec="seconds")
        on_file = set(known_garages.values())
        records = []
        for row in ROW_RE.findall(page):
            count, name, info = COUNT_RE.search(row), NAME_RE.search(row), INFO_RE.search(row)
            if not (count and name and count.group(1)) or (info and info.group(1).strip()):
                continue
            place_id = f"{self.name}-{archive_slug(html.unescape(name.group(1)).strip())}"
            if place_id in on_file:
                records.append(OccupancyRecord(place_id=place_id, ts=ts_iso, free=int(count.group(1))))
        return records
