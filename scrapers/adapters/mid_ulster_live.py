"""Mid Ulster's off-street car parks (Northern Ireland), via the
council's ArcGIS Online layer "MUDC_Off_CarParks".

Capacity-only -- "Charged_sp" (metered) and "Free_space" (unmetered) are
both static space counts, no live occupancy or timestamp anywhere. Found
while double-checking whether the UK sweep had actually opened every
lead surfaced by the data.europa.eu searches rather than dismissing
council names by title alone; this and Belfast Council's car park CSVs
(both direct links now 404) kept surfacing without ever being fetched.
19 small-town car parks across Cookstown, Magherafelt, Dungannon,
Fivemiletown, Clogher, Maghera and Castledawson -- closes a real gap,
since the UK otherwise has zero coverage in this project. No operator
field exists, so no Q-Park check is possible.

The service's attribute-level X/Y fields are Irish Grid (EPSG:29900),
not lat/lon -- the request's own "geometry" field (via outSR=4326) is
used instead, the same requested-SRS approach as assen_live.py.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = (
    "https://services1.arcgis.com/IBPnlgK2X1Ngocds/arcgis/rest/services/MUDC_Off_CarParks/FeatureServer/0/query"
    "?where=1%3D1&outFields=*&f=json&outSR=4326&resultRecordCount=50"
)


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class MidUlsterLiveAdapter(SourceAdapter):
    name = "mid-ulster-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for f in data.get("features", []):
            a = f.get("attributes", {})
            name = (a.get("NAME") or "").strip()
            town = (a.get("TOWN") or "").strip()
            try:
                capacity = int(a.get("Charged_sp") or 0) + int(a.get("Free_space") or 0)
            except (TypeError, ValueError):
                capacity = 0
            if not name or not town or capacity <= 0:
                continue
            geo = f.get("geometry") or {}
            records.append(
                CapacityRecord(
                    place_id=f"mid-ulster-live-{_slug(town)}-{_slug(name)}-{a.get('OBJECTID')}",
                    place_name=name,
                    city_name=town,
                    num_all=capacity,
                    source_id=self.name,
                    latitude=geo.get("y"),
                    longitude=geo.get("x"),
                    source_web_url="https://data-midulster.opendata.arcgis.com/datasets/8ff590ded2c9474791b27c9fc3b82d02_0",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
