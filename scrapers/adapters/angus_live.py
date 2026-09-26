"""Angus Council's car parks (Scotland), via the council's own public WFS
on xmap.cloud (layer angus_public:car_parks).

Capacity-only, no live occupancy field. 37 car parks, 1,698 spaces, in
Arbroath, Forfar, Brechin, Carnoustie, Kirriemuir, Montrose and smaller
towns. Found via the Spatial Hub "Car Parking - Angus" entry: Spatial
Hub's own Scotland-wide car-park layer drops every attribute except name
and council (no space counts), but this source layer keeps them. Open
access, no key. WFS 1.0.0 is used because it returns lon/lat order for
EPSG:4326.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = (
    "https://angus.maps.xmap.cloud/angus_public/car_parks/wfs?service=WFS&version=1.0.0"
    "&request=GetFeature&typeName=angus_public:car_parks&outputFormat=application/json&srsName=EPSG:4326"
)


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class AngusLiveAdapter(SourceAdapter):
    name = "angus-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for f in data.get("features", []):
            p = f.get("properties", {})
            name = (p.get("carpark") or "").strip()
            town = (p.get("town") or "").strip()
            capacity = p.get("capacity")
            if not name or not town or not capacity:
                continue
            coords = (f.get("geometry") or {}).get("coordinates") or [None, None]
            records.append(
                CapacityRecord(
                    place_id=f"angus-live-{_slug(town)}-{_slug(name)}",
                    place_name=name,
                    city_name=town,
                    num_all=int(capacity),
                    source_id=self.name,
                    latitude=coords[1],
                    longitude=coords[0],
                    source_web_url="https://data.spatialhub.scot/dataset/car_parking-an",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
