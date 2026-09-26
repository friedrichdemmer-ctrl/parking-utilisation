"""Geneva's public car parks (Switzerland), via the canton's SITG layer
"Parkings à usage public" (OTC_PARKING, listed on opendata.swiss).

Capacity-only. The layer's 534 rows include many restricted-use car
parks (clinics, schools, residents); only those whose "VOCATION"
mentions public use and that have public spaces are kept -- 313 car
parks, 28,773 spaces. 34 carry a real-time flag, but no open real-time
feed was found. The layer has no commune field, so every site is filed
under city "Genève" (canton-wide, like "London" for the boroughs).
"""

from __future__ import annotations

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

LAYER_URL = "https://vector.sitg.ge.ch/arcgis/rest/services/OTC_PARKING/FeatureServer/0"
API_URL = LAYER_URL + "/query?where=1%3D1&outFields=*&f=json&outSR=4326&resultRecordCount=2000"


class GeneveLiveAdapter(SourceAdapter):
    name = "geneve-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for f in fetcher.get_json(API_URL).get("features", []):
            a = f.get("attributes", {})
            name, capacity = (a.get("NOM") or "").strip(), a.get("NB_PL_PUBLIQUES")
            if not name or not capacity or "public" not in (a.get("VOCATION") or "").lower():
                continue
            geo = f.get("geometry") or {}
            link = (a.get("LIEN_WWW") or "").strip()
            records.append(
                CapacityRecord(
                    place_id=f"geneve-live-{a.get('ID_PARKING')}",
                    place_name=name,
                    city_name="Genève",
                    num_all=int(capacity),
                    source_id=self.name,
                    latitude=geo.get("y"),
                    longitude=geo.get("x"),
                    place_url=link if link.startswith("http") else None,
                    source_web_url=LAYER_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
