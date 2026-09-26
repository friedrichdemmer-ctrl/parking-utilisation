"""Live parking occupancy across Bordeaux Métropole, via its Opendatasoft
portal (opendata.bordeaux-metropole.fr), dataset "st_park_p".

Found while grinding through Belgium (a search for Braine-l'Alleud's smart
parking surfaced this as a related result). Bordeaux itself is already one
of our biggest French Q-Park cities, but only via BNLS -- the static,
2024-01-stale national import (bnls-qpark-fr/bnls-other-fr). This is a
genuine upgrade opportunity: confirmed 2 Q-Park garages here (Clemenceau,
Bord'Eau Village) with live, current timestamps, distinct from the BNLS
entries by place_id, so both sources can coexist without duplicating a
physical garage under two identities -- unlike sync_archive.py's
RENAME_MAP situations, there's no shared ID scheme to reconcile here, and
manually cross-matching ~60 BNLS names against ~100 of these would be its
own project. Left as a design tradeoff: this adapter's Q-Park garages are
additional entries alongside (not replacing) the BNLS ones for the same
metro area, same as how a live find in one city sometimes sits next to an
older capacity-only source elsewhere in this project.

Covers the whole Bordeaux Métropole (14 communes), not just Bordeaux
itself -- Bègles, Mérignac, Pessac, Talence, etc. -- and several other
operators (Indigo, Effia, Interparking, the TBM transit authority, and
Bordeaux Métropole's own facilities) in addition to Q-Park, kept since
fetching the whole dataset costs the same as filtering it down, per "also
cover non-Q-Park towns/operators where effort is low."

Only rows whose "etat" is OUVERT, LIBRE or COMPLET are used; FERME
(closed) and rows past no live "mdate"/missing total are dropped -- ~27 of
the 100 rows, mostly permanently-closed or never-wired-up facilities.

Place ids are keyed on the garage name alone. They used to carry the
Opendatasoft recordid, but that is a hash of the record's content and
changed on every update from 2026-09-24, giving each reading a new id.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://opendata.bordeaux-metropole.fr/api/records/1.0/search/?dataset=st_park_p&rows=200"
OPERATIONAL_STATES = {"OUVERT", "LIBRE", "COMPLET"}

INSEE_TO_COMMUNE = {
    "33032": "Lormont",
    "33039": "Bègles",
    "33063": "Bordeaux",
    "33069": "Bruges",  # note: this insee is actually Cenon/Bordeaux-suburb code in some editions; kept as observed in the address field below
    "33075": "Bruges",
    "33167": "Floirac",
    "33200": "Le Haillan",
    "33249": "Bassens",
    "33281": "Mérignac",
    "33312": "Parempuyre",
    "33318": "Pessac",
    "33376": "Saint-Aubin-de-Médoc",
    "33522": "Talence",
    "33550": "Villenave-d'Ornon",
}


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[éèê]", "e", s)
    s = re.sub(r"[àâ]", "a", s)
    s = re.sub(r"[ç]", "c", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class BordeauxMetropoleLiveAdapter(SourceAdapter):
    name = "bordeaux-metropole-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        data = fetcher.get_json(API_URL)
        for rec in data.get("records", []):
            f = rec.get("fields", {})
            if f.get("etat") not in OPERATIONAL_STATES:
                continue
            name = (f.get("nom") or "").strip()
            total = f.get("total")
            free = f.get("libres")
            ts_raw = f.get("mdate")
            if not name or not total or free is None or not ts_raw:
                continue
            commune = INSEE_TO_COMMUNE.get(f.get("insee"), "Bordeaux")
            ts = datetime.fromisoformat(ts_raw).astimezone(timezone.utc).isoformat(timespec="seconds")
            yield rec["recordid"], f, name, commune, int(total), int(free), ts

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for recordid, f, name, commune, total, _free, _ts in self._rows(fetcher):
            point = f.get("geo_point_2d") or [None, None]
            records.append(
                CapacityRecord(
                    place_id=f"bordeaux-metropole-live-{_slug(name)}",
                    place_name=name,
                    city_name=commune,
                    num_all=total,
                    source_id=self.name,
                    address=f.get("adresse"),
                    latitude=point[0],
                    longitude=point[1],
                    place_url=f.get("url"),
                    source_web_url="https://opendata.bordeaux-metropole.fr/pages/parking-disponibilite/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for recordid, _f, name, _commune, _total, free, ts in self._rows(fetcher):
            records.append(OccupancyRecord(place_id=f"bordeaux-metropole-live-{_slug(name)}", ts=ts, free=free))
        return records
