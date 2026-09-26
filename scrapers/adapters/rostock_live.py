"""Rostock's car parks, via the city's open-data portal (opendata-hro.de,
"Parkmöglichkeiten", GeoJSON download from geo.sv.rostock.de).

Capacity-only: the dataset has car, motorhome and bus spaces, operator
and fees for 95 sites (13 multi-storey, 13 underground, 69 surface,
including Warnemünde) but no occupancy. The city's parking-guidance
counts are not published openly. Sites without car spaces (bus- or
motorhome-only) are skipped. Names are "<type> <location>", e.g.
"Parkhaus Östliche Altstadt", since the location field alone is often
just a street or district.
"""

from __future__ import annotations

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://geo.sv.rostock.de/download/opendata/parkmoeglichkeiten/parkmoeglichkeiten.json"
SOURCE_WEB_URL = "https://www.opendata-hro.de/dataset/parkmoeglichkeiten"


class RostockLiveAdapter(SourceAdapter):
    name = "rostock-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for f in fetcher.get_json(API_URL).get("features", []):
            p = f.get("properties", {})
            uuid, capacity = p.get("uuid"), p.get("stellplaetze_pkw")
            location = (p.get("standort") or "").strip()
            if not uuid or not capacity or not location:
                continue
            lon, lat = ((f.get("geometry") or {}).get("coordinates") or [None, None])[:2]
            street = " ".join(str(v) for v in (p.get("strasse_name"), p.get("hausnummer"), p.get("hausnummer_zusatz")) if v)
            records.append(
                CapacityRecord(
                    place_id=f"rostock-live-{uuid}",
                    place_name=f"{(p.get('art') or '').strip()} {location}".strip(),
                    city_name="Rostock",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=street or None,
                    latitude=lat,
                    longitude=lon,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
