"""Live parking occupancy for La Rochelle, via its own Drupal-based open
data portal (opendata.agglo-larochelle.fr), a CSV refreshed roughly every
minute per its own "date_comptage" column.

The server serves this CSV comma-delimited to this project's plain
urllib request, but semicolon-delimited to a bare `curl` with no custom
headers -- a locale-dependent Drupal CSV export quirk. Delimiter is
comma here since that's what this project's HttpFetcher actually gets.

Found via a direct data.gouv.fr full-text search for "parking temps réel"
across all organizations -- La Rochelle's own org listing (55 datasets)
didn't surface this under a title match, since its metadata title doesn't
contain "parking". Zero prior coverage of La Rochelle existed in this
project before this adapter. Not Q-Park; no operator field exists in this
CSV at all, and none of the 11 garage names suggest it.

One row in the source has no id/nom/nb_places at all (only a stray
nb_places_disponibles value) -- dropped as clearly malformed.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

CSV_URL = "https://opendata.agglo-larochelle.fr/sites/default/files/dataset/5ab/f904f-38c3-4fae-b510-49ce1a60f7bd/od_parking_dispo.csv"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[éèê]", "e", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class LaRochelleLiveAdapter(SourceAdapter):
    name = "la-rochelle-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        text = fetcher.get_text(CSV_URL)
        reader = csv.DictReader(io.StringIO(text), delimiter=",")
        for row in reader:
            row_id = (row.get("id") or "").strip()
            name = (row.get("nom") or "").strip()
            total = row.get("nb_places")
            free = row.get("nb_places_disponibles")
            ts_raw = row.get("date_comptage")
            if not row_id or not name or not total or not free or not ts_raw:
                continue
            ts = (
                datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S.%f")
                .replace(tzinfo=ZoneInfo("Europe/Paris"))
                .astimezone(timezone.utc)
                .isoformat(timespec="seconds")
            )
            yield row_id, name, int(float(total)), int(float(free)), row.get("ylat"), row.get("xlong"), ts

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for row_id, name, total, _free, lat, lon, _ts in self._rows(fetcher):
            records.append(
                CapacityRecord(
                    place_id=f"la-rochelle-live-{_slug(row_id)}",
                    place_name=name,
                    city_name="La Rochelle",
                    num_all=total,
                    source_id=self.name,
                    latitude=float(lat) if lat else None,
                    longitude=float(lon) if lon else None,
                    source_web_url="https://opendata.agglo-larochelle.fr/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for row_id, _name, _total, free, _lat, _lon, ts in self._rows(fetcher):
            records.append(OccupancyRecord(place_id=f"la-rochelle-live-{_slug(row_id)}", ts=ts, free=free))
        return records
