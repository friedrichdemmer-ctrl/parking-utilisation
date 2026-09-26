"""Hannover: inner-city garages (capacity-only) and Region Hannover
Park+Ride sites (live where sensored), from the GeoJSON layers behind the
VMZ Niedersachsen traffic-information site (vmz-niedersachsen.de, Mapsight).

These are the public site's own map layers, not a documented open-data
API. "stadt-hannover-parking" lists the 16 garages of the city's parking
guidance system with their capacity inside the HTML description
("Stellplätze 269") but no occupancy -- the 7 garages whose live counts
the city's "Hannover Parken" app shows are not published here.
"region-hannover-park-and-ride2" lists ~70 P+R sites across the region
with a structured "parking" object; about 15 carry live totals
(totalFree / totalCapacity) and a timestamp with UTC offset. Sites
without live totals take their capacity from the sum of their car areas.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

BASE = "https://www.vmz-niedersachsen.de/geojson/"
GARAGES_URL = BASE + "stadt-hannover-parking.geojson"
PARK_RIDE_URL = BASE + "region-hannover-park-and-ride2.geojson"
SOURCE_WEB_URL = "https://www.vmz-niedersachsen.de/stadt-hannover/parkleitsystem-city"

CAPACITY_RE = re.compile(r"Stellpl\w*\s+(\d+)")


def _text(s) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(s or ""))).replace("\xad", "").split())


def _parking(props: dict) -> dict:
    p = props.get("parking")
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except ValueError:
            return {}
    return p or {}


def _pr_capacity(parking: dict) -> int | None:
    if parking.get("totalCapacity"):
        return int(parking["totalCapacity"])
    total = sum((a.get("motorVehicle") or {}).get("capacity") or 0 for a in parking.get("areas") or [])
    return total or None


class HannoverLiveAdapter(SourceAdapter):
    name = "hannover-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for f in fetcher.get_json(GARAGES_URL).get("features", []):
            p = f.get("properties", {})
            name, m = _text(p.get("title")), CAPACITY_RE.search(_text(p.get("description")))
            if not p.get("id") or not name or not m:
                continue
            lon, lat = ((f.get("geometry") or {}).get("coordinates") or [None, None])[:2]
            records.append(
                CapacityRecord(
                    place_id=f"hannover-live-{p['id']}",
                    place_name=name,
                    city_name="Hannover",
                    num_all=int(m.group(1)),
                    source_id=self.name,
                    latitude=lat,
                    longitude=lon,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        for f in fetcher.get_json(PARK_RIDE_URL).get("features", []):
            p = f.get("properties", {})
            name, capacity = _text(p.get("title")), _pr_capacity(_parking(p))
            if not p.get("id") or not name or not capacity:
                continue
            lon, lat = ((f.get("geometry") or {}).get("coordinates") or [None, None])[:2]
            records.append(
                CapacityRecord(
                    place_id=f"hannover-live-pr-{p['id']}",
                    place_name=f"P+R {name}",
                    city_name=_text(p.get("city")) or "Hannover",
                    num_all=capacity,
                    source_id=self.name,
                    address=_text(p.get("address")) or None,
                    latitude=lat,
                    longitude=lon,
                    source_web_url="https://www.vmz-niedersachsen.de/region-hannover/park-und-ride/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for f in fetcher.get_json(PARK_RIDE_URL).get("features", []):
            p = f.get("properties", {})
            parking = _parking(p)
            free, stamp = parking.get("totalFree"), parking.get("timestamp")
            if not p.get("id") or free is None or not stamp or not parking.get("totalCapacity"):
                continue
            ts = datetime.fromisoformat(stamp).astimezone(timezone.utc).isoformat(timespec="seconds")
            records.append(OccupancyRecord(place_id=f"hannover-live-pr-{p['id']}", ts=ts, free=int(free)))
        return records
