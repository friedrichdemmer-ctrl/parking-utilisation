"""Q-Park's Rouen garage, via Métropole Rouen Normandie's static parking
register (data.gouv.fr).

Capacity-only, same pattern as db_bahnpark.py/copenhagen_qpark.py/
lyon_qpark.py -- no live occupancy field exists in this CSV at all, just
location/capacity/operator for the 9 garages the metropole manages. Only
the one row whose "delegatair" (delegated operator) field is "Q-PARK
Services" is trusted as Q-Park's; the other 8 are Effia, Indigo, or
"Rouen Normandie Stationnement" (the metropole's own operator).
"""

from __future__ import annotations

import csv
import io
import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

CSV_URL = "https://static.data.gouv.fr/resources/parkings-en-ouvrage-metropole-rouen-normandie/20240906-142156/parking-metropolerouennormandie-20240904.csv"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[éèê]", "e", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class RouenQParkAdapter(SourceAdapter):
    name = "rouen-qpark"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        text = fetcher.get_text(CSV_URL)
        reader = csv.DictReader(io.StringIO(text), delimiter=";")
        records = []
        for row in reader:
            if "Q-PARK" not in (row.get("delegatair") or "").upper():
                continue
            name = (row.get("nom") or "").strip()
            capacity = row.get("nb_places")
            if not name or not capacity:
                continue
            try:
                lat = float(row["Ylat"])
                lon = float(row["Xlong"])
            except (KeyError, ValueError):
                lat = lon = None
            records.append(
                CapacityRecord(
                    place_id=f"rouen-qpark-{_slug(row.get('id') or name)}",
                    place_name=name,
                    city_name="Rouen",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=row.get("adresse"),
                    latitude=lat,
                    longitude=lon,
                    place_url=row.get("url"),
                    source_web_url="https://www.data.gouv.fr/datasets/parkings-en-ouvrage-metropole-rouen-normandie",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
