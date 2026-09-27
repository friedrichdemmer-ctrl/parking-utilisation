"""Live parking for Florence, via the city's open data ("Dati in tempo reale
sui posti liberi nei parcheggi di Firenze - Posti liberi", Comune di
Firenze, data from Firenze Parcheggi).

One GeoJSON (datigis.comune.fi.it) with the 13 Firenze Parcheggi garages:
total spaces, paid spaces, free spaces and an update time with offset.
The free count is relative to the total, not the paid spaces -- several
garages report more free spaces than paid ones (Novoli 198 free of 170
paid, 242 total) -- so posti_totali is the capacity.
"""

from __future__ import annotations

from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = (
    "https://datigis.comune.fi.it/resources/open-data/"
    "dati-in-tempo-reale-sui-posti-liberi-nei-parcheggi-di-firenze-posti-liberi/fipark_posti_liberi.geojson"
)
SOURCE_WEB_URL = "https://opendata.comune.fi.it/"


def _int(v) -> int | None:
    s = str(v if v is not None else "").strip()
    return int(s) if s.isdigit() else None


class FirenzeLiveAdapter(SourceAdapter):
    name = "firenze-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for f in fetcher.get_json(API_URL).get("features", []):
            p = f.get("properties") or {}
            total, name = _int(p.get("posti_totali")), (p.get("nome") or "").strip()
            if not p.get("id") or not name or not total:
                continue
            lon, lat = ((f.get("geometry") or {}).get("coordinates") or [None, None])[:2]
            records.append(
                CapacityRecord(
                    place_id=f"firenze-live-{p['id']}",
                    place_name=name,
                    city_name="Firenze",
                    num_all=total,
                    source_id=self.name,
                    address=(p.get("indirizzo") or "").strip() or None,
                    latitude=lat,
                    longitude=lon,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for f in fetcher.get_json(API_URL).get("features", []):
            p = f.get("properties") or {}
            free, ts = _int(p.get("posti_liberi")), p.get("ultimo_aggiornamento")
            if not p.get("id") or free is None or not ts:
                continue
            utc = datetime.fromisoformat(ts).astimezone(timezone.utc).isoformat(timespec="seconds")
            records.append(OccupancyRecord(place_id=f"firenze-live-{p['id']}", ts=utc, free=free))
        return records
