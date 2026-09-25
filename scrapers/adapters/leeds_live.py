"""Leeds City Council's car parks (England), via the council's Local
Government Transparency Code list on Data Mill North.

Capacity-only, no live occupancy (Leeds' live car-park API was
decommissioned by the council). The newest published list is 2020-21.
The CSV has postcodes but no coordinates, so each postcode is geocoded
through postcodes.io; two rows give only a postcode district ("LS28"),
which falls back to the district centroid. Two rows are skipped: "Station
Top" in Otley (spaces given as "50PSV", i.e. bus bays) and "Pudsey Civic"
(no space count). "Town" values that are Leeds neighbourhoods rather than
separate towns are reported as city "Leeds"; Otley, Morley, Pudsey,
Wetherby etc. keep their own town name, as the Northern Irish council
adapters do.
"""

from __future__ import annotations

import csv
import io
import re

from scrapers import uk_postcodes
from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

CSV_URL = (
    "https://datamillnorth.org/download/council-car-parks/"
    "e014240b-70d5-4514-98cf-92aaefaa28b5/Car%2520parks%25202020%2520and%25202021.csv"
)

LEEDS_NEIGHBOURHOODS = {"city centre", "hyde park", "little london", "moortown", "holt park"}


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class LeedsLiveAdapter(SourceAdapter):
    name = "leeds-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        text = fetcher.get_text(CSV_URL)
        geocoded: dict[str, dict | None] = {}
        records = []
        for row in csv.DictReader(io.StringIO(text)):
            name = (row.get("Car Park") or "").strip()
            town = (row.get("Town") or "").strip()
            postcode = " ".join((row.get("Post Code") or "").split())
            capacity = (row.get("Spaces") or "").strip()
            if not name or not town or not capacity.isdigit():
                continue
            if postcode not in geocoded:
                geocoded[postcode] = uk_postcodes.lookup(fetcher, postcode)
            geo = geocoded[postcode] or {}
            city = "Leeds" if town.lower() in LEEDS_NEIGHBOURHOODS else town
            records.append(
                CapacityRecord(
                    place_id=f"leeds-live-{_slug(town)}-{_slug(name)}",
                    place_name=name,
                    city_name=city,
                    num_all=int(capacity),
                    source_id=self.name,
                    address=postcode or None,
                    latitude=geo.get("latitude"),
                    longitude=geo.get("longitude"),
                    source_web_url="https://datamillnorth.org/dataset/council-car-parks",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
