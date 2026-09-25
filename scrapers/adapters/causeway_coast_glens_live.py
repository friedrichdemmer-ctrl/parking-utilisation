"""Causeway Coast and Glens's off-street car parks (Northern Ireland),
via the council's ArcGIS Online layer "CCGBC_Off_Street_Car_Parking".

Capacity-only, no live occupancy field. Found while systematically
checking every Northern Ireland council for the same kind of car-park
layer that mid_ulster_live.py surfaced -- most (Belfast, Antrim and
Newtownabbey, Derry City and Strabane, Mid and East Antrim) turned out
to have no working resource link in the harvested catalog or on their
own portal; this one and ards_north_down_live.py/fermanagh_omagh_live.py
did. 80 car parks across many small towns (Ballycastle, Ballymoney,
Bushmills, Coleraine, Cushendall, Cushendun, Dungiven, Garvagh, Kilrea,
Limavady and others). No operator field, so no Q-Park check is
possible.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = (
    "https://services.arcgis.com/kNPftFdcdm7bfDuO/arcgis/rest/services/CCGBC_Off_Street_Car_Parking/FeatureServer/0/query"
    "?where=1%3D1&outFields=*&f=json&outSR=4326&resultRecordCount=100"
)


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class CausewayCoastGlensLiveAdapter(SourceAdapter):
    name = "causeway-coast-glens-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for f in data.get("features", []):
            a = f.get("attributes", {})
            name = (a.get("Name") or "").strip()
            town = (a.get("Location") or "").strip()
            capacity = a.get("Spaces")
            if not name or not town or not capacity:
                continue
            records.append(
                CapacityRecord(
                    place_id=f"causeway-coast-glens-live-{_slug(town)}-{_slug(name)}-{a.get('ObjectId')}",
                    place_name=name,
                    city_name=town,
                    num_all=int(capacity),
                    source_id=self.name,
                    latitude=a.get("Latitude"),
                    longitude=a.get("Longitude"),
                    source_web_url="https://ccgbcodni-cbcni.opendata.arcgis.com/maps/CBCni::ccgbc-off-street-car-parking",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
