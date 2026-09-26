"""Bottrop's inner-city car parks, via the city's ArcGIS layer
"Parkmöglichkeiten Innenstadt (Punkte)" (listed on Open.NRW).

Capacity-only, no live occupancy field. 18 rows; those without a space
count (e.g. the temporarily closed Hansazentrum garage) are skipped.
"""

from __future__ import annotations

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

LAYER_URL = "https://gis.bottrop.de/arcgis/rest/services/Themenkarten/Parkplaetze/MapServer/4"
API_URL = LAYER_URL + "/query?where=1%3D1&outFields=*&f=json&outSR=4326"


class BottropLiveAdapter(SourceAdapter):
    name = "bottrop-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for f in fetcher.get_json(API_URL).get("features", []):
            a = f.get("attributes", {})
            name, capacity = (a.get("BEZEICHNUN") or "").strip(), str(a.get("ANZAHL_STE") or "").strip()
            if not name or not capacity.isdigit() or int(capacity) <= 0:
                continue
            geo = f.get("geometry") or {}
            records.append(
                CapacityRecord(
                    place_id=f"bottrop-live-{a.get('OBJECTID')}",
                    place_name=name,
                    city_name="Bottrop",
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
