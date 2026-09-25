"""Assen's car parks, via the municipality's own ArcGIS server
(gis.assen.nl), layer "Parkeervoorzieningen_binnenstad".

Capacity-only -- no live occupancy field exists. Found via the same
country-wide data.europa.eu full-text search used for the rest of this
session's leads; Assen had zero prior coverage in this project. No
operator field exists here at all, so no Q-Park check is possible.
Requests coordinates directly in WGS84 (outSR=4326) since the layer's
native geometry is in the Dutch RD New projection (EPSG:28992), not
lat/lon.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = (
    "https://gis.assen.nl/arcgis/rest/services/verkeer/Parkeervoorzieningen_binnenstad/MapServer/0/query"
    "?where=1%3D1&outFields=*&f=json&outSR=4326&resultRecordCount=50"
)


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class AssenLiveAdapter(SourceAdapter):
    name = "assen-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for f in data.get("features", []):
            a = f.get("attributes", {})
            name = (a.get("NAAM") or "").strip()
            capacity = a.get("CAPACITEIT")
            geo = f.get("geometry") or {}
            if not name or not capacity:
                continue
            records.append(
                CapacityRecord(
                    place_id=f"assen-live-{_slug(name)}-{a.get('OBJECTID')}",
                    place_name=name,
                    city_name="Assen",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=a.get("INGANG"),
                    latitude=geo.get("y"),
                    longitude=geo.get("x"),
                    source_web_url="https://gis.assen.nl/arcgis/rest/services/verkeer/Parkeervoorzieningen_binnenstad/MapServer",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
