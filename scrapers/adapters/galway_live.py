"""Galway's car parks, via Galway City Council's ArcGIS Hub open data
portal, dataset "CarParkingOpenData".

Capacity-only -- no live occupancy field or timestamp exists here, just
name/type/space-count per garage. Found via the same country-wide
data.europa.eu search that found cork_live.py. Ireland had zero prior
coverage in this project before these two adapters. No operator field
exists, so no Q-Park check is possible.

3 of the 17 rows have a blank ("space"-only string) NO_SPACES value --
two free surface lots at Salthill and one at Harbour -- dropped rather
than guessed at, leaving 14 garages with a real capacity.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://services-eu1.arcgis.com/Zmea819kt4Uu8kML/arcgis/rest/services/CarParkingOpenData/FeatureServer/0/query?where=1%3D1&outFields=*&f=json&resultRecordCount=100"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class GalwayLiveAdapter(SourceAdapter):
    name = "galway-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for f in data.get("features", []):
            a = f.get("attributes", {})
            name = (a.get("NAME") or "").strip()
            capacity = (a.get("NO_SPACES") or "").strip()
            if not name or not capacity or not capacity.isdigit():
                continue
            records.append(
                CapacityRecord(
                    place_id=f"galway-live-{_slug(name)}-{a.get('OBJECTID')}",
                    place_name=name,
                    city_name="Galway",
                    num_all=int(capacity),
                    source_id=self.name,
                    latitude=a.get("Lat"),
                    longitude=a.get("Long"),
                    source_web_url="https://galway-city-council-opendata-galwaycityco.hub.arcgis.com/datasets/206187e21bcd43a9833df759b8991c2f_0",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
