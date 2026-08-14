"""Q-Park garages in the Netherlands, via the Nationaal Parkeerregister (NPR)
run by RDW (the Dutch vehicle licensing authority) -- openly licensed (CC0),
no authentication required.

Q-Park itself is a registered data provider in the NPR (areamanagerid 2448,
"Q-Park Nederland BV"), publishing both static facility data and, for most
of its facilities, genuinely live occupancy -- confirmed directly before
writing this: of Q-Park's 159 registered areas, 151 had real dynamic (live)
data on inspection.

Two-step lookup:
  1. opendata.rdw.nl's Socrata "PARKEERGEBIED" dataset, filtered to
     areamanagerid=2448, gives the UUIDs of Q-Park's own facilities without
     downloading the full ~15k-facility national registry.
  2. Each UUID is queried directly against npropendata.rdw.nl's static and
     dynamic endpoints.

The static payload's operator.postalAddress is Q-Park's own registered
business address (their HQ in Maastricht), not the garage's location --
the real address is under accessPoints[0].accessPointAddress instead. Easy
mistake to make since both look like plausible "address" fields; verified
against a real response before picking the right one.

Live occupancy is much smaller than it first looked. The facility list
marks 151 of Q-Park's 159 areas as having a dynamicDataUrl, which reads
like broad live coverage -- but querying them for real showed most return
401 Unauthorized (anonymous access is evidently not granted per-facility
just because the field is present), and one of the handful that did
return 200 turned out to be replaying a single reading from May 2025, over
a year stale, not actually live. So this only writes occupancy when the
response succeeds AND its timestamp is recent (MAX_OCCUPANCY_AGE_SECONDS)
-- in practice that was ~7 facilities out of 159 on the run this was
written against, not the ~150 the facility list implied.
"""

from __future__ import annotations

import re
import urllib.error
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

QPARK_AREAMANAGER_ID = "2448"
AREAS_URL = f"https://opendata.rdw.nl/resource/mz4f-59fw.json?areamanagerid={QPARK_AREAMANAGER_ID}&$limit=500"
NPR_BASE = "https://npropendata.rdw.nl/parkingdata/v2"
MAX_OCCUPANCY_AGE_SECONDS = 2 * 3600


def _slug(name: str) -> str:
    s = name.lower()
    s = s.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


def _city_from_area_name(area_name: str) -> str:
    # Area names are formatted like "GRONINGEN-Museum Centrum", less
    # consistently "Scheveningen - Strand" -- used only as a fallback when
    # accessPointAddress.city isn't present.
    city = re.split(r"\s*-\s*", area_name, maxsplit=1)[0]
    return city.strip().title()


def _place_id(uuid: str, area_name: str) -> str:
    return f"npr-qpark-nl-{uuid}-{_slug(area_name)}"


class QParkNetherlandsAdapter(SourceAdapter):
    name = "npr-qpark-nl"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 30 * 60

    def _areas(self, fetcher) -> list[dict]:
        return fetcher.get_json(AREAS_URL)

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for area in self._areas(fetcher):
            uuid = area.get("uuid")
            area_name = area.get("areaname")
            if not uuid or not area_name:
                continue
            try:
                static = fetcher.get_json(f"{NPR_BASE}/static/{uuid}")
            except Exception as exc:
                print(f"[{self.name}] capacity: failed to fetch static data for {area_name}: {exc}")
                continue
            info = static.get("parkingFacilityInformation") or {}
            specs = info.get("specifications") or []
            capacity = specs[0].get("capacity") if specs else None
            if not capacity:
                continue
            location = info.get("locationForDisplay") or {}
            access_points = info.get("accessPoints") or []
            address = (access_points[0].get("accessPointAddress") if access_points else None) or {}
            address_str = " ".join(p for p in (address.get("streetName"), address.get("houseNumber")) if p) or None
            city = address.get("city") or _city_from_area_name(area_name)
            records.append(
                CapacityRecord(
                    place_id=_place_id(uuid, area_name),
                    place_name=area_name,
                    city_name=city,
                    num_all=int(capacity),
                    source_id=self.name,
                    address=address_str,
                    latitude=location.get("latitude"),
                    longitude=location.get("longitude"),
                    source_web_url="https://www.q-park.nl/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for area in self._areas(fetcher):
            uuid = area.get("uuid")
            area_name = area.get("areaname")
            if not uuid or not area_name:
                continue
            try:
                dynamic = fetcher.get_json(f"{NPR_BASE}/dynamic/{uuid}")
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 404):
                    continue  # not exposed for us -- most Q-Park facilities, despite listing a dynamicDataUrl
                print(f"[{self.name}] occupancy: failed to fetch dynamic data for {area_name}: {exc}")
                continue
            except Exception as exc:
                print(f"[{self.name}] occupancy: failed to fetch dynamic data for {area_name}: {exc}")
                continue
            status = (dynamic.get("parkingFacilityDynamicInformation") or {}).get("facilityActualStatus") or {}
            free = status.get("vacantSpaces")
            last_updated = status.get("lastUpdated")
            if free is None or last_updated is None:
                continue
            age_seconds = datetime.now(timezone.utc).timestamp() - last_updated
            if age_seconds > MAX_OCCUPANCY_AGE_SECONDS:
                continue  # stale reading (seen: one facility replaying a >1-year-old value) -- not actually live
            ts = datetime.fromtimestamp(last_updated, tz=timezone.utc).isoformat(timespec="seconds")
            records.append(OccupancyRecord(place_id=_place_id(uuid, area_name), ts=ts, free=int(free)))
        return records
