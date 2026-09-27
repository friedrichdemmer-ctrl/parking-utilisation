"""Live parking for Bologna, via the city's Opendatasoft portal
(opendata.comune.bologna.it). The first Italian source in this project.

- "disponibilita-parcheggi-vigente": the 3 garages on the city's guidance
  system (Autostazione, VIII Agosto, Riva Reno) with capacity, free and
  occupied counts and a UTC timestamp, refreshed every few minutes.
  "disponibilita-parcheggi-storico" holds the same readings from
  2024-06-07 to 2024-11-09 (backfilled once, not fetched here).
- "parcheggi": 44 car parks with a space count. Only the public ones are
  kept (tariff "pagamento", "gratuito" or "righe blu"); residents-only
  ("pertinenziale") and subscription-only ("abbonamento") ones are left
  out, as are the three live garages, which come from the first dataset.

Opendatasoft record ids are content hashes, so place_ids are built from
names (see bordeaux_metropole_live.py for why).

The "data" timestamps are Italian local time labelled as UTC: a reading
fetched at 05:45 UTC on 2026-09-27 was stamped "07:39:00+00:00". They are
re-read as Europe/Rome wall-clock time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

API = "https://opendata.comune.bologna.it/api/explore/v2.1/catalog/datasets"
LIVE_URL = API + "/disponibilita-parcheggi-vigente/records?limit=100"
STATIC_URL = API + "/parcheggi/records?limit=100"
SOURCE_WEB_URL = "https://opendata.comune.bologna.it/explore/dataset/disponibilita-parcheggi-vigente/"
PUBLIC_TARIFFS = {"pagamento", "gratuito", "righe blu"}
# "parcheggi" names of the garages the live dataset already covers
LIVE_NAMES_IN_STATIC = {"Piazza otto agosto", "Riva Reno", "Autostazione"}


ROME = ZoneInfo("Europe/Rome")


def _utc(ts: str) -> str:
    local = datetime.fromisoformat(ts).replace(tzinfo=None)
    return local.replace(tzinfo=ROME).astimezone(timezone.utc).isoformat(timespec="seconds")


def _place_id(name: str) -> str:
    return f"bologna-live-{archive_slug(name).lower()}"


class BolognaLiveAdapter(SourceAdapter):
    name = "bologna-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for r in fetcher.get_json(LIVE_URL).get("results", []):
            name, total = (r.get("parcheggio") or "").strip(), r.get("posti_totali")
            if not name or not total:
                continue
            point = r.get("coordinate") or {}
            records.append(
                CapacityRecord(
                    place_id=_place_id(name), place_name=name, city_name="Bologna", num_all=int(total),
                    source_id=self.name, latitude=point.get("lat"), longitude=point.get("lon"),
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        for r in fetcher.get_json(STATIC_URL).get("results", []):
            name, spaces = (r.get("name") or "").strip(), r.get("posti")
            if not name or not spaces or name in LIVE_NAMES_IN_STATIC or r.get("tariffa") not in PUBLIC_TARIFFS:
                continue
            point = r.get("geo_point_2d") or {}
            records.append(
                CapacityRecord(
                    place_id=_place_id(name), place_name=name, city_name="Bologna", num_all=int(spaces),
                    source_id=self.name, address=(r.get("nomezona") or "").strip().title() or None,
                    latitude=point.get("lat"), longitude=point.get("lon"),
                    source_web_url=API.replace("/api/explore/v2.1/catalog/datasets", "/explore/dataset/parcheggi/"),
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for r in fetcher.get_json(LIVE_URL).get("results", []):
            name, free, ts = (r.get("parcheggio") or "").strip(), r.get("posti_liberi"), r.get("data")
            if not name or free is None or not ts:
                continue
            records.append(OccupancyRecord(place_id=_place_id(name), ts=_utc(ts), free=int(free)))
        return records
