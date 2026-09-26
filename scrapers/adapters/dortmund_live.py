"""Live parking for Dortmund, via the city's open-data portal
(open-data.dortmund.de, dataset "parkhauser", Opendatasoft API).

Dortmund used to arrive only via the defgsus community archive under
source_id "digistadt-dortmund-parken", scraped from a geoweb page that
now answers 503; the archive has had nothing since 2023-12-04. This feed
is the city's own, with capacity, free spaces, coordinates and a UTC
timestamp per garage, so this adapter keeps writing into the archive's
place_ids (its name is that legacy source_id).

24 garages on 2026-09-26. Four renamed ones are mapped back to their
archive names in LEGACY_NAMES. "Alte Post / NH Hotel" (236 spaces) is
deliberately not mapped to the archive's "Alte Post" (89 spaces): the
capacity nearly tripled, so it's treated as a changed facility rather
than rewriting the old record's capacity under its history. Garages with
no timestamp or zero capacity (not currently reporting) are skipped.
"""

from __future__ import annotations

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

API_URL = "https://open-data.dortmund.de/api/v2/catalog/datasets/parkhauser/exports/json"
SOURCE_WEB_URL = "https://open-data.dortmund.de/explore/dataset/parkhauser/"

LEGACY_NAMES = {
    "CineStar": "Cinestar",
    "Dietrich - Keuning - Haus": "Dietr.-Keuning-Haus",
    "Klinikum Dortmund": "Klinikum DO",
}


def _place_id(name: str) -> str:
    return f"digistadt-dortmund-parken-{archive_slug(LEGACY_NAMES.get(name, name))}"


class DortmundLiveAdapter(SourceAdapter):
    name = "digistadt-dortmund-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for r in fetcher.get_json(API_URL):
            name = (r.get("name") or "").strip()
            capacity = r.get("capacity")
            if not name or not capacity:
                continue
            point = r.get("geo_point_2d") or {}
            records.append(
                CapacityRecord(
                    place_id=_place_id(name),
                    place_name=name,
                    city_name="Dortmund",
                    num_all=int(capacity),
                    source_id=self.name,
                    latitude=point.get("lat"),
                    longitude=point.get("lon"),
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for r in fetcher.get_json(API_URL):
            name = (r.get("name") or "").strip()
            free, ts = r.get("frei"), r.get("zeitstempel")
            if not name or free is None or not ts or not r.get("capacity"):
                continue
            records.append(OccupancyRecord(place_id=_place_id(name), ts=ts, free=int(free)))
        return records
