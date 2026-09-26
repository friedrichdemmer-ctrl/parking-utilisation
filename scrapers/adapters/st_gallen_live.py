"""Live parking for St. Gallen (Switzerland), via the city's open-data
portal (daten.stadt.sg.ch, "Freie Parkplätze in der Stadt St.Gallen",
sourced from the city's parking-guidance system).

14 sites with capacity, free spaces, status, coordinates and a UTC
timestamp. Sites without a capacity are skipped, and readings are only
kept for sites marked "offen" (one reports "fehler/offline"). The feed
occasionally carries garbage free counts (9,999,597 for Oberer Graben on
2026-09-26); the standard free-vs-capacity validation rejects those.
"""

from __future__ import annotations

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://daten.stadt.sg.ch/api/v2/catalog/datasets/freie-parkplatze-in-der-stadt-stgallen-pls/exports/json"
SOURCE_WEB_URL = "https://daten.stadt.sg.ch/explore/dataset/freie-parkplatze-in-der-stadt-stgallen-pls/"


class StGallenLiveAdapter(SourceAdapter):
    name = "st-gallen-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for r in fetcher.get_json(API_URL):
            site_id, name, capacity = r.get("ph_id"), (r.get("ph_name") or "").strip(), r.get("anzahl_parkplatze")
            if not site_id or not name or not capacity or capacity <= 1:
                continue
            point = r.get("koordinaten") or {}
            records.append(
                CapacityRecord(
                    place_id=f"st-gallen-live-{site_id}",
                    place_name=name,
                    city_name="St. Gallen",
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
            site_id, free, ts = r.get("ph_id"), r.get("frei"), r.get("letzte_aktualisierung")
            if not site_id or free is None or not ts or r.get("ph_status") != "offen" or (r.get("anzahl_parkplatze") or 0) <= 1:
                continue
            records.append(OccupancyRecord(place_id=f"st-gallen-live-{site_id}", ts=ts, free=int(free)))
        return records
