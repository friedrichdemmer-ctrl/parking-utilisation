"""Interparking's Belgian garages, via transportdata.be (Belgium's national
transport open-data platform), a static APDS JSON extract.

Capacity-only -- no live occupancy field exists in this extract at all,
just name/location/spacesTotal for each garage -- same pattern as the
other single-operator static backfills (db_bahnpark.py, rouen_qpark.py,
saint_etienne_qpark.py). Not Q-Park; Interparking is a separate pan-
European operator. Justified anyway because Belgium had almost no
coverage in this project before this adapter (only Gent, via gent_live.py)
-- found via a country-wide data.europa.eu full-text search rather than
guessing Belgian city names one by one, the same technique that worked
well for France's long tail.

The source has no city/address field at all, only a name and a single
lat/lon point per garage (stored as [lat, lon], not GeoJSON's usual
[lon, lat] -- confirmed by cross-checking known landmarks like "Meir",
Antwerp's main shopping street). City is assigned by nearest-neighbor
distance to a fixed table of Belgian city centers. Four well-known Brussels-region landmarks ("Bordet - Erasme", "Stockel
Square", "Woluwe Shopping Center", "Westland Shopping Center") are
geometrically a little further from Brussels center than the ~5 km cutoff
used for everything else, so they're pinned to Brussels by name rather
than by distance. Three entries ("Ninia", "Centre", "Esplanade") are
20+ km from every city in the table -- too far to guess confidently --
and are dropped rather than mislabeled, the same discipline that kept
Angers' live feed out of this project for being too ambiguous to join
safely.
"""

from __future__ import annotations

import math
import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://transportdata.be/dataset/eb813fc1-1b68-4661-84c0-2f6781b93489/resource/3f5de0f8-ba5d-4469-85a9-db74b2ac6658/download/ipk-car-parks-extract-be-apds-20250828104127.json"

CITIES = {
    "Brussels": (50.8503, 4.3517),
    "Zaventem": (50.8967, 4.4844),
    "Antwerp": (51.2194, 4.4025),
    "Ghent": (51.0500, 3.7303),
    "Bruges": (51.2093, 3.2247),
    "Liege": (50.6326, 5.5797),
    "Namur": (50.4669, 4.8675),
    "Aalst": (50.9377, 4.0356),
    "Knokke-Heist": (51.3500, 3.2833),
}
MAX_DISTANCE_DEGREES = 0.05  # ~5.5 km -- see module docstring for the exceptions on both sides
NAME_OVERRIDES = {
    "Bordet - Erasme": "Brussels",
    "Stockel Square": "Brussels",
    "Woluwe Shopping Center": "Brussels",
    "Westland Shopping Center": "Brussels",
}


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


def _nearest_city(lat: float, lon: float) -> tuple[str, float]:
    best_city, best_dist = None, 1e9
    for city, (clat, clon) in CITIES.items():
        d = math.hypot(lat - clat, lon - clon)
        if d < best_dist:
            best_dist = d
            best_city = city
    return best_city, best_dist


class InterparkingBelgiumAdapter(SourceAdapter):
    name = "interparking-belgium"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for place in data.get("places", []):
            name = (place.get("name") or [{}])[0].get("string", "").strip()
            total = place.get("characteristics", {}).get("spacesTotal")
            coords = place.get("indicativePointLocation", {}).get("coordinates")
            if not name or not total or not coords:
                continue
            lat, lon = coords
            city = NAME_OVERRIDES.get(name)
            if city is None:
                city, dist = _nearest_city(lat, lon)
                if dist > MAX_DISTANCE_DEGREES:
                    continue
            records.append(
                CapacityRecord(
                    place_id=f"interparking-belgium-{_slug(place.get('id') or name)}",
                    place_name=name,
                    city_name=city,
                    num_all=int(total),
                    source_id=self.name,
                    latitude=lat,
                    longitude=lon,
                    source_web_url="https://transportdata.be/dataset/eb813fc1-1b68-4661-84c0-2f6781b93489",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
