"""Luzern's public garages (Switzerland), via the city's open-data layer
"Öffentliche Parkhäuser" (map.stadtluzern.ch OGD/oeffentliches_parkhaus).

Capacity-only, no live occupancy field. 25 rows, 24 with a space count
(about 7,000 spaces), from the Bahnhofparking garages to Allmend/Messe.
"""

from __future__ import annotations

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

LAYER_URL = "https://map.stadtluzern.ch/server/rest/services/OGD/oeffentliches_parkhaus/MapServer/0"
API_URL = LAYER_URL + "/query?where=1%3D1&outFields=*&f=json&outSR=4326"


class LuzernLiveAdapter(SourceAdapter):
    name = "luzern-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for f in fetcher.get_json(API_URL).get("features", []):
            a = f.get("attributes", {})
            name, capacity = (a.get("NAME") or "").strip(), a.get("PP_ZAHL")
            if not name or not capacity:
                continue
            geo = f.get("geometry") or {}
            records.append(
                CapacityRecord(
                    place_id=f"luzern-live-{a.get('OBJECTID')}",
                    place_name=name,
                    city_name="Luzern",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=(a.get("ADRESSE") or "").strip() or None,
                    latitude=geo.get("y"),
                    longitude=geo.get("x"),
                    place_url=a.get("LINK_WEBSEITE") or None,
                    source_web_url=LAYER_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
