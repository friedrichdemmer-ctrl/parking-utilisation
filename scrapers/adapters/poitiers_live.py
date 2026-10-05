"""Live parking occupancy for Poitiers, via Grand Poitiers' data-fair portal
(data.grandpoitiers.fr), dataset "mobilites-stationnement-des-parkings-en-
temps-reel" ("Mobilité - Stationnement des parkings en temps réel", also
listed on data.gouv.fr).

Source: https://data.grandpoitiers.fr/datasets/mobilites-stationnement-des-parkings-en-temps-reel
API:    https://data.grandpoitiers.fr/data-fair/api/v1/datasets/mobilites-stationnement-des-parkings-en-temps-reel/lines?size=100
Licence: Licence Ouverte v2.0 (Etalab).

9 city-centre garages (Théâtre, Hôtel de Ville, Blossac-Tison, Notre-Dame,
Gare Toumaï, Gare Effia, Arrêt Minute, Palais de Justice, Cordeliers).
"Places" = free spaces, "Capacite" = total. The whole dataset is
re-ingested by data-fair every 5 minutes (each line's "_updatedAt").

Timestamps: the source's own "Dernière_mise_à_jour_Base" is labelled UTC
("Z") but runs about 6 minutes AHEAD of real time (e.g. 14:14:55Z fetched
at 14:08:43 UTC, consistently) -- a clock skew on the source system, not
a local-time label (that would be +2 h). So the reading's timestamp is the
earlier of that value and data-fair's "_updatedAt" ingest time: normally
the ingest time, but if the source's own value ever goes stale it wins and
the staleness shows through.

Skipped: rows with no count or capacity <= 0. The feed has no status
field; a 0 free count (Palais de Justice at times) is taken at face value.

Place ids use the dataset's own numeric "Id" column -- data-fair's "_id"
is regenerated on every ingest and must not be used.

Note: the same 8 garages (minus Cordeliers) exist in the national BNLS
file as 86194-P-001..008, but neither bnls-* source ingests Poitiers.
"""

from __future__ import annotations

from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = (
    "https://data.grandpoitiers.fr/data-fair/api/v1/datasets/"
    "mobilites-stationnement-des-parkings-en-temps-reel/lines?size=100"
)
WEB_URL = "https://data.grandpoitiers.fr/datasets/mobilites-stationnement-des-parkings-en-temps-reel"


def _parse(ts_raw):
    if not ts_raw:
        return None
    try:
        ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else None


def _latlon(r):
    raw = r.get("infos_parkingsgeo_point") or r.get("_geopoint")
    if not raw:
        return None, None
    try:
        lat, lon = (float(x) for x in str(raw).split(","))
        return lat, lon
    except ValueError:
        return None, None


class PoitiersLiveAdapter(SourceAdapter):
    name = "poitiers-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        now = datetime.now(timezone.utc)
        data = fetcher.get_json(API_URL)
        for r in data.get("results", []):
            fid = r.get("Id")
            name = (r.get("Nom") or "").strip()
            if fid is None or not name:
                continue
            total = r.get("Capacite")
            free = r.get("Places")
            if not total or int(total) <= 0 or free is None or int(free) < 0:
                continue
            candidates = [t for t in (_parse(r.get("Dernière_mise_à_jour_Base")), _parse(r.get("_updatedAt"))) if t]
            ts = min(candidates + [now])
            yield str(fid), name.title(), r, int(total), int(free), ts.astimezone(timezone.utc).isoformat(timespec="seconds")

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for fid, name, r, total, _free, _ts in self._rows(fetcher):
            lat, lon = _latlon(r)
            records.append(
                CapacityRecord(
                    place_id=f"{self.name}-{fid}",
                    place_name=name,
                    city_name="Poitiers",
                    num_all=total,
                    source_id=self.name,
                    latitude=lat,
                    longitude=lon,
                    source_web_url=WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return [
            OccupancyRecord(place_id=f"{self.name}-{fid}", ts=ts, free=free)
            for fid, _name, _r, _total, free, ts in self._rows(fetcher)
        ]
