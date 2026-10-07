"""Live parking for the OPG (Osnabrücker Parkstätten-Betriebsgesellschaft)
garages and car parks in Osnabrück, Quakenbrück and Bad Rothenfelde, from
the operator's own site parken-osnabrueck.de.

These used to arrive only via the defgsus community archive under
source_id "parken-osnabrueck". The archive scraper reads the same
endpoint as this adapter -- the JSON behind the site's map
("ajaxCallGetUtilizationData"), keyed "ramp-<n>" with the operator's
numeric identifier, capacity and "available" -- and its place_ids are
f"parken-osnabrueck-{identifier}", so this adapter takes over that
source_id (its name) and writes into the same place_ids.

The utilisation JSON carries no names; those, with address and
coordinates, come from the "parkingRampData" object embedded in the
homepage (its "tstamp" is when the record was edited, not a reading time).
Neither carries an update time for the counts, so readings use the
fetch time. The site itself shows a ramp as "keine Infos" when its
thresholds are unset, so readings are skipped when the capacity is 0 or
"available" is missing or outside 0..capacity.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

SITE_URL = "https://www.parken-osnabrueck.de/"
API_URL = (
    SITE_URL + "index.php?type=427590"
    "&tx_tiopgparkhaeuserosnabrueck_parkingosnabruek%5Bcontroller%5D=Parking"
    "&tx_tiopgparkhaeuserosnabrueck_parkingosnabruek%5Baction%5D=ajaxCallGetUtilizationData"
)
RAMP_DATA_RE = re.compile(r"var parkingRampData = (\{.*?\});\s*\n", re.S)
DETAIL_RE = re.compile(r'href=\\?"(\\?/parken\\?/parkplatzsuche\\?/detail\\?/[^"\\]+\.html)')


def _place_id(identifier) -> str:
    return f"parken-osnabrueck-{identifier}"


class OsnabrueckLiveAdapter(SourceAdapter):
    name = "parken-osnabrueck"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _utilisation(self, fetcher) -> list[dict]:
        data = fetcher.get_json(API_URL)
        # The site answers with an empty list ([]) when it has no readings (seen 2026-10-06 onwards);
        # the normal answer is an object keyed "ramp-<n>". Both mean "nothing to read" when empty.
        return list(data.values()) if isinstance(data, dict) else [u for u in data if isinstance(u, dict)]

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        match = RAMP_DATA_RE.search(fetcher.get_text(SITE_URL))
        meta = json.loads(match.group(1)) if match else {}
        records = []
        for u in self._utilisation(fetcher):
            ident, capacity = u.get("identifier"), u.get("capacity")
            m = meta.get(str(ident))
            if ident is None or not capacity or not m:
                continue
            detail = DETAIL_RE.search(m.get("gmapsMarker") or "")
            records.append(
                CapacityRecord(
                    place_id=_place_id(ident),
                    place_name=(m.get("name") or "").strip() or str(ident),
                    city_name=(m.get("city") or "").strip() or "Osnabrück",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=(m.get("address") or "").strip() or None,
                    latitude=float(m["latitude"]) if m.get("latitude") else None,
                    longitude=float(m["longitude"]) if m.get("longitude") else None,
                    place_url=SITE_URL.rstrip("/") + detail.group(1).replace("\\/", "/") if detail else None,
                    source_web_url=SITE_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        records = []
        for u in self._utilisation(fetcher):
            ident, capacity, free = u.get("identifier"), u.get("capacity"), u.get("available")
            if ident is None or not capacity or free is None or not 0 <= int(free) <= int(capacity):
                continue
            records.append(OccupancyRecord(place_id=_place_id(ident), ts=now, free=int(free)))
        return records
