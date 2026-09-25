"""Dundee City Council's car parks (Scotland), via the council's ArcGIS
Online layer "Dundee City Council Car Park".

Capacity-only, no live occupancy field. 43 car parks, 3,639 spaces. Found
through ArcGIS Online search, the same discovery route as the Northern
Irish and Irish council adapters. The layer has an owner field, but every
row is the council itself, so no Q-Park check is possible.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

LAYER_URL = "https://services.arcgis.com/GlZ1P6ksdiXNYhvC/arcgis/rest/services/Dundee_City_Council_Car_Park/FeatureServer/0"
API_URL = LAYER_URL + "/query?where=1%3D1&outFields=*&f=json&outSR=4326"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class DundeeLiveAdapter(SourceAdapter):
    name = "dundee-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for f in data.get("features", []):
            a = f.get("attributes", {})
            name = (a.get("Name") or "").strip()
            capacity = str(a.get("Spaces") or "").strip()
            if not name or not capacity.isdigit():
                continue
            geo = f.get("geometry") or {}
            records.append(
                CapacityRecord(
                    place_id=f"dundee-live-{_slug(name)}",
                    place_name=name,
                    city_name="Dundee",
                    num_all=int(capacity),
                    source_id=self.name,
                    latitude=geo.get("y"),
                    longitude=geo.get("x"),
                    source_web_url=LAYER_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
