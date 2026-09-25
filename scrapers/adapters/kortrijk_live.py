"""Kortrijk's car parks (Belgium), via the city's ArcGIS Online layer
"Parkings", discovered through its public "Overzicht Parkeerplaatsen
Kortrijk" web map.

Capacity-only, no live occupancy field. 23 car parks, no operator
field, so no Q-Park check is possible. Closes a real gap: Kortrijk had
zero prior coverage in this project. Found via the same ArcGIS Online
web-map discovery technique used for the Irish and Northern Irish
councils this session.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = (
    "https://services5.arcgis.com/Qdkl0gOjDA8dsPak/arcgis/rest/services/Parkings/FeatureServer/0/query"
    "?where=1%3D1&outFields=*&f=json&outSR=4326&resultRecordCount=100"
)


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class KortrijkLiveAdapter(SourceAdapter):
    name = "kortrijk-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for f in data.get("features", []):
            a = f.get("attributes", {})
            name = (a.get("Naam") or "").strip()
            capacity = a.get("Capaciteit")
            if not name or not capacity:
                continue
            geo = f.get("geometry") or {}
            records.append(
                CapacityRecord(
                    place_id=f"kortrijk-live-{_slug(name)}-{a.get('id')}",
                    place_name=name,
                    city_name="Kortrijk",
                    num_all=int(capacity),
                    source_id=self.name,
                    latitude=geo.get("y"),
                    longitude=geo.get("x"),
                    place_url=a.get("Meer_info"),
                    source_web_url="https://services5.arcgis.com/Qdkl0gOjDA8dsPak/arcgis/rest/services/Parkings/FeatureServer/0",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
