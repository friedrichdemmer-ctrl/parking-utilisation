"""London Borough of Hillingdon's council car parks, via the council's
own public map service (LBH_PublicData, layer "Car Parks").

Capacity-only, no live occupancy field. 32 car parks, 3,480 spaces, in
Uxbridge, Ruislip, Eastcote, Hayes, Northwood and other Hillingdon towns.
Filed under city "London" like the TfL and City of London sources; the
council's own town name goes into the address.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

LAYER_URL = "https://maps.hillingdon.gov.uk/arcgis/rest/services/PublicServices/LBH_PublicData/MapServer/1"
API_URL = LAYER_URL + "/query?where=1%3D1&outFields=*&f=json&outSR=4326"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class HillingdonLiveAdapter(SourceAdapter):
    name = "hillingdon-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for f in data.get("features", []):
            a = f.get("attributes", {})
            name = (a.get("NAME") or "").strip()
            capacity = a.get("SPACES")
            if not name or not capacity:
                continue
            geo = f.get("geometry") or {}
            address = ", ".join(
                v.strip() for v in (a.get("Road"), a.get("Town"), a.get("POSTCODE")) if v and str(v).strip()
            )
            records.append(
                CapacityRecord(
                    place_id=f"hillingdon-live-{_slug(name)}-{a.get('ID')}",
                    place_name=name,
                    city_name="London",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=address or None,
                    latitude=geo.get("y"),
                    longitude=geo.get("x"),
                    source_web_url=LAYER_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
