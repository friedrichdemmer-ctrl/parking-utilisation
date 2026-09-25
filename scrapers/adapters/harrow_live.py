"""London Borough of Harrow's car parks, via the council's public map
service (Transport_and_Streets_2, layer 7 "Car Parks").

Capacity-only, no live occupancy field. The layer has 30 rows; only
public car parks (type "Council" or "Private") with a positive space
count are kept -- 12 sites, about 2,200 spaces, including Peel House
multi-storey, Queen's House and Greenhill Way. Council-housing estate car
parks (type "Housing") are residents' parking and are skipped, as are the
untyped "Civic Centre" rows. Polygon geometry is reduced to the
vertex-average centroid of its first ring, as in waterford_live.py.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

LAYER_URL = "https://mapping.harrow.gov.uk/server/rest/services/Public/Transport_and_Streets_2/FeatureServer/7"
API_URL = LAYER_URL + "/query?where=1%3D1&outFields=*&f=json&outSR=4326"

PUBLIC_TYPES = {"Council", "Private"}


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


class HarrowLiveAdapter(SourceAdapter):
    name = "harrow-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for f in data.get("features", []):
            a = f.get("attributes", {})
            name = (a.get("NAME") or "").strip()
            capacity = a.get("TOTAL_SPACES")
            if not name or a.get("TYPE") not in PUBLIC_TYPES or not capacity or capacity <= 0:
                continue
            lat, lon = _centroid(f.get("geometry"))
            records.append(
                CapacityRecord(
                    place_id=f"harrow-live-{_slug(name)}-{a.get('OBJECTID')}",
                    place_name=name,
                    city_name="London",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=(a.get("ADDRESS") or "").strip() or None,
                    latitude=lat,
                    longitude=lon,
                    source_web_url=LAYER_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
