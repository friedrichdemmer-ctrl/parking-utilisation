"""Ards and North Down's car parks (Northern Ireland), via the
council's ArcGIS Online layer, discovered through its public "AND Car
Parks" web map (the layer itself isn't listed with a working link in
the harvested data.europa.eu catalog entry, unlike causeway_coast_
glens_live.py and fermanagh_omagh_live.py found the same sweep).

Capacity-only, no live occupancy field. Two rows are exact duplicates
of another row under the same name and capacity (a car park split into
two mapped sections, both carrying the full total) -- deduplicated by
name+town. 14 of the 45 rows have no name field at all, only a street
address; those use the street name instead of dropping them. Polygon
geometry (not a point) is reduced to its vertex-average centroid for
mapping. No operator field, so no Q-Park check is possible.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = (
    "https://services3.arcgis.com/arG2UzeMsqPNJzQ1/arcgis/rest/services/Car_Parks/FeatureServer/0/query"
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


class ArdsNorthDownLiveAdapter(SourceAdapter):
    name = "ards-north-down-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        seen = set()
        records = []
        for f in data.get("features", []):
            a = f.get("attributes", {})
            name = (a.get("CouncilPro") or a.get("StreetName") or "").strip()
            town = (a.get("TOWN") or "").strip()
            capacity = a.get("Spaces")
            if not name or not town or not capacity:
                continue
            key = (name, town, capacity)
            if key in seen:
                continue
            seen.add(key)
            lat, lon = _centroid(f.get("geometry"))
            records.append(
                CapacityRecord(
                    place_id=f"ards-north-down-live-{_slug(town)}-{_slug(name)}-{a.get('OBJECTID')}",
                    place_name=name,
                    city_name=town,
                    num_all=int(capacity),
                    source_id=self.name,
                    latitude=lat,
                    longitude=lon,
                    source_web_url="https://www.arcgis.com/home/item.html?id=5faa5a500b174710a0e6817dd6c92591",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
