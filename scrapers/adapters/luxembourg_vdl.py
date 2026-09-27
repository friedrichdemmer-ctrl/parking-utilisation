"""Live parking for Luxembourg City, via the Ville de Luxembourg's open
feed (feed.vdl.lu/circulation/parking/feed.json, listed on data.public.lu
as "Mobilité: emplacements de parking libres"). The first source for
Luxembourg in this project.

One JSON document with ~29 car parks (city centre, Gare, Kirchberg and the
park-and-ride sites): "total" spaces, "actuel" free spaces, and flags for
open ("ouvert"), full ("complet") and sensor fault ("panne"). A faulty
site reports 0 free, which would look full, so its reading is skipped.
Sites with total 0 (no counting) are left out entirely. The document's
last_build_date (RFC 822 with offset) is the reading timestamp.
"""

from __future__ import annotations

from datetime import timezone
from email.utils import parsedate_to_datetime

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://feed.vdl.lu/circulation/parking/feed.json"
SOURCE_WEB_URL = "https://data.public.lu/fr/datasets/mobilite-emplacements-de-parking-libres/"


class LuxembourgVdlAdapter(SourceAdapter):
    name = "luxembourg-vdl"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for p in (fetcher.get_json(API_URL).get("parking") or {}).values():
            total, name = p.get("total"), (p.get("titre") or "").strip()
            if not p.get("id") or not name or not isinstance(total, int) or total <= 0:
                continue
            loc = p.get("localisation") or {}
            entry = (loc.get("entree") or [{}])[0]
            records.append(
                CapacityRecord(
                    place_id=f"luxembourg-vdl-{p['id']}",
                    place_name=name,
                    city_name="Luxembourg",
                    num_all=total,
                    source_id=self.name,
                    address=(entry.get("adresse") or "").strip() or None,
                    latitude=loc.get("latitude"),
                    longitude=loc.get("longitude"),
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        doc = fetcher.get_json(API_URL)
        built = doc.get("last_build_date")
        if not built:
            return []
        ts = parsedate_to_datetime(built).astimezone(timezone.utc).isoformat(timespec="seconds")
        records = []
        for p in (doc.get("parking") or {}).values():
            free = p.get("actuel")
            if not p.get("id") or not isinstance(free, int) or not p.get("total") or p.get("panne") or not p.get("ouvert"):
                continue
            records.append(OccupancyRecord(place_id=f"luxembourg-vdl-{p['id']}", ts=ts, free=free))
        return records
