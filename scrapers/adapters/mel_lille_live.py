"""Live parking occupancy across the Métropole Européenne de Lille (MEL),
via its Geoserver OGC Features API (data.lillemetropole.fr).

Not a Q-Park city -- found while sweeping France for Q-Park coverage, but
genuinely live (confirmed against real-time timestamps) and open, so
included per "also cover non-Q-Park towns where effort is low". Covers
Lille, Roubaix, Tourcoing and Villeneuve-d'Ascq (29 garages total).

The dataset's own catalog page on data.gouv.fr links several endpoint
variants (plain OGC API paths, WFS); most 404 -- only the geoserver
"ogc/features/v1" path actually works, found by trying each one in turn.

Garages report an "etat" (status) field -- only "OUVERT" and "LIBRE" are
treated as operational; "FERME" (closed) and blank/other values show
nbr_libre stuck at 0 or an unclear reading, not a genuine live count.
"COMPLET" (full) is kept since it's still an operational status, just
usually near zero free spaces.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://data.lillemetropole.fr/geoserver/ogc/features/v1/collections/mel_mobilite_et_transport:parking/items?f=json&limit=200"
OPERATIONAL_STATES = {"OUVERT", "LIBRE", "COMPLET"}


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[éèê]", "e", s)
    s = re.sub(r"[àâ]", "a", s)
    s = re.sub(r"[ûü]", "u", s)
    s = re.sub(r"[îï]", "i", s)
    s = re.sub(r"[ç]", "c", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class MelLilleLiveAdapter(SourceAdapter):
    name = "mel-lille-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        data = fetcher.get_json(API_URL)
        for feat in data.get("features", []):
            props = feat.get("properties", {})
            if props.get("etat") not in OPERATIONAL_STATES:
                continue
            name = (props.get("nom") or "").strip()
            city = (props.get("ville") or "").strip().title()
            total = props.get("nbr_total")
            free = props.get("nbr_libre")
            ts_raw = props.get("dtdate")
            if not name or not city or not total or free is None or not ts_raw:
                continue
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(timespec="seconds")
            yield props, name, city, int(total), int(free), ts

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for props, name, city, total, _free, _ts in self._rows(fetcher):
            records.append(
                CapacityRecord(
                    place_id=f"mel-lille-live-{props.get('id')}",
                    place_name=name,
                    city_name=city,
                    num_all=total,
                    source_id=self.name,
                    address=props.get("adresse"),
                    latitude=props.get("latitude"),
                    longitude=props.get("longitude"),
                    source_web_url="https://www.data.gouv.fr/datasets/disponibilite-temps-reel-des-parkings-mel-3",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for props, _name, _city, _total, free, ts in self._rows(fetcher):
            records.append(OccupancyRecord(place_id=f"mel-lille-live-{props.get('id')}", ts=ts, free=free))
        return records
