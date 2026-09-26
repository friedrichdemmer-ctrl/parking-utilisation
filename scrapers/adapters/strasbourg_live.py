"""Live parking occupancy for Strasbourg, via its Opendatasoft portal
(data.strasbourg.eu), dataset "occupation-parkings-temps-reel".

Not a Q-Park city -- found incidentally while chasing a Bordeaux lead
that surfaced this in the same search. Genuinely live (confirmed against
the record's own current timestamp) and open, so included per "also
cover non-Q-Park towns where effort is low."

Only rows whose "etat_descriptif" is "Ouvert" are used; "Fermé" and
"frequentation temps reel indisponible" (no real-time data available)
are dropped -- 8 of the 35 garages in the dataset.

Place ids are keyed on the garage name alone. They used to carry the
Opendatasoft recordid, but that is a hash of the record's content and
changed on every update from 2026-09-24, giving each reading a new id.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://data.strasbourg.eu/api/records/1.0/search/?dataset=occupation-parkings-temps-reel&rows=100"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[éèê]", "e", s)
    s = re.sub(r"[àâ]", "a", s)
    s = re.sub(r"[ôö]", "o", s)
    s = re.sub(r"[ç]", "c", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class StrasbourgLiveAdapter(SourceAdapter):
    name = "strasbourg-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        data = fetcher.get_json(API_URL)
        for rec in data.get("records", []):
            f = rec.get("fields", {})
            if f.get("etat_descriptif") != "Ouvert":
                continue
            name = (f.get("nom_parking") or "").strip()
            total = f.get("total")
            free = f.get("libre")
            ts_raw = rec.get("record_timestamp")
            if not name or not total or free is None or not ts_raw:
                continue
            lat, lon = f.get("position") or [None, None]
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(timespec="seconds")
            yield rec["recordid"], name, int(total), int(free), lat, lon, ts

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for recordid, name, total, _free, lat, lon, _ts in self._rows(fetcher):
            records.append(
                CapacityRecord(
                    place_id=f"strasbourg-live-{_slug(name)}",
                    place_name=name,
                    city_name="Strasbourg",
                    num_all=total,
                    source_id=self.name,
                    latitude=lat,
                    longitude=lon,
                    source_web_url="https://data.strasbourg.eu/explore/dataset/occupation-parkings-temps-reel/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for recordid, name, _total, free, _lat, _lon, ts in self._rows(fetcher):
            records.append(OccupancyRecord(place_id=f"strasbourg-live-{_slug(name)}", ts=ts, free=free))
        return records
