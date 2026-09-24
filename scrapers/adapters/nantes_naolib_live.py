"""Live parking occupancy for Nantes Métropole, via its Opendatasoft portal
(data.nantesmetropole.fr), two datasets sharing an identical schema:
"244400404_parkings-publics-nantes-disponibilites" (26 public garages) and
"244400404_parcs-relais-nantes-metropole-disponibilites" (21 park-and-ride
sites).

Not a Q-Park city -- both are operated by Naolib, the Nantes Métropole
transit authority. Found while grinding through cheap non-Q-Park French
metros after Tours/Strasbourg. Genuinely live: confirmed against the
records' own "grp_horodatage" timestamp, which matches current time.

Rows with grp_exploitation == 0 (no capacity in operation, e.g. a garage
mid-closure) are dropped -- 1 of 27 in the public-garage dataset, none of
the 21 park-and-ride sites.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

PUBLIC_URL = "https://data.nantesmetropole.fr/api/explore/v2.1/catalog/datasets/244400404_parkings-publics-nantes-disponibilites/records?limit=100"
PARK_RELAIS_URL = "https://data.nantesmetropole.fr/api/explore/v2.1/catalog/datasets/244400404_parcs-relais-nantes-metropole-disponibilites/records?limit=100"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[éèê]", "e", s)
    s = re.sub(r"[àâ]", "a", s)
    s = re.sub(r"[ç]", "c", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class NantesNaolibLiveAdapter(SourceAdapter):
    name = "nantes-naolib-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        for prefix, url in (("public", PUBLIC_URL), ("pr", PARK_RELAIS_URL)):
            data = fetcher.get_json(url)
            for rec in data.get("results", []):
                total = rec.get("grp_exploitation")
                free = rec.get("grp_disponible")
                name = (rec.get("grp_nom") or "").strip()
                ts_raw = rec.get("grp_horodatage")
                if not name or not total or free is None or not ts_raw:
                    continue
                loc = rec.get("location") or {}
                ts = datetime.fromisoformat(ts_raw).astimezone(timezone.utc).isoformat(timespec="seconds")
                place_id = f"nantes-naolib-live-{prefix}-{_slug(name)}-{rec.get('grp_identifiant')}"
                yield rec, place_id, name, int(total), int(free), loc.get("lat"), loc.get("lon"), ts

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for rec, place_id, name, total, _free, lat, lon, _ts in self._rows(fetcher):
            records.append(
                CapacityRecord(
                    place_id=place_id,
                    place_name=name,
                    city_name="Nantes",
                    num_all=total,
                    source_id=self.name,
                    address=rec.get("adresse"),
                    latitude=lat,
                    longitude=lon,
                    source_web_url="https://data.nantesmetropole.fr/explore/dataset/244400404_parkings-publics-nantes-disponibilites/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for _rec, place_id, _name, _total, free, _lat, _lon, ts in self._rows(fetcher):
            records.append(OccupancyRecord(place_id=place_id, ts=ts, free=free))
        return records
