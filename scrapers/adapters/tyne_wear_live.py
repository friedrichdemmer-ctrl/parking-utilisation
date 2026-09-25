"""Live car-park occupancy for Tyne & Wear and Durham (England), via the
North East UTMC Open Data Service (netraveldata.co.uk).

Needs an account: credentials come from the NETRAVELDATA_USER and
NETRAVELDATA_PASSWORD environment variables (Fly secrets in production)
and are sent as HTTP Basic auth. The service sits behind an Azure
Application Gateway that 403s Python's default user agent; HttpFetcher's
own user agent passes. Data is under the Open Government Licence 3.0.

The feed lists 199 sites, but 86 have sent nothing since 2012-2016 (some
duplicating current sites under older codes, capacities dated 2011), so
only sites whose dynamic record has updated since 2020 are kept -- the
same set previously taken from Newcastle University's Urban Observatory
mirror, whose UTMC site codes this adapter keeps as place ids.

Occupancy is only recorded for sites actively counting: state SPACES,
ALMOST FULL or FULL, and updated within the last hour. About 17 sites
(Metrocentre, North Tyneside, Sunderland) only send an hourly "OPEN" with
occupancy 0, which would falsely read as empty, so they stay
capacity-only. Timestamps are labelled "+0000" but are UK local time (a
reading stamped 11:30 arrives at 10:30 UTC in summer); a timestamp that
would lie in the future as UTC is reinterpreted as Europe/London.
"""

from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from scrapers import uk_postcodes
from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

STATIC_URL = "https://www.netraveldata.co.uk/api/v2/carpark/static"
DYNAMIC_URL = "https://www.netraveldata.co.uk/api/v2/carpark/dynamic"
SOURCE_WEB_URL = "https://www.netraveldata.co.uk/"

ACTIVE_SINCE = datetime(2020, 1, 1, tzinfo=timezone.utc)
MAX_READING_AGE = timedelta(hours=1)
COUNTING_STATES = {"SPACES", "ALMOST FULL", "FULL"}
LONDON = ZoneInfo("Europe/London")


def _auth_headers() -> dict[str, str]:
    user = os.environ.get("NETRAVELDATA_USER")
    password = os.environ.get("NETRAVELDATA_PASSWORD")
    if not user or not password:
        raise RuntimeError("NETRAVELDATA_USER / NETRAVELDATA_PASSWORD not set")
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _parse_ts(value: str | None, now: datetime) -> datetime | None:
    if not value:
        return None
    ts = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f%z")
    if ts > now + timedelta(minutes=5):
        ts = ts.replace(tzinfo=LONDON).astimezone(timezone.utc)
    return ts


def _latest(items: list[dict] | None) -> dict:
    return (items or [{}])[-1]


def _district(result: dict | None) -> str | None:
    d = (result or {}).get("admin_district")
    return "Durham" if d == "County Durham" else d


class TyneWearLiveAdapter(SourceAdapter):
    name = "tyne-wear-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 30 * 60

    def _fetch(self, fetcher) -> tuple[dict[str, dict], dict[str, dict]]:
        headers = _auth_headers()
        static = {s["systemCodeNumber"]: s for s in fetcher.get_json(STATIC_URL, headers=headers)}
        dynamic = {d["systemCodeNumber"]: d for d in fetcher.get_json(DYNAMIC_URL, headers=headers)}
        return static, dynamic

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        now = datetime.now(timezone.utc)
        static, dynamic = self._fetch(fetcher)
        records = []
        for site_id, s in static.items():
            last = _parse_ts(_latest((dynamic.get(site_id) or {}).get("dynamics")).get("lastUpdated"), now)
            if last is None or last < ACTIVE_SINCE:
                continue
            definition = _latest(s.get("definitions"))
            capacity = _latest(s.get("configurations")).get("capacity")
            name = (definition.get("shortDescription") or "").strip()
            point = definition.get("point") or {}
            lat, lon = point.get("latitude"), point.get("longitude")
            if not name or not capacity:
                continue
            city = _district(uk_postcodes.nearest(fetcher, lat, lon)) if lat and lon else None
            records.append(
                CapacityRecord(
                    place_id=f"tyne-wear-live-{site_id}",
                    place_name=name,
                    city_name=city or "Newcastle upon Tyne",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=(definition.get("longDescription") or "").strip() or None,
                    latitude=lat,
                    longitude=lon,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        now = datetime.now(timezone.utc)
        static, dynamic = self._fetch(fetcher)
        records = []
        for site_id, d in dynamic.items():
            reading = _latest(d.get("dynamics"))
            ts = _parse_ts(reading.get("lastUpdated"), now)
            occupied = reading.get("occupancy")
            capacity = _latest((static.get(site_id) or {}).get("configurations")).get("capacity")
            if (
                reading.get("stateDescription") not in COUNTING_STATES
                or ts is None
                or now - ts > MAX_READING_AGE
                or occupied is None
                or not capacity
            ):
                continue
            records.append(
                OccupancyRecord(
                    place_id=f"tyne-wear-live-{site_id}",
                    ts=ts.isoformat(timespec="seconds"),
                    free=int(capacity) - int(occupied),
                )
            )
        return records
