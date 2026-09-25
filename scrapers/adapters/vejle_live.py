"""Live parking occupancy for Vejle, via the municipality's "LetParkering"
(Easy Parking) API (letparkeringapi.azurewebsites.net).

Found via a country-wide data.europa.eu full-text search for real-time
parking; Denmark had only Copenhagen covered before this (via
copenhagen_qpark.py). Not Q-Park -- no operator field exists at all.

The API also exposes a "ParkingSpotOverview" endpoint with 343 individual
space-level sensor readings, deliberately not used here -- same wrong
shape for this project's per-garage model as the Shop&Drive (Wallonia)
and Marche-en-Famenne per-space sensor feeds skipped elsewhere this
session. "ParkingOverview" is the correct garage-level aggregate: 13
garages with capacity ("antalPladser") and free spaces ("ledigePladser")
already summed.

Neither endpoint returns a timestamp, so this uses the fetch time as the
reading's own timestamp -- the same fallback already used in
koeln_live.py, qpark_nl.py, other_operators_nl.py and
muenchen_parkraumwende.py for live feeds with no embedded timestamp.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://letparkeringapi.azurewebsites.net/api/ParkingOverview"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[æ]", "ae", s)
    s = re.sub(r"[ø]", "oe", s)
    s = re.sub(r"[å]", "aa", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class VejleLiveAdapter(SourceAdapter):
    name = "vejle-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for r in data:
            name = (r.get("parkeringsplads") or "").strip()
            total = r.get("antalPladser")
            if not name or not total:
                continue
            records.append(
                CapacityRecord(
                    place_id=f"vejle-live-{_slug(name)}-{r.get('id')}",
                    place_name=name,
                    city_name="Vejle",
                    num_all=int(total),
                    source_id=self.name,
                    latitude=float(r["latitude"]) if r.get("latitude") else None,
                    longitude=float(r["longitude"]) if r.get("longitude") else None,
                    source_web_url="https://letparkeringapi.azurewebsites.net/index.html",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        records = []
        for r in fetcher.get_json(API_URL):
            name = (r.get("parkeringsplads") or "").strip()
            free = r.get("ledigePladser")
            if not name or free is None:
                continue
            records.append(OccupancyRecord(place_id=f"vejle-live-{_slug(name)}-{r.get('id')}", ts=now, free=free))
        return records
