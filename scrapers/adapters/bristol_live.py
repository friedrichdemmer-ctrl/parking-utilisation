"""Bristol's car parks (England), via Bristol City Council's "Layer
Library" transport map service.

Capacity-only. The layer has occupancy columns (OCCUPANCY,
OCCUPANCYCURRENT, TREND) but they are zero/null for every row -- the
same never-wired-up state found when Bristol was first checked for live
data -- so they are ignored. 51 car parks, 13 of them multi-storey or
underground, including 7 operated by NCP (National Car Parks) and Cabot
Circus (2,540 spaces). No Q-Park sites. Some operator names are dated
(e.g. "Norwich Union"), but only the name and capacity are used.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

LAYER_URL = "https://maps2.bristol.gov.uk/server2/rest/services/ext/ll_transport/MapServer/5"
API_URL = LAYER_URL + "/query?where=1%3D1&outFields=*&f=json&outSR=4326"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class BristolLiveAdapter(SourceAdapter):
    name = "bristol-live"
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
            records.append(
                CapacityRecord(
                    place_id=f"bristol-live-{_slug(name)}",
                    place_name=name,
                    city_name="Bristol",
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
