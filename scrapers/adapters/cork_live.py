"""Cork's car parks, via Cork City Council's open data portal
(data.corkcity.ie), dataset "Parking".

Capacity-only -- no live occupancy field or timestamp exists in this
CSV, just name/spaces/hours/price per garage. Found via a country-wide
data.europa.eu full-text search for real-time parking, the same
technique used for France and Belgium; Ireland had zero prior coverage
in this project (an earlier pass this session checked Dublin, Cork and
Galway directly and found nothing open). No operator field exists here
at all, so no Q-Park check is possible.
"""

from __future__ import annotations

import csv
import io
import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

CSV_URL = "https://data.corkcity.ie/dataset/f4ff0fe7-844d-485a-b57e-a6ac2f06dfae/resource/c609d229-f7fe-4da9-a065-1e44f65bc7dc/download/parking_details.csv"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class CorkLiveAdapter(SourceAdapter):
    name = "cork-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        text = fetcher.get_text(CSV_URL)
        reader = csv.DictReader(io.StringIO(text))
        records = []
        for row in reader:
            name = (row.get("name") or "").strip()
            capacity = row.get("spaces")
            if not name or not capacity:
                continue
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except (KeyError, ValueError):
                lat = lon = None
            records.append(
                CapacityRecord(
                    place_id=f"cork-live-{_slug(row.get('identifier') or name)}",
                    place_name=name,
                    city_name="Cork",
                    num_all=int(capacity),
                    source_id=self.name,
                    latitude=lat,
                    longitude=lon,
                    source_web_url="https://data.corkcity.ie/dataset/f4ff0fe7-844d-485a-b57e-a6ac2f06dfae",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
