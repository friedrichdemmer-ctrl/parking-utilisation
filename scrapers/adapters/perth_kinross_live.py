"""Perth and Kinross Council's car parks (Scotland), via the council's
ArcGIS Online layer "Car_Parking_Points".

Capacity-only, no live occupancy field. 69 rows across Perth, Crieff,
Kinross, Pitlochry, Blairgowrie and smaller towns; 7 have a blank or
"UNKNOWN" bay count and are skipped. Two rows are both named "Ferry
Road" in Pitlochry but are genuinely separate car parks (east and west
of the road, 26 vs 60 spaces), so the source's own row id keeps them
apart. Names and towns are all upper case in the source and are
re-cased for display.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

LAYER_URL = "https://services-eu1.arcgis.com/WD0cvOmDKf7CA0Xy/arcgis/rest/services/Car_Parking_Points/FeatureServer/6"
API_URL = LAYER_URL + "/query?where=1%3D1&outFields=*&f=json&outSR=4326"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


def _recase(s: str) -> str:
    return " ".join(w.capitalize() for w in s.split())


class PerthKinrossLiveAdapter(SourceAdapter):
    name = "perth-kinross-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for f in data.get("features", []):
            a = f.get("attributes", {})
            name = _recase(a.get("CAR_PARK_NAME") or "")
            town = _recase(a.get("TOWN") or "")
            capacity = str(a.get("NO_BAYS") or "").strip()
            if not name or not town or not capacity.isdigit():
                continue
            geo = f.get("geometry") or {}
            records.append(
                CapacityRecord(
                    place_id=f"perth-kinross-live-{_slug(town)}-{_slug(name)}-{a.get('MI_PRINX')}",
                    place_name=name,
                    city_name=town,
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
