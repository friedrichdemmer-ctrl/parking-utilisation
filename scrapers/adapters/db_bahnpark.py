"""DB BahnPark's "Parking Information" API -- ~315 parking facilities around
train stations nationwide, including Berlin and München.

NOT YET REGISTERED in scrapers/registry.py. This was built against the
published OpenAPI documentation (developers.deutschebahn.com) before the
account's API subscription had been approved by DB, so several things here
are best-effort and need a real response to confirm before this goes live:

  - Field names in FACILITY_CAPACITY_KEYS / OCCUPANCY_FREE_KEYS /
    OCCUPANCY_TOTAL_KEYS are guesses at common REST naming conventions, not
    confirmed from an actual payload. fetch_capacity()/fetch_occupancy()
    log a warning listing the real keys seen whenever none of the guessed
    names match, specifically so the first live run tells us what to fix
    instead of silently writing nothing or writing garbage.
  - One source (a web search summary, not confirmed firsthand) suggested
    DB's capacity/occupancy data may be a coarse category rather than an
    exact free-space count. If /capacities turns out to return a category
    instead of a number, fetch_occupancy() should be rewritten rather than
    forcing a category into OccupancyRecord.free -- not done here since we
    haven't seen a real response yet.
  - The free tier ("Testzugang") is capped at 1,000 requests/month and 10/
    minute. If GET /parking-facilities/{id}/capacities really is one call
    per facility (not inline on the list response), even a daily check
    across Berlin + München's facilities could threaten that budget --
    occupancy_interval_seconds is deliberately conservative (24h) below,
    but the real number of matched facilities needs checking before this
    is trusted at any cadence.
  - stopPlaceId (train-station-scoped search) is NOT used here. Berlin and
    München each have several stations, and guessing which ones without a
    confirmed ID felt worse than fetching the whole ~315-facility list (one
    call) and filtering by address client-side, the same pattern used by
    every other adapter in this package. Whether GET /parking-facilities
    actually allows a bare call with no stopPlaceId is itself unconfirmed.

Credentials come from the DB API Marketplace ("neue Anwendung erstellen",
then subscribe that application to the "Testzugang" plan on this product --
subscriptions need manual approval from DB before they work). They must be
set as Fly.io secrets (DB_BAHNPARK_CLIENT_ID, DB_BAHNPARK_API_KEY), never
committed to this repo.
"""

from __future__ import annotations

import os
import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_BASE = "https://apis.deutschebahn.com/db-api-marketplace/apis/parking-information/db-bahnpark/v2"

CITY_ADDRESS_PATTERNS = {
    "Berlin": re.compile(r"\bBerlin\b", re.IGNORECASE),
    "München": re.compile(r"\bM(ü|u)nchen\b", re.IGNORECASE),
}

# Guessed field names, in priority order -- see module docstring.
FACILITY_ID_KEYS = ("id", "facilityId", "parkingFacilityId")
FACILITY_NAME_KEYS = ("name", "title", "facilityName")
FACILITY_ADDRESS_KEYS = ("address", "street")
FACILITY_CITY_KEYS = ("city", "town", "location")
FACILITY_CAPACITY_KEYS = ("numberOfParkingSpaces", "totalSpaces", "capacity", "spaces", "parkingSpaces")
OCCUPANCY_FREE_KEYS = ("freeSpaces", "free", "availableSpaces", "available")
OCCUPANCY_TOTAL_KEYS = ("totalSpaces", "capacity", "numberOfParkingSpaces")
OCCUPANCY_TIMESTAMP_KEYS = ("lastUpdate", "timestamp", "updatedAt")


def _slug(name: str) -> str:
    s = name.lower()
    s = s.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


def _first(d: dict, keys: tuple[str, ...]):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _nested_text(value) -> str:
    """Some DB APIs nest address fields as {"street": ..., "city": ...} objects
    rather than flat strings -- flatten defensively so our regex matching
    doesn't miss a city name buried in a sub-object."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(str(v) for v in value.values() if isinstance(v, (str, int, float)))
    return str(value) if value is not None else ""


class DbBahnparkAdapter(SourceAdapter):
    name = "db-bahnpark"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 24 * 3600  # conservative pending a real facility count -- see module docstring

    def _auth_headers(self) -> dict[str, str]:
        client_id = os.environ.get("DB_BAHNPARK_CLIENT_ID")
        api_key = os.environ.get("DB_BAHNPARK_API_KEY")
        if not client_id or not api_key:
            raise RuntimeError("DB_BAHNPARK_CLIENT_ID / DB_BAHNPARK_API_KEY not set")
        return {"DB-Client-Id": client_id, "DB-Api-Key": api_key, "Accept": "application/json"}

    def _list_facilities(self, fetcher) -> list[dict]:
        data = fetcher.get_json(f"{API_BASE}/parking-facilities", headers=self._auth_headers())
        # Defensive: some IBM APIC-fronted APIs wrap lists as {"items": [...]}
        # rather than a bare array -- handle both until we've seen a real one.
        if isinstance(data, dict):
            for key in ("items", "facilities", "results", "content"):
                if isinstance(data.get(key), list):
                    return data[key]
            return []
        return data if isinstance(data, list) else []

    def _matched_facilities(self, fetcher) -> list[tuple[dict, str, str]]:
        """Yields (facility, place_id, city_name) for facilities in Berlin or München."""
        out = []
        for facility in self._list_facilities(fetcher):
            haystack = " ".join(
                _nested_text(_first(facility, keys) or "")
                for keys in (FACILITY_ADDRESS_KEYS, FACILITY_CITY_KEYS, FACILITY_NAME_KEYS)
            )
            for city_name, pattern in CITY_ADDRESS_PATTERNS.items():
                if pattern.search(haystack):
                    fid = _first(facility, FACILITY_ID_KEYS)
                    name = _first(facility, FACILITY_NAME_KEYS) or f"facility-{fid}"
                    if fid is None:
                        continue
                    place_id = f"db-bahnpark-{fid}-{_slug(str(name))}"
                    out.append((facility, place_id, city_name))
                    break
        return out

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        matched = self._matched_facilities(fetcher)
        records = []
        unmatched_keys_logged = False
        for facility, place_id, city_name in matched:
            name = str(_first(facility, FACILITY_NAME_KEYS) or place_id)
            capacity = _first(facility, FACILITY_CAPACITY_KEYS)
            if capacity is None:
                if not unmatched_keys_logged:
                    print(f"[{self.name}] capacity: no known capacity field on facility, keys seen: {sorted(facility.keys())}")
                    unmatched_keys_logged = True
                continue
            address = _nested_text(_first(facility, FACILITY_ADDRESS_KEYS) or "") or None
            records.append(
                CapacityRecord(
                    place_id=place_id,
                    place_name=name,
                    city_name=city_name,
                    num_all=int(capacity) if isinstance(capacity, (int, float)) else None,
                    source_id=self.name,
                    address=address,
                    source_web_url="https://www.dbbahnpark.de/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        matched = self._matched_facilities(fetcher)
        records = []
        unmatched_keys_logged = False
        for facility, place_id, _city_name in matched:
            fid = _first(facility, FACILITY_ID_KEYS)
            try:
                cap_data = fetcher.get_json(
                    f"{API_BASE}/parking-facilities/{fid}/capacities", headers=self._auth_headers()
                )
            except Exception as exc:
                print(f"[{self.name}] occupancy: failed to fetch capacities for {place_id}: {exc}")
                continue
            if isinstance(cap_data, list):
                cap_data = cap_data[0] if cap_data else {}
            if not isinstance(cap_data, dict):
                continue
            free = _first(cap_data, OCCUPANCY_FREE_KEYS)
            ts = _first(cap_data, OCCUPANCY_TIMESTAMP_KEYS)
            if free is None or not isinstance(free, (int, float)):
                if not unmatched_keys_logged:
                    print(f"[{self.name}] occupancy: no numeric free-space field, keys seen: {sorted(cap_data.keys())}")
                    unmatched_keys_logged = True
                continue
            if not ts:
                continue
            records.append(OccupancyRecord(place_id=place_id, ts=str(ts), free=int(free)))
        return records
