"""Fermanagh and Omagh's car parks (Northern Ireland), via the
council's own CSV export (fermanaghomagh.com).

Capacity-only, no live occupancy field. Found during the same
systematic Northern Ireland council sweep as
causeway_coast_glens_live.py and ards_north_down_live.py. 39 car parks
across Enniskillen, Omagh, Ballinamallard, Dromore, Fintona,
Irvinestown, Kesh, Lisnaskea, Maguiresbridge, Tempo and Carrickmore. No
operator field, so no Q-Park check is possible.
"""

from __future__ import annotations

import csv
import io
import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

CSV_URL = "http://www.fermanaghomagh.com/app/uploads/2016/12/Open_Data_car_parks.csv"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class FermanaghOmaghLiveAdapter(SourceAdapter):
    name = "fermanagh-omagh-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        text = fetcher.get_text(CSV_URL)
        reader = csv.DictReader(io.StringIO(text))
        records = []
        for i, row in enumerate(reader):
            name = (row.get("Car_Park_Name") or "").strip()
            town = (row.get("Town") or "").strip()
            capacity = row.get("Spaces")
            if not name or not town or not capacity:
                continue
            try:
                lat = float(row["Latitude (y)"])
                lon = float(row["Longitude (x)"])
            except (KeyError, ValueError):
                lat = lon = None
            records.append(
                CapacityRecord(
                    place_id=f"fermanagh-omagh-live-{_slug(town)}-{_slug(name)}-{i}",
                    place_name=name,
                    city_name=town,
                    num_all=int(capacity),
                    source_id=self.name,
                    latitude=lat,
                    longitude=lon,
                    source_web_url="http://www.fermanaghomagh.com/app/uploads/2016/12/Open_Data_car_parks.csv",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
