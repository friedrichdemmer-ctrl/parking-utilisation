"""Live parking for Basel (Switzerland), via the canton's open-data portal
(data.bs.ch dataset 100088, "Aktuelle Belegung der öffentlichen
Parkhäuser Basel", CC BY 4.0), sourced from Parkleitsystem Basel and
updated every minute.

16 public garages with capacity, free spaces, coordinates and a UTC
timestamp. place_ids use the feed's own stable slug ("id2", e.g. "city").
Readings for garages not marked "offen" are skipped, since a closed
garage reports 0 free, which would look full. "Parkhaus Post Basel" has
no total in the feed and is skipped entirely. The first Swiss source in
this project.
"""

from __future__ import annotations

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://data.bs.ch/api/v2/catalog/datasets/100088/exports/json"
SOURCE_WEB_URL = "https://data.bs.ch/explore/dataset/100088/"


class BaselLiveAdapter(SourceAdapter):
    name = "basel-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for r in fetcher.get_json(API_URL):
            slug, name, total = r.get("id2"), (r.get("title") or "").strip(), r.get("total")
            if not slug or not name or not total:
                continue
            point = r.get("geo_point_2d") or {}
            records.append(
                CapacityRecord(
                    place_id=f"basel-live-{slug}",
                    place_name=name,
                    city_name="Basel",
                    num_all=int(total),
                    source_id=self.name,
                    address=r.get("address") or None,
                    latitude=point.get("lat"),
                    longitude=point.get("lon"),
                    place_url=r.get("link") or None,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for r in fetcher.get_json(API_URL):
            slug, free, ts = r.get("id2"), r.get("free"), r.get("published")
            if not slug or free is None or not ts or not r.get("total") or r.get("status") != "offen":
                continue
            records.append(OccupancyRecord(place_id=f"basel-live-{slug}", ts=ts, free=int(free)))
        return records
