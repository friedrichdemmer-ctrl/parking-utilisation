"""Live parking occupancy for Amsterdam, via the city's own VORin traffic
system (p-info.vorin-amsterdam.nl), refreshed roughly every minute per the
feed's own "PubDate" field.

Found via a country-wide data.europa.eu full-text search for real-time
parking; not part of the RDW Nationaal Parkeerregister (NPR) already
covering Q-Park's and other operators' Dutch facilities via qpark_nl.py/
other_operators_nl.py -- this is Amsterdam's own municipal system.

The feed mixes car parks ("P-"/"PR-"/"PT-" prefixes) with bicycle parking
("FP-" prefix, name containing "fietsstalling") and a couple of "TEST"/
"Dummy" placeholder entries -- only genuine car facilities with a
positive capacity and State "ok" are kept.

Three entries are the same physical garage published twice under both a
regular ID and a park-and-ride alias, confirmed by identical capacity and
near-identical coordinates (all under ~200m apart, versus every other
"nearby" pair in this dataset having a different capacity, since central
Amsterdam genuinely has many distinct garages close together): "PR-011_
ArenA" duplicates "P-201_ P1 ArenA", "PR-002_ Olympisch Stadion P+R"
duplicates "P-102_ Olympisch Stadion", and "PR-304_ VUmc" duplicates
"P-302_ VUmc (ACTA)". The park-and-ride alias is dropped in each pair
rather than counting the same garage's capacity twice.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://p-info.vorin-amsterdam.nl/v1/ParkingLocation.json"
EXCLUDED_DUPLICATE_ALIASES = {
    "PR-011_ ArenA",
    "PR-002_ Olympisch Stadion P+R",
    "PR-304_ VUmc",
}


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class AmsterdamLiveAdapter(SourceAdapter):
    name = "amsterdam-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        data = fetcher.get_json(API_URL)
        for f in data.get("features", []):
            p = f.get("properties", {})
            name = (p.get("Name") or "").strip()
            if not name or name in EXCLUDED_DUPLICATE_ALIASES:
                continue
            if name.startswith("FP-") or "fietsstalling" in name.lower() or "test" in name.lower() or "dummy" in name.lower():
                continue
            if p.get("State") != "ok":
                continue
            try:
                total = int(p.get("ShortCapacity") or 0)
                free = int(p.get("FreeSpaceShort") or 0)
            except ValueError:
                continue
            if total <= 0:
                continue
            ts_raw = p.get("PubDate")
            if not ts_raw:
                continue
            lat, lon = f.get("geometry", {}).get("coordinates", [None, None])
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(timespec="seconds")
            yield f.get("Id"), name, total, free, lat, lon, ts

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for place_id, name, total, _free, lat, lon, _ts in self._rows(fetcher):
            records.append(
                CapacityRecord(
                    place_id=f"amsterdam-live-{_slug(name)}-{place_id[:8]}",
                    place_name=name,
                    city_name="Amsterdam",
                    num_all=total,
                    source_id=self.name,
                    latitude=lat,
                    longitude=lon,
                    source_web_url="https://p-info.vorin-amsterdam.nl/v1/ParkingLocation.json",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for place_id, name, _total, free, _lat, _lon, ts in self._rows(fetcher):
            records.append(OccupancyRecord(place_id=f"amsterdam-live-{_slug(name)}-{place_id[:8]}", ts=ts, free=free))
        return records
