"""Live parking occupancy for Tours Métropole, via its Opendatasoft portal
(data.tours-metropole.fr), dataset "etat-des-parkings-en-ouvrage-en-temps-
reel-tours-metropole-val-de-loire".

Not a Q-Park city, found incidentally while chasing a Bordeaux lead --
in scope per "also cover non-Q-Park towns where effort is low." Small
(7 garages across Tours and Joué-lés-Tours) but genuinely live, confirmed
against the feed's own "updated_at" timestamp.

The same portal also publishes an Effia-operated parking dataset
("etat-des-parkings-temps-reel-effia-..."), deliberately not used here --
its own "horodatage" timestamps are stuck at September 2024, over a year
stale despite otherwise plausible-looking free/occupied counts, matching
the "looks live, isn't" pattern found elsewhere in this project (Aarhus,
api.parkendd.de).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://data.tours-metropole.fr/api/records/1.0/search/?dataset=etat-des-parkings-en-ouvrage-en-temps-reel-tours-metropole-val-de-loire&rows=50"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[éèê]", "e", s)
    s = re.sub(r"[àâ]", "a", s)
    s = re.sub(r"[ç]", "c", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class ToursLiveAdapter(SourceAdapter):
    name = "tours-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        data = fetcher.get_json(API_URL)
        for rec in data.get("records", []):
            f = rec.get("fields", {})
            name = (f.get("libelle_parking") or "").strip()
            commune = (f.get("commune") or "Tours").strip()
            total = f.get("capacite")
            free = f.get("free_spots")
            ts_raw = f.get("updated_at")
            if not name or not total or free is None or not ts_raw:
                continue
            lat = f.get("latitude")
            lon = f.get("longitude")
            ts = datetime.fromisoformat(ts_raw).astimezone(timezone.utc).isoformat(timespec="seconds")
            yield rec["recordid"], f, name, commune, int(total), int(free), lat, lon, ts

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for recordid, f, name, commune, total, _free, lat, lon, _ts in self._rows(fetcher):
            records.append(
                CapacityRecord(
                    place_id=f"tours-live-{_slug(name)}-{recordid[:8]}",
                    place_name=name,
                    city_name=commune,
                    num_all=total,
                    source_id=self.name,
                    address=f.get("adresse"),
                    latitude=float(lat) if lat else None,
                    longitude=float(lon) if lon else None,
                    source_web_url="https://data.tours-metropole.fr/pages/parkingtempsreel/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for recordid, _f, name, _commune, _total, free, _lat, _lon, ts in self._rows(fetcher):
            records.append(OccupancyRecord(place_id=f"tours-live-{_slug(name)}-{recordid[:8]}", ts=ts, free=free))
        return records
