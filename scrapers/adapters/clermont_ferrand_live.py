"""Live parking occupancy for Clermont Auvergne Métropole, via its
Opendatasoft portal (opendata.clermontmetropole.eu), dataset
"occupation_parcs_stationnement_metropolitains".

Source: https://opendata.clermontmetropole.eu/explore/dataset/occupation_parcs_stationnement_metropolitains/
API:    https://opendata.clermontmetropole.eu/api/explore/v2.1/catalog/datasets/occupation_parcs_stationnement_metropolitains/records?limit=100
Licence: Licence Ouverte v2.0 (publisher: SAGS, Indigo, Effia).

13 barrier-controlled car parks: the SAGS-run city-centre garages
(Vercingétorix, Saint-Pierre, Gambetta, Fontgiève, Médiathèque, Blaise
Pascal, 1er Mai, Cathédrale) plus T2C park-and-ride (Les Pistes, Henri
Dunant). Gambetta and Blaise Pascal each appear twice (surface /
underground) as separate rows with their own capacity. Updated about
every minute.

Timestamps: per-row "horodatage" is genuine UTC ("+00:00", a minute or two
behind fetch time when checked), converted as-is.

Skipped: rows whose "etat" is not "Valide" -- both Henri Dunant P+R rows
are "Invalide" with null counts and a timestamp frozen at 2025-04-06 --
and rows with no count or capacity <= 0.

Place ids use the dataset's own numeric "identifiant", not the
Opendatasoft recordid, which is not stable.
"""

from __future__ import annotations

from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = (
    "https://opendata.clermontmetropole.eu/api/explore/v2.1/catalog/datasets/"
    "occupation_parcs_stationnement_metropolitains/records?limit=100"
)
WEB_URL = "https://opendata.clermontmetropole.eu/explore/dataset/occupation_parcs_stationnement_metropolitains/"


class ClermontFerrandLiveAdapter(SourceAdapter):
    name = "clermont-ferrand-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        data = fetcher.get_json(API_URL)
        for r in data.get("results", []):
            fid = r.get("identifiant")
            name = (r.get("nom") or "").strip()
            if fid is None or not name:
                continue
            if (r.get("etat") or "").strip() != "Valide":
                continue
            total = r.get("capacite_maximale")
            free = r.get("places_libres")
            ts_raw = r.get("horodatage")
            if not total or int(total) <= 0 or free is None or int(free) < 0 or not ts_raw:
                continue
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).astimezone(timezone.utc)
            yield str(fid), name, r, int(total), int(free), ts.isoformat(timespec="seconds")

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for fid, name, r, total, _free, _ts in self._rows(fetcher):
            records.append(
                CapacityRecord(
                    place_id=f"{self.name}-{fid}",
                    place_name=name,
                    city_name="Clermont-Ferrand",
                    num_all=total,
                    source_id=self.name,
                    latitude=r.get("latitude"),
                    longitude=r.get("longitude"),
                    place_url=r.get("lien"),
                    source_web_url=WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return [
            OccupancyRecord(place_id=f"{self.name}-{fid}", ts=ts, free=free)
            for fid, _name, _r, _total, free, ts in self._rows(fetcher)
        ]
