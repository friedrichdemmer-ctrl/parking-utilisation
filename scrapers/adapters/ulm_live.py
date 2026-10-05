"""Live parking for Ulm's city garages, from the operator's own JSON
interface on parken-in-ulm.de (Ulmer Parkbetriebs-GmbH; documented at
https://parken-in-ulm.de/parkdaten, Datenlizenz Deutschland - Namensnennung
2.0, attribution "parken-in-ulm.de").

Ulm used to arrive via the defgsus community archive under source_id
"parken-in-ulm", which scraped this same site's HTML; the archive has had no
parken-in-ulm columns since 2026-08. Since then the six garages MobiData BW
carries have been fed from its "ulm_sensors" source
(mobidata_bw_existing.py), which is a separate, sensor-based count -- at
13:14-13:17 UTC on 2026-10-05 it showed Am Rathaus 83 free where this feed
showed 62, and its capacities differ by 4-19 spaces. This adapter goes back to the operator's gate counts
the archive history was built from, and also covers CCU Süd and Frauenstraße,
which MobiData does not carry (stale since 2023-12). It is meant to replace
UlmMobidataBwOccupancyAdapter, not to run alongside it: both write the same
place_ids with different timestamps and different numbers.

The interface is a JSON-RPC POST (an empty JSON object as the body);
"last_update" is per garage, in UTC as documented (checked: 13:17 at a
13:18 UTC fetch). The operator says data older than ten minutes is not
current, so readings older than that are skipped rather than re-stamped.

The interface has no open/closed flag, so closed garages have to be
handled here:
- Kornhaus is skipped outright: closed to short-term parkers for renovation
  (site text, 2026-10), yet reported as 0 free with a fresh timestamp. It has
  never had a reading on file, so nothing is lost.
- Theater (Mon-Fri 18:30-02:00, Sat/Sun 06:30-02:00) and CCU Nord (Mon-Fri
  06:30-22:15, Sat 08:30-22:15, closed Sundays) are skipped outside their
  opening hours, as listed on the site's homepage: on a Monday afternoon
  Theater read 0 of 74 free here (closed, not full).
"""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

API_URL = "https://parken-in-ulm.de/get_parking_data"
SOURCE_WEB_URL = "https://parken-in-ulm.de/parkdaten"
MAX_AGE = timedelta(minutes=10)
BERLIN = ZoneInfo("Europe/Berlin")

# feed name -> archive place name, where they differ
LEGACY_NAMES = {
    "CCU Nord": "Congress Centrum Nord / Basteicenter",
    "CCU Süd": "Congress Centrum Süd / Maritim Hotel",
}
CLOSED = {"Kornhaus"}


def _theater_open(local: datetime) -> bool:
    t = local.time()
    if t < time(2, 0):  # the previous evening's session, every day
        return True
    return t >= (time(18, 30) if local.weekday() < 5 else time(6, 30))


def _ccu_nord_open(local: datetime) -> bool:
    t, day = local.time(), local.weekday()
    if day == 6:
        return False
    return (time(6, 30) if day < 5 else time(8, 30)) <= t < time(22, 15)


OPENING_HOURS = {"Theater": _theater_open, "CCU Nord": _ccu_nord_open}


def _place_id(name: str) -> str:
    return f"parken-in-ulm-{archive_slug(LEGACY_NAMES.get(name, name))}"


class UlmLiveAdapter(SourceAdapter):
    name = "parken-in-ulm"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _facilities(self, fetcher) -> list[dict]:
        body = fetcher.post_text(API_URL, "{}", headers={"Content-Type": "application/json"})
        return json.loads(body).get("result", {}).get("facilities", [])

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for f in self._facilities(fetcher):
            name, capacity = (f.get("name") or "").strip(), f.get("total_parking_spaces")
            if not name or not capacity:
                continue
            records.append(
                CapacityRecord(
                    place_id=_place_id(name),
                    place_name=LEGACY_NAMES.get(name, name),
                    city_name="Ulm",
                    num_all=int(capacity),
                    source_id=self.name,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        now = datetime.now(timezone.utc)
        records = []
        for f in self._facilities(fetcher):
            name, free, updated = (f.get("name") or "").strip(), f.get("vacant_parking_spaces"), f.get("last_update")
            if not name or name in CLOSED or free is None or not updated:
                continue
            ts = datetime.strptime(updated, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if now - ts > MAX_AGE:
                continue
            is_open = OPENING_HOURS.get(name)
            if is_open and not is_open(ts.astimezone(BERLIN)):
                continue
            records.append(OccupancyRecord(place_id=_place_id(name), ts=ts.isoformat(timespec="seconds"), free=int(free)))
        return records
