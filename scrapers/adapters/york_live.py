"""City of York Council's car parks (England), via the council's own GIS
server (the layer behind its data.gov.uk "Car Parks" entry).

Capacity-only, no live occupancy field. 13 council car parks, about
2,400 spaces. Polygon geometry is reduced to the vertex-average centroid
of its first ring for mapping, as in waterford_live.py.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

LAYER_URL = "https://maps.york.gov.uk/arcgis/rest/services/Public/LV_TranStreetTravel/MapServer/4"
API_URL = LAYER_URL + "/query?where=1%3D1&outFields=*&f=json&outSR=4326"


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


class YorkLiveAdapter(SourceAdapter):
    name = "york-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for f in data.get("features", []):
            a = f.get("attributes", {})
            name = (a.get("DESCRIPTIO") or "").strip()
            capacity = a.get("CARPARKSPACES")
            if not name or not capacity:
                continue
            lat, lon = _centroid(f.get("geometry"))
            records.append(
                CapacityRecord(
                    place_id=f"york-live-{_slug(name)}",
                    place_name=name,
                    city_name="York",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=(a.get("LV_DETAILS") or "").strip() or None,
                    latitude=lat,
                    longitude=lon,
                    place_url=a.get("WEBSITE2"),
                    source_web_url=LAYER_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
