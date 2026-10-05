"""Live parking for Braunschweig, from the city's own GeoJSON feed behind
the parking layer of its city map (braunschweig.de/plan, "parken").

Braunschweig used to arrive only via the defgsus community archive under
source_id "braunschweig-parken", which reads this same file; this adapter
takes over that source_id (its name). place_ids are the archive's:
f"braunschweig-parken-{archive_slug(name)}".

The file lists 10 garages, but only those with an "openingState" carry
counts; the rest (Forschungsflughafen, Ring-Center, and Magni and Packhof,
whose externalId now ends "_DYNAMISCH_AUSLAUSTUNGSDATEN_DEAKTIVIERT",
i.e. live data switched off) are skipped. Each garage has its own ISO
"timestamp" with a correct offset (it matched the fetch time), used as
the reading time. Readings are only kept for openingState "open".

Parkhaus Schloss reported 0 occupied / 1300 free with fresh timestamps
on a Monday afternoon (2026-10-05), and its archive history is constant
too -- apparently a dead counter, kept since the feed gives no way to
tell, but worth excluding downstream.
"""

from __future__ import annotations

from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

FEED_URL = "https://www.braunschweig.de/apps/pulp/result/parkhaeuser.geojson"
WEB_URL = "https://www.braunschweig.de/plan/index.php#parken"


def _place_id(name: str) -> str:
    return f"braunschweig-parken-{archive_slug(name)}"


class BraunschweigLiveAdapter(SourceAdapter):
    name = "braunschweig-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _features(self, fetcher) -> list[dict]:
        return fetcher.get_json(FEED_URL).get("features", [])

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for f in self._features(fetcher):
            p = f.get("properties", {})
            name, capacity = (p.get("name") or "").strip(), p.get("capacity")
            if not name or not capacity:
                continue
            coords = (f.get("geometry") or {}).get("coordinates") or [None, None]
            records.append(
                CapacityRecord(
                    place_id=_place_id(name),
                    place_name=name,
                    city_name="Braunschweig",
                    num_all=int(capacity),
                    source_id=self.name,
                    latitude=coords[1],
                    longitude=coords[0],
                    source_web_url=WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for f in self._features(fetcher):
            p = f.get("properties", {})
            name, capacity, free, stamp = (p.get("name") or "").strip(), p.get("capacity"), p.get("free"), p.get("timestamp")
            if not name or p.get("openingState") != "open" or free is None or not capacity or not stamp:
                continue
            if not 0 <= int(free) <= int(capacity):
                continue
            ts = datetime.fromisoformat(stamp).astimezone(timezone.utc).isoformat(timespec="seconds")
            records.append(OccupancyRecord(place_id=_place_id(name), ts=ts, free=int(free)))
        return records
