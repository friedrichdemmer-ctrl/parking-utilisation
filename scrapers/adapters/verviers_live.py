"""Verviers' car parks, via Wallonia's open data portal (odwb.be),
dataset "parkings-verviers".

Capacity-only ("estim_nobr" is an estimated space count, no live
occupancy field or timestamp exists) -- same pattern as
liege_hors_voirie.py, found via the same odwb.be catalog sweep. Closes
a real gap: Verviers had zero prior coverage in this project. No
operator field exists in this register at all, so no Q-Park check is
possible here.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://www.odwb.be/api/explore/v2.1/catalog/datasets/parkings-verviers/records?limit=50"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[éèê]", "e", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class VerviersLiveAdapter(SourceAdapter):
    name = "verviers-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for r in data.get("results", []):
            name = (r.get("nom") or "").strip()
            capacity = r.get("estim_nobr")
            if not name or not capacity:
                continue
            point = r.get("geo_point_2d") or {}
            records.append(
                CapacityRecord(
                    place_id=f"verviers-live-{_slug(name)}",
                    place_name=name,
                    city_name="Verviers",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=r.get("adresse"),
                    latitude=point.get("lat"),
                    longitude=point.get("lon"),
                    place_url=r.get("lien"),
                    source_web_url="https://www.odwb.be/explore/dataset/parkings-verviers/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
