"""Stuttgart garages via MobiData BW's public ParkAPI v3, the
Baden-Württemberg state mobility-data platform (Datenlizenz Deutschland
Namensnennung 2.0, run by NVBW - Nahverkehrsgesellschaft Baden-Württemberg).

This is a state-wide dataset (>30k records, everything down to individual
street bays and bike lockers) -- scoped here to Stuttgart's car-relevant
garage types only, matched on the address's postal-code+city suffix (a plain
substring match on "Stuttgart" false-positives on "Stuttgarter Straße" in
other towns). None of Stuttgart's garage entries carry live occupancy in
this feed -- the handful of realtime=true Stuttgart-named records turned out
to be airport bike lockers, not car garages -- so this is a capacity
backfill, same as Munich, not a live adapter.

Mannheim and Karlsruhe are also in this dataset but deliberately left out:
our archive already carries duplicate historical entries for both cities
from two overlapping legacy sources (most visible in Mannheim, e.g. "C1" vs
"C1 Hauptverwaltung MPB, Parkhaus" for the same garage), and appending a
third source would compound that rather than fix it. Filling their existing
capacity gaps needs a name-matched override, not a new set of rows.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://api.mobidata-bw.de/park-api/api/public/v3/parking-sites?name=Stuttgart&limit=100"
GARAGE_TYPES = {"CAR_PARK", "UNDERGROUND", "OFF_STREET_PARKING_GROUND"}
CITY_ADDRESS_RE = re.compile(r"\d{5}\s+Stuttgart\s*$")


def _slug(name: str) -> str:
    s = name.lower()
    s = s.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class StuttgartMobidataBwAdapter(SourceAdapter):
    name = "mobidata-bw-stuttgart"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # no live data available for Stuttgart's garages; fetch_occupancy is a no-op

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for item in data.get("items", []):
            if item.get("purpose") != "CAR" or item.get("type") not in GARAGE_TYPES:
                continue
            if not CITY_ADDRESS_RE.search(item.get("address") or ""):
                continue
            name = (item.get("name") or "").strip()
            capacity = item.get("capacity")
            if not name or not capacity:
                continue
            records.append(
                CapacityRecord(
                    place_id=f"mobidata-bw-{item['id']}-{_slug(name)}",
                    place_name=name,
                    city_name="Stuttgart",
                    num_all=capacity,
                    source_id=self.name,
                    address=item.get("address"),
                    latitude=item.get("lat"),
                    longitude=item.get("lon"),
                    place_url=item.get("public_url") or None,
                    source_web_url="https://mobidata-bw.de/dataset/gebuendelte-parkdaten-bw",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
