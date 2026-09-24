"""Moers's live parking-guidance feed, published as open data (CC BY-NC-SA
4.0) via Open Data Portal Ruhr (opendata.ruhr) -- found by active discovery,
not a catalog keyword match on "parking" (it's filed as a general dataset,
this project's earlier Mobilithek/GovData "parking category" sweeps never
surfaced it).

The feed is a small CSV, Latin-1 encoded (not UTF-8 -- confirmed against a
raw byte dump; "Mühlenstr." etc. would otherwise decode as irrecoverably
mangled replacement characters). Fetched directly with urllib rather than
the shared HttpFetcher, whose get_text() assumes UTF-8.

Several rows are permanently placeholder/inactive: OpeningState "Unbekannt"
with Capacity 0 (never wired up) or "Geschlossen" (temporarily/permanently
shut). Both are filtered the same way -- state must be "Geöffnet" and
capacity > 0 -- rather than trying to distinguish "closed today" from
"closed for good" from this feed alone.
"""

from __future__ import annotations

import csv
import io
import re
import urllib.request
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

FEED_URL = "http://download.moers.de/PLS/plcinfo.csv"
USER_AGENT = "parking-utilisation-scraper/1.0 (research project, low-volume, polite)"


def _slug(name: str) -> str:
    s = name.lower()
    s = s.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class MoersLiveAdapter(SourceAdapter):
    name = "moers-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        req = urllib.request.Request(FEED_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("latin-1")
        reader = csv.DictReader(io.StringIO(text), delimiter=";", quotechar='"')
        for row in reader:
            name = (row.get("Name") or "").strip()
            if not name or row.get("OpeningState") != "Geöffnet":
                continue
            try:
                capacity = int(row["Capacity"])
                occupied = int(row["OccupiedSites"])
                ts_ms = int(row["Timestamp"])
            except (KeyError, ValueError):
                continue
            if capacity <= 0:
                continue
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")
            yield name, capacity, occupied, ts

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for name, capacity, _occupied, _ts in self._rows(fetcher):
            records.append(
                CapacityRecord(
                    place_id=f"moers-live-{_slug(name)}",
                    place_name=name,
                    city_name="Moers",
                    num_all=capacity,
                    source_id=self.name,
                    source_web_url="https://opendata.ruhr/dataset/parkleitsystem-moers",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for name, capacity, occupied, ts in self._rows(fetcher):
            free = capacity - occupied
            records.append(OccupancyRecord(place_id=f"moers-live-{_slug(name)}", ts=ts, free=free))
        return records
