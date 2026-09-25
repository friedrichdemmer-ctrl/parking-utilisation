"""Waterford's car parks (Ireland), via the council's ArcGIS Online
layer "Car_Parks_(Open Data)".

Capacity-only, no live occupancy field. 79 car parks across Waterford
City, Dungarvan, Tramore, Lismore, Dunmore East and several smaller
towns in the county. 3 confirmed Q-Park garages in Waterford City
("Clock Tower" x2, "Exchange Street Car Park"), identified by the
"Operator" field -- inconsistently spelled "Q-Park" and "Qpark" in the
source, both matched. A handful of names repeat within the same town
(e.g. four "University Hospital Waterford" car parks) but always with
different capacities, so these are genuinely distinct facilities, not
the kind of exact-duplicate row seen in ards_north_down_live.py --
nothing is deduplicated here. Polygon geometry is reduced to its
vertex-average centroid for mapping, the same approach used there.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = (
    "https://services-eu1.arcgis.com/eivETUtIaP8x2Pdh/arcgis/rest/services/Car_Parks_(Open_Data)/FeatureServer/0/query"
    "?where=1%3D1&outFields=*&f=json&outSR=4326&resultRecordCount=100"
)


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


def _centroid(geometry: dict) -> tuple[float | None, float | None]:
    rings = (geometry or {}).get("rings")
    if not rings or not rings[0]:
        return None, None
    points = rings[0]
    lon = sum(p[0] for p in points) / len(points)
    lat = sum(p[1] for p in points) / len(points)
    return lat, lon


class WaterfordLiveAdapter(SourceAdapter):
    name = "waterford-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for f in data.get("features", []):
            a = f.get("attributes", {})
            name = (a.get("Car_Park") or "").strip()
            town = (a.get("Location") or "").strip()
            capacity = a.get("Capacity")
            if not name or not town or not capacity:
                continue
            lat, lon = _centroid(f.get("geometry"))
            records.append(
                CapacityRecord(
                    place_id=f"waterford-live-{_slug(town)}-{_slug(name)}-{a.get('FID')}",
                    place_name=name,
                    city_name=town,
                    num_all=int(capacity),
                    source_id=self.name,
                    latitude=lat,
                    longitude=lon,
                    source_web_url="https://services-eu1.arcgis.com/eivETUtIaP8x2Pdh/arcgis/rest/services/Car_Parks_(Open_Data)/FeatureServer/0",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
