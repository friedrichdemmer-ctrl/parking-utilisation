"""Live parking occupancy for Montpellier Méditerranée Métropole, from the
metropole's own FIWARE / NGSI-LD API (portail-api.montpellier.fr), entity
type "OffStreetParking":

    https://portail-api-data.montpellier.fr/ngsi-ld/v1/entities?type=OffStreetParking&limit=1000

Documented on data.montpellier3m.fr, dataset "Disponibilité des places dans
les parkings de Montpellier Méditerranée Métropole"; licence ODbL. The old
host portail-api-data.montpellier3m.fr answered 503 when this was written
(2026-10-05) and is only tried as a fallback. The older "/offstreetparking"
endpoint is marked deprecated in the API spec and uses a different id
numbering ("urn:ngsi-ld:parking:002" = Arc de Triomphe) and timestamps that
are local time mislabelled as UTC for some garages -- not used here.

Timestamps: each garage's availableSpotNumber carries an "observedAt" in
genuine UTC (checked against the fetch time: Triangle/Pitot read 14:14Z at a
14:16Z fetch; the temporal history shows ~5-minute updates). That is used as
the reading time.

The listing has 39 entities, of which ~21 carry a live count: city-centre
garages (Comédie, Corum, Triangle, Polygone, ...) plus tram park-and-ride
sites (Circé Odysseum, Mosson, Sabines, Occitanie, Garcia Lorca,
Euromédecine, Saint-Jean-le-Sec) and a few "proximité" car parks in
Castelnau-le-Lez. Skipped:
  * entities without availableSpotNumber (shopping-centre and outer P+R
    sites that are listed with capacity only) -- no capacity row either;
  * status other than "Open";
  * readings older than STALE_AFTER (Foch Préfecture frozen since
    2026-09-28, Polygone since 2025-12-31 -- storage would dedupe the
    repeated timestamp anyway, this just keeps them out explicitly);
  * readings with free > capacity (Charles de Gaulle reports 75 free of 50).

Capacity is "totalSpotNumber". Note some garages also carry a smaller
"publicSpaces" (e.g. Triangle 594 total / 436 public) -- the rest are
season-ticket spaces; which of the two the free count is measured against
is not documented, totalSpotNumber is the one the feed pairs it with.

place_ids use the entity's own id suffix ("34172-P-001"), which is the
national BNLS-style facility id and stable across runs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URLS = [
    "https://portail-api-data.montpellier.fr/ngsi-ld/v1/entities?type=OffStreetParking&limit=1000",
    "https://portail-api-data.montpellier3m.fr/ngsi-ld/v1/entities?type=OffStreetParking&limit=1000",
]
WEB_URL = "https://data.montpellier3m.fr/dataset/disponibilite-des-places-dans-les-parkings-de-montpellier-mediterranee-metropole"
STALE_AFTER = timedelta(hours=6)

# INSEE code -> commune, for the communes that appear in the feed
COMMUNES = {
    34172: "Montpellier",
    34057: "Castelnau-le-Lez",
    34270: "Saint-Jean-de-Védas",
    34120: "Jacou",
    34123: "Juvignac",
    34129: "Lattes",
    34198: "Pérols",
    34077: "Clapiers",
    34090: "Grabels",
}


def _val(entity: dict, key: str):
    prop = entity.get(key)
    return prop.get("value") if isinstance(prop, dict) else None


class MontpellierLiveAdapter(SourceAdapter):
    name = "montpellier-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _entities(self, fetcher) -> list[dict]:
        last_exc = None
        for url in API_URLS:
            try:
                data = fetcher.get_json(url)
                if isinstance(data, list):
                    return data
            except Exception as exc:  # noqa: BLE001 -- try the fallback host
                last_exc = exc
        if last_exc:
            raise last_exc
        return []

    def _rows(self, fetcher):
        for e in self._entities(fetcher):
            ent_id = (e.get("id") or "").rsplit(":", 1)[-1]
            name = (_val(e, "name") or "").strip()
            total = _val(e, "totalSpotNumber")
            if not ent_id or not name or not isinstance(total, (int, float)) or total <= 0:
                continue
            avail = e.get("availableSpotNumber")
            if not isinstance(avail, dict) or avail.get("value") is None:
                continue  # listed with capacity only, no live count
            yield ent_id, name, e, int(total), avail

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for ent_id, name, e, total, _avail in self._rows(fetcher):
            loc = (_val(e, "location") or {}).get("coordinates") or [None, None]
            records.append(
                CapacityRecord(
                    place_id=f"{self.name}-{ent_id}",
                    place_name=name,
                    city_name=COMMUNES.get(_val(e, "insee"), "Montpellier"),
                    num_all=total,
                    source_id=self.name,
                    address=_val(e, "address"),
                    latitude=loc[1],
                    longitude=loc[0],
                    source_web_url=WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        now = datetime.now(timezone.utc)
        records = []
        for ent_id, _name, e, total, avail in self._rows(fetcher):
            if _val(e, "status") != "Open":
                continue
            try:
                free = int(avail["value"])
                ts = datetime.fromisoformat(avail["observedAt"].replace("Z", "+00:00")).astimezone(timezone.utc)
            except (KeyError, TypeError, ValueError):
                continue
            if not 0 <= free <= total or now - ts > STALE_AFTER:
                continue
            records.append(
                OccupancyRecord(place_id=f"{self.name}-{ent_id}", ts=ts.isoformat(timespec="seconds"), free=free)
            )
        return records
