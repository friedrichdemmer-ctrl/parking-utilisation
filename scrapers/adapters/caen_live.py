"""Live park-and-ride occupancy for Caen la Mer, via the Twisto (Caen
transit network) Opendatasoft portal, dataset "liste-des-pr-et-
disponibilite-en-temps-reel" ("Liste des P+R et disponibilité en temps
réel", also listed on data.gouv.fr).

Source: https://twisto-caen.opendatasoft.com/explore/dataset/liste-des-pr-et-disponibilite-en-temps-reel/
API:    https://twisto-caen.opendatasoft.com/api/explore/v2.1/catalog/datasets/liste-des-pr-et-disponibilite-en-temps-reel/records?limit=100
Licence: stated as "Domaine public" in the dataset metadata.

Only 2 tram P+R are covered (P+R Côte de Nacre in Caen, P+R Jean Vilar in
Ifs) -- no live feed was found for Caen's city-centre garages (Indigo and
others). The portal re-harvests every few minutes.

Timestamps: the rows carry no update time, so fetch time (UTC) is used.

Skipped: rows with no count or capacity <= 0 (none at time of writing).

Place ids use the dataset's own "id" field (319, 320), not the
Opendatasoft recordid, which is not stable.
"""

from __future__ import annotations

from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = (
    "https://twisto-caen.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    "liste-des-pr-et-disponibilite-en-temps-reel/records?limit=100"
)
WEB_URL = "https://twisto-caen.opendatasoft.com/explore/dataset/liste-des-pr-et-disponibilite-en-temps-reel/"


class CaenLiveAdapter(SourceAdapter):
    name = "caen-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        data = fetcher.get_json(API_URL)
        for r in data.get("results", []):
            fid = (str(r.get("id") or "")).strip()
            name = (r.get("nom") or "").strip()
            total = r.get("placestotales")
            free = r.get("placeslibres")
            if not fid or not name or not total or int(total) <= 0 or free is None or int(free) < 0:
                continue
            yield fid, name, r, int(total), int(free)

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for fid, name, r, total, _free in self._rows(fetcher):
            city = (r.get("ville") or "Caen").strip().title()
            records.append(
                CapacityRecord(
                    place_id=f"{self.name}-{fid}",
                    place_name=name,
                    city_name=city,
                    num_all=total,
                    source_id=self.name,
                    address=r.get("adresse"),
                    latitude=r.get("latitude"),
                    longitude=r.get("longitude"),
                    source_web_url=WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return [
            OccupancyRecord(place_id=f"{self.name}-{fid}", ts=ts, free=free)
            for fid, _name, _r, _total, free in self._rows(fetcher)
        ]
