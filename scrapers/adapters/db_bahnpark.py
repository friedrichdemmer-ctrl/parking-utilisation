"""DB BahnPark's "Parking Information" API -- parking facilities immediately
around train stations nationwide.

Confirmed against a real (subscription-approved) response, not guessed:
scoped to Berlin and München here, which turned out to have only 9 DB
BahnPark facilities between them (8 Berlin, 1 München) -- this API only
covers station-adjacent facilities, not city-wide coverage, so it's a small
supplement to what's already on file, not a replacement for it. Checked by
name against the existing archive before adding: no overlap found.

Capacity-only, deliberately. The live "occupancy" data at
/parking-facilities/{id}/capacities is a coarse category
(e.g. {"category": "MORE_THAN_FIFTY", "text": "> 50"}), not an exact
free-space count -- our OccupancyRecord schema expects a real number for
utilisation math, and turning a category into a fabricated number would be
worse than not having it. fetch_occupancy() is a no-op, same pattern as
Berlin/Stuttgart's capacity-only adapters.

Credentials come from Fly.io secrets (DB_BAHNPARK_CLIENT_ID,
DB_BAHNPARK_API_KEY) -- never committed to this repo.
"""

from __future__ import annotations

import os
import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_BASE = "https://apis.deutschebahn.com/db-api-marketplace/apis/parking-information/db-bahnpark/v2"

TARGET_CITIES = {"Berlin", "München"}


def _slug(name: str) -> str:
    s = name.lower()
    s = s.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


def _display_name(facility: dict) -> str:
    for entry in facility.get("name") or []:
        if entry.get("context") == "DISPLAY":
            return entry["name"]
    for entry in facility.get("name") or []:
        if entry.get("context") == "NAME":
            return entry["name"]
    return f"facility-{facility.get('id')}"


def _parking_capacity(facility: dict) -> int | None:
    for entry in facility.get("capacity") or []:
        if entry.get("type") == "PARKING" and entry.get("total") not in (None, ""):
            try:
                return int(entry["total"])
            except ValueError:
                return None
    return None


class DbBahnparkAdapter(SourceAdapter):
    name = "db-bahnpark"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def _auth_headers(self) -> dict[str, str]:
        client_id = os.environ.get("DB_BAHNPARK_CLIENT_ID")
        api_key = os.environ.get("DB_BAHNPARK_API_KEY")
        if not client_id or not api_key:
            raise RuntimeError("DB_BAHNPARK_CLIENT_ID / DB_BAHNPARK_API_KEY not set")
        return {"DB-Client-Id": client_id, "DB-Api-Key": api_key, "Accept": "application/json"}

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(f"{API_BASE}/parking-facilities", headers=self._auth_headers())
        records = []
        for facility in data.get("_embedded", []):
            address = facility.get("address") or {}
            city = address.get("city")
            if city not in TARGET_CITIES:
                continue
            capacity = _parking_capacity(facility)
            if not capacity:
                continue
            name = _display_name(facility)
            location = address.get("location") or {}
            records.append(
                CapacityRecord(
                    place_id=f"db-bahnpark-{facility['id']}-{_slug(name)}",
                    place_name=name,
                    city_name=city,
                    num_all=capacity,
                    source_id=self.name,
                    address=address.get("streetAndNumber"),
                    latitude=location.get("latitude"),
                    longitude=location.get("longitude"),
                    place_url=facility.get("url"),
                    source_web_url="https://www.dbbahnpark.de/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
