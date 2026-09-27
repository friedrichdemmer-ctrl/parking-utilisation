"""Live parking for Vigo, via the Concello de Vigo's open data ("Datos en
tiempo real de ocupación de parkings en la cidade", datos-ckan.vigo.org
dataset t-parking-real), refreshed every 3 minutes.

One JSON list with the city's ~11 public garages: total spaces, free
spaces, coordinates and a local-time timestamp ("2026-09-27 08:43:00" was
fetched at 06:45 UTC), read as Europe/Madrid.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://datos.vigo.org/data/trafico/parkings-ocupacion.json"
SOURCE_WEB_URL = "https://datos-ckan.vigo.org/dataset/t-parking-real"
MADRID = ZoneInfo("Europe/Madrid")


class VigoLiveAdapter(SourceAdapter):
    name = "vigo-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for r in fetcher.get_json(API_URL):
            gid, name, total = r.get("id_parking"), (r.get("nombre") or "").strip(), r.get("totalplazas")
            if not gid or not name or not isinstance(total, int) or total <= 0:
                continue
            records.append(
                CapacityRecord(
                    place_id=f"vigo-live-{gid}",
                    place_name=name,
                    city_name="Vigo",
                    num_all=total,
                    source_id=self.name,
                    latitude=r.get("lat"),
                    longitude=r.get("lon"),
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for r in fetcher.get_json(API_URL):
            gid, free, ts = r.get("id_parking"), r.get("plazaslibres"), r.get("fechahora")
            if not gid or not isinstance(free, int) or not ts:
                continue
            utc = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=MADRID).astimezone(timezone.utc)
            records.append(OccupancyRecord(place_id=f"vigo-live-{gid}", ts=utc.isoformat(timespec="seconds"), free=free))
        return records
