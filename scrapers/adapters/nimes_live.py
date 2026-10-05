"""Live parking occupancy for Nîmes, via Nîmes Métropole's Opendatasoft
portal (data.nimes-metropole.fr), dataset "etat-des-parkings-en-temps-reel-
ville-de-nimes" ("Etat des parkings en temps réel - Ville de Nîmes").

Source: https://data.nimes-metropole.fr/explore/dataset/etat-des-parkings-en-temps-reel-ville-de-nimes/
API:    https://data.nimes-metropole.fr/api/explore/v2.1/catalog/datasets/etat-des-parkings-en-temps-reel-ville-de-nimes/records?limit=100
Licence: Licence Ouverte v2.0 (Etalab).

Found in the transport.data.gouv.fr / data.gouv.fr sweep (outside the
batch). 7 garages: 5 Indigo (Arènes, Maison Carrée, Porte Auguste, Jardin
de la Fontaine -- all city centre -- and CHU Carremeau, the hospital) and
2 Q-Park (Gare Feuchères, Jean Jaurès). The portal re-harvests every few
minutes; Indigo rows move every ~5 min, Q-Park rows every ~6 min.

Timestamps -- local-as-UTC trap, corrected: the per-row "updatedat" is
correct UTC for the Q-Park rows (14:13Z fetched at 14:17 UTC) but runs
exactly 2 hours BEHIND for the Indigo rows (12:15Z / 12:21Z fetched at
14:17 / 14:23 UTC, with counts changing in step -- so they are live, not
stale). That is the signature of local Paris time being converted to UTC
twice. For partner == "Indigo" the Paris UTC offset is therefore added
back; if that would put the reading more than 10 min in the future (the
upstream fixed it, or winter time behaves differently) the raw value is
used instead. Check this again after the end of summer time (2026-10-25):
the double-conversion theory predicts a 1-hour shift in winter.

Skipped: rows with a non-empty "status" other than open-like values (the
field was null for every row when written), rows with no count, and
capacity <= 0. "freespots" is a string in the feed; non-numeric values are
skipped.

Place ids use the dataset's own "parkcode", not the Opendatasoft recordid.
Neither Q-Park Nîmes garage is in the national BNLS file (no overlap with
bnls-qpark-fr).
"""

from __future__ import annotations

import ast
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = (
    "https://data.nimes-metropole.fr/api/explore/v2.1/catalog/datasets/"
    "etat-des-parkings-en-temps-reel-ville-de-nimes/records?limit=100"
)
WEB_URL = "https://data.nimes-metropole.fr/explore/dataset/etat-des-parkings-en-temps-reel-ville-de-nimes/"
PARIS = ZoneInfo("Europe/Paris")
OPEN_STATUSES = {"", "open", "ouvert", "opened"}


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _latlon(raw):
    """"coordinate" comes either as a python-dict string "{'lon': x, 'lat': y}"
    (Indigo rows) or as "lat, lon" (Q-Park rows)."""
    if not raw:
        return None, None
    s = str(raw).strip()
    if s.startswith("{"):
        try:
            d = ast.literal_eval(s)
            return float(d["lat"]), float(d["lon"])
        except (ValueError, SyntaxError, KeyError, TypeError):
            return None, None
    parts = re.split(r"[,;]\s*", s)
    if len(parts) == 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            pass
    return None, None


def _ts(raw, partner, now):
    ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if ts.tzinfo is None:
        return None
    ts = ts.astimezone(timezone.utc)
    if partner.lower() == "indigo":
        offset = ts.astimezone(PARIS).utcoffset() or timedelta(0)
        fixed = ts + offset
        if fixed <= now + timedelta(minutes=10):
            ts = fixed
    return ts


class NimesLiveAdapter(SourceAdapter):
    name = "nimes-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        now = datetime.now(timezone.utc)
        data = fetcher.get_json(API_URL)
        for r in data.get("results", []):
            code = (str(r.get("parkcode") or "")).strip()
            name = (r.get("name") or "").strip()
            if not code or not name:
                continue
            if (str(r.get("status") or "")).strip().lower() not in OPEN_STATUSES:
                continue
            total = _int(r.get("totalparkingspaces"))
            free = _int(r.get("freespots"))
            if not total or total <= 0 or free is None or free < 0 or not r.get("updatedat"):
                continue
            ts = _ts(r["updatedat"], (r.get("partner") or ""), now)
            if ts is None:
                continue
            yield code, name, r, total, free, ts.isoformat(timespec="seconds")

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for code, name, r, total, _free, _ts in self._rows(fetcher):
            lat, lon = _latlon(r.get("coordinate"))
            street = (r.get("address_street") or "").strip()
            records.append(
                CapacityRecord(
                    place_id=f"{self.name}-{code}",
                    place_name=name,
                    city_name="Nîmes",
                    num_all=total,
                    source_id=self.name,
                    address=street or None,
                    latitude=lat,
                    longitude=lon,
                    place_url=r.get("urlwebsite"),
                    source_web_url=WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return [
            OccupancyRecord(place_id=f"{self.name}-{code}", ts=ts, free=free)
            for code, _name, _r, _total, free, ts in self._rows(fetcher)
        ]
