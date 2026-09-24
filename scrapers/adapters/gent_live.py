"""Ghent's (Gent, Belgium) live parking-garage occupancy feed, published
openly via the city's Opendatasoft portal (data.stad.gent).

Found while sweeping Belgium for Q-Park coverage -- Ghent itself isn't a
Q-Park city, but the data is genuinely live (3-minute update interval,
confirmed against the portal's own "last modified" timestamp), fully open
(no registration, unlike the Mobilithek-gated German finds), and cheap to
add, so it's in scope under "also cover non-Q-Park towns where effort is
low." Operator is the city's own Mobiliteitsbedrijf Gent, not Q-Park.

Unusually complete for a first pass: the API already gives both
totalcapacity and availablecapacity directly, plus isopennow/
temporaryclosed flags -- no name-matching or capacity backfill needed.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://data.stad.gent/api/explore/v2.1/catalog/datasets/bezetting-parkeergarages-real-time/records?limit=50"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class GentLiveAdapter(SourceAdapter):
    name = "gent-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        data = fetcher.get_json(API_URL)
        for r in data.get("results", []):
            name = (r.get("name") or "").strip()
            total = r.get("totalcapacity")
            available = r.get("availablecapacity")
            ts_raw = r.get("lastupdate")
            if not name or not total or available is None or not ts_raw:
                continue
            loc = r.get("location") or {}
            ts = datetime.fromisoformat(ts_raw).astimezone(timezone.utc).isoformat(timespec="seconds")
            yield name, int(total), int(available), loc.get("lat"), loc.get("lon"), ts

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for name, total, _avail, lat, lon, _ts in self._rows(fetcher):
            records.append(
                CapacityRecord(
                    place_id=f"gent-live-{_slug(name)}",
                    place_name=name,
                    city_name="Gent",
                    num_all=total,
                    source_id=self.name,
                    latitude=lat,
                    longitude=lon,
                    source_web_url="https://data.stad.gent/explore/dataset/bezetting-parkeergarages-real-time/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for name, _total, available, _lat, _lon, ts in self._rows(fetcher):
            records.append(OccupancyRecord(place_id=f"gent-live-{_slug(name)}", ts=ts, free=available))
        return records
