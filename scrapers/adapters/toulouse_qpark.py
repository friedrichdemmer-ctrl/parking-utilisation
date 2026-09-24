"""Q-Park's Toulouse garage, via Toulouse Métropole's static parking
register (data.toulouse-metropole.fr, dataset "parcs-de-stationnement").

Capacity-only, same pattern as db_bahnpark.py/copenhagen_qpark.py/
lyon_qpark.py/rouen_qpark.py -- no live occupancy field exists in this
register at all, just location/capacity/operator for the 23 garages
Toulouse Métropole manages. Only the one row whose "gestionnaire" field
is exactly "Q Park" is trusted as Q-Park's; the other 22 are INDIGO or
"TM" (the metropole's own operator). Toulouse had zero prior coverage in
this project (not even via the national BNLS import), so this closes a
real gap, small as it is.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://data.toulouse-metropole.fr/api/explore/v2.1/catalog/datasets/parcs-de-stationnement/records?limit=100"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[éèê]", "e", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class ToulouseQParkAdapter(SourceAdapter):
    name = "toulouse-qpark"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for rec in data.get("results", []):
            if (rec.get("gestionnaire") or "").strip() != "Q Park":
                continue
            name = (rec.get("nom") or "").strip()
            capacity = rec.get("nb_places")
            if not name or not capacity:
                continue
            point = rec.get("geo_point_2d") or {}
            records.append(
                CapacityRecord(
                    place_id=f"toulouse-qpark-{_slug(rec.get('id') or name)}",
                    place_name=name,
                    city_name="Toulouse",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=rec.get("adresse"),
                    latitude=point.get("lat"),
                    longitude=point.get("lon"),
                    source_web_url="https://data.toulouse-metropole.fr/explore/dataset/parcs-de-stationnement/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
