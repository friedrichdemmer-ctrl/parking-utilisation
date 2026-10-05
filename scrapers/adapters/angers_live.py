"""Live parking occupancy for Angers, from the city's Opendatasoft portal
(data.angers.fr), licence ODbL:

  * "parking-angers" ("Disponibilité dans les Parking à Angers") -- free
    spaces per garage, refreshed every minute; garages run by Alter
    Services (parking-angers.fr). Only two fields: a technical garage key
    "nom" (e.g. "Mail", "Saint Laud 2") and "disponible".
  * "angers_stationnement" -- the static description (capacity, address,
    coordinates) of the same garages, keyed "49007-P-0xx". The portal says
    the two join on id = nom, but they do not (ids vs short names), so the
    mapping is spelled out in GARAGES below, matched via names, addresses
    and parking-angers.fr URLs (e.g. "Republique" -> "Fleur d'Eau Les
    Halles", 18 place de la République; "Berges De Maine" -> "Saint-Serge
    Cinéma", URL .../parking-des-berges-du-maine/).

The live feed has no capacity, so capacity is read from the static dataset.
"Chateau" is in the live feed but has no static row (no capacity) and is
skipped until one appears; the dataset's description also carries a stale
"momentanément indisponible" banner although the data is live.

Timestamps: the live records' v1 "record_timestamp" is shifted two hours
into the PAST (12:09Z at a 14:10Z fetch, advancing minute by minute in
step with real time): the source's UTC wall-clock time is being read as
Europe/Paris local time and converted again. The adapter adds the
Europe/Paris UTC offset back. Should the portal ever fix this, the
corrected time would land in the future; then the raw value is used.
Readings older than STALE_AFTER after correction are skipped, as are
counts outside [0, capacity].

place_ids are f"angers-live-{slug of the live key}" (e.g.
"angers-live-saint-laud-2"), stable across runs; the Opendatasoft recordid
is a content hash and is not used.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

LIVE_URL = "https://data.angers.fr/api/records/1.0/search/?dataset=parking-angers&rows=100"
STATIC_URL = "https://data.angers.fr/api/explore/v2.1/catalog/datasets/angers_stationnement/records?limit=100"
WEB_URL = "https://data.angers.fr/explore/dataset/parking-angers/"
PARIS = ZoneInfo("Europe/Paris")
STALE_AFTER = timedelta(hours=6)

# live "nom" -> static "id" in angers_stationnement
GARAGES = {
    "Mail": "49007-P-010",
    "Marengo": "49007-P-016",
    "Larrey": "49007-P-008",
    "Saint Serge Patinoire": "49007-P-013",
    "Leclerc": "49007-P-015",
    "Mitterrand Rennes": "49007-P-002",
    "Mitterrand Maine": "49007-P-007",
    "Quai": "49007-P-017",
    "Bressigny": "49007-P-009",
    "Saint Laud": "49007-P-011",
    "Haras Public": "49007-P-012",
    "Saint Laud 2": "49007-P-005",
    "Ralliement": "49007-P-006",
    "Republique": "49007-P-003",
    "Moliere": "49007-P-014",
    "Berges De Maine": "49007-P-001",
    "Maternite": "49007-P-018",
    "Confluences": "49007-P-004",
}


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[éèêë]", "e", s)
    s = re.sub(r"[àâ]", "a", s)
    s = re.sub(r"[ôö]", "o", s)
    s = re.sub(r"[ç]", "c", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _corrected_ts(raw: str, now: datetime) -> datetime:
    ts = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    shifted = ts + PARIS.utcoffset(ts.replace(tzinfo=None))
    return shifted if shifted <= now + timedelta(minutes=10) else ts


class AngersLiveAdapter(SourceAdapter):
    name = "angers-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _static(self, fetcher) -> dict[str, dict]:
        data = fetcher.get_json(STATIC_URL)
        return {r.get("id"): r for r in data.get("results", []) if r.get("id")}

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        static = self._static(fetcher)
        records = []
        for key, sid in GARAGES.items():
            row = static.get(sid)
            if not row:
                continue
            total = row.get("nb_places")
            if not isinstance(total, int) or total <= 0:
                continue
            records.append(
                CapacityRecord(
                    place_id=f"{self.name}-{_slug(key)}",
                    place_name=(row.get("nom") or key).strip(),
                    city_name="Angers",
                    num_all=total,
                    source_id=self.name,
                    address=row.get("adresse"),
                    latitude=_float(row.get("ylat")),
                    longitude=_float(row.get("xlong")),
                    place_url=row.get("url"),
                    source_web_url=WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        static = self._static(fetcher)
        now = datetime.now(timezone.utc)
        data = fetcher.get_json(LIVE_URL)
        records = []
        for rec in data.get("records", []):
            f = rec.get("fields", {})
            key = (f.get("nom") or "").strip()
            free = f.get("disponible")
            row = static.get(GARAGES.get(key, ""))
            if not row or not isinstance(free, int):
                continue  # unmapped garage (e.g. "Chateau") -- no capacity known
            total = row.get("nb_places")
            if not isinstance(total, int) or not 0 <= free <= total:
                continue
            try:
                ts = _corrected_ts(rec["record_timestamp"], now)
            except (KeyError, ValueError):
                continue
            if now - ts > STALE_AFTER:
                continue
            records.append(
                OccupancyRecord(place_id=f"{self.name}-{_slug(key)}", ts=ts.isoformat(timespec="seconds"), free=free)
            )
        return records
