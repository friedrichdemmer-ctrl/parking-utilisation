"""Live parking occupancy for Orléans Métropole, via its Opendatasoft portal
(data.orleans-metropole.fr), dataset "om-mobilite-parcs-stationnement"
("Parcs de stationnement - Orléans Métropole", also listed on data.gouv.fr).

Source: https://data.orleans-metropole.fr/explore/dataset/om-mobilite-parcs-stationnement/
API:    https://data.orleans-metropole.fr/api/explore/v2.1/catalog/datasets/om-mobilite-parcs-stationnement/records?limit=100
Licence: Licence Ouverte v2.0 (Etalab).

One dataset covers all 31 car parks of the metropole (city-centre garages
run by Orléans Gestion / Indigo / Carrefour, plus Effia-run tram P+R and
small bus P+R); 23 carry a live free-space count, refreshed every few
minutes. City-centre garages and tram P+R are mixed in one feed --
type_parking says which ("Parking" / "Parking Relais Tram" / "Parking
Relais Bus").

Timestamps: "horodatage_maj_places_disponibles" carries a correct local
offset (e.g. "2026-10-05T16:04:52+02:00" fetched at 14:08 UTC), so it is
simply converted to UTC -- no local-as-UTC correction needed.

Skipped: rows with places_disponibles_temps_reel != "oui" (no live count
-- the small bus P+R, Jules Verne, Bustière, Gare des Aubrais enclos, dépose
minute), rows whose etat_equipement is not "en service" (e.g. Halles
Charpenterie "fermé pour travaux", which still reports a plausible-looking
free count), and rows with no count/timestamp or capacity <= 0.

Place ids use the dataset's own "id_equipement" UUID (the "id" column is
empty), not the Opendatasoft recordid, which is not stable.
"""

from __future__ import annotations

from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = (
    "https://data.orleans-metropole.fr/api/explore/v2.1/catalog/datasets/"
    "om-mobilite-parcs-stationnement/records?limit=100"
)
WEB_URL = "https://data.orleans-metropole.fr/explore/dataset/om-mobilite-parcs-stationnement/"

# INSEE code -> commune (the dataset has no commune-name field)
COMMUNES = {
    "45234": "Orléans",
    "45147": "Fleury-les-Aubrais",
    "45232": "Olivet",
    "45075": "La Chapelle-Saint-Mesmin",
    "45272": "Saint-Cyr-en-Val",
    "45284": "Saint-Jean-de-Braye",
    "45285": "Saint-Jean-de-la-Ruelle",
    "45286": "Saint-Jean-le-Blanc",
}


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


class OrleansLiveAdapter(SourceAdapter):
    name = "orleans-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        data = fetcher.get_json(API_URL)
        for r in data.get("results", []):
            fid = (r.get("id_equipement") or "").strip()
            name = (r.get("nom") or "").strip()
            if not fid or not name:
                continue
            if (r.get("places_disponibles_temps_reel") or "").strip().lower() != "oui":
                continue
            if (r.get("etat_equipement") or "").strip().lower() != "en service":
                continue
            total = _int(r.get("nb_places"))
            free = _int(r.get("nb_places_disponibles"))
            ts_raw = r.get("horodatage_maj_places_disponibles")
            if not total or total <= 0 or free is None or free < 0 or not ts_raw:
                continue
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                continue
            ts = ts.astimezone(timezone.utc).isoformat(timespec="seconds")
            yield fid, name, r, total, free, ts

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for fid, name, r, total, _free, _ts in self._rows(fetcher):
            geo = r.get("geo") or {}
            records.append(
                CapacityRecord(
                    place_id=f"{self.name}-{fid}",
                    place_name=name,
                    city_name=COMMUNES.get(str(r.get("insee") or ""), "Orléans"),
                    num_all=total,
                    source_id=self.name,
                    address=r.get("adresse"),
                    latitude=geo.get("lat"),
                    longitude=geo.get("lon"),
                    place_url=r.get("url"),
                    source_web_url=WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return [
            OccupancyRecord(place_id=f"{self.name}-{fid}", ts=ts, free=free)
            for fid, _name, _r, _total, free, ts in self._rows(fetcher)
        ]
