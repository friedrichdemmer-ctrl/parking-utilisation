"""The City of London Corporation's public car parks, via the "City Car
Parks" layer of its INSPIRE map service.

Capacity-only, no live occupancy field. 5 multi-storey/underground
garages in the Square Mile (Baynard House, Tower Hill, London Wall,
Smithfield, The Minories), 1,594 spaces. The same service's "Car Parks"
layer is the Corporation's Epping Forest laybys, not town-centre
parking, and is deliberately not used. The layer's tariff text shows "?"
where "£" belongs (mangled on the Corporation's server); tariffs aren't
stored, so this doesn't affect anything here.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

LAYER_URL = "https://www.mapping.cityoflondon.gov.uk/arcgis/rest/services/INSPIRE/MapServer/42"
API_URL = LAYER_URL + "/query?where=1%3D1&outFields=*&f=json&outSR=4326"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class CityOfLondonLiveAdapter(SourceAdapter):
    name = "city-of-london-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for f in data.get("features", []):
            a = f.get("attributes", {})
            name = (a.get("CAR_PARKS") or "").strip()
            capacity = a.get("SPACES")
            if not name or not capacity:
                continue
            geo = f.get("geometry") or {}
            records.append(
                CapacityRecord(
                    place_id=f"city-of-london-live-{_slug(name)}",
                    place_name=name,
                    city_name="London",
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
