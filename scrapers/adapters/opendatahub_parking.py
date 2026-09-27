"""Live parking for South Tyrol (Alto Adige), via the Open Data Hub's
mobility API (mobility.api.opendatahub.com, run by NOI Techpark for the
province; CC0). Covers Bolzano, Merano, Bressanone, Brunico, Caldaro, Val
Gardena and other towns, from several operators (the city's own system
"FAMAS", SKIDATA garages, Merano's municipal car parks, the Val Gardena
consortium).

Each ParkingStation carries its capacity in metadata and a "free"
measurement with a UTC timestamp, refreshed every 2-10 minutes. Left out:
- origin "SBB" (Swiss railway car parks, no occupancy) and "A22"
  (motorway service areas);
- stations with capacity 0 or -1 (placeholders; their "free" is then a
  9999 sentinel);
- stations with no municipality in their metadata.
The Trento/Rovereto stations (origin "FBK") stopped reporting in 2023 and
drop out through the usual freshness checks rather than a filter here.

Two different stations can share a name (Bressanone's "Parcheggio Via
Dante" appears twice), so place_ids use the station code.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API = "https://mobility.api.opendatahub.com/v2/flat,node/ParkingStation"
WHERE = "where=sactive.eq.true,sorigin.nin.(SBB,A22)"
STATIONS_URL = f"{API}?limit=-1&{WHERE}"
FREE_URL = f"{API}/free/latest?limit=-1&{WHERE}&select=scode,mvalue,mvalidtime"
SOURCE_WEB_URL = "https://opendatahub.com/datasets/mobility/"

# metadata "municipality" -> Italian town name ("Italian - German" is the
# usual form, but a few are German-first)
MUNICIPALITY = {
    "Meran - Merano": "Merano",
    "Merano - Meran": "Merano",
    "Marling - Marlengo": "Marlengo",
    "Bressanone": "Bressanone",
    "valgardena": "Val Gardena",
}


def _city(municipality: str | None) -> str | None:
    if not municipality:
        return None
    m = municipality.strip()
    return MUNICIPALITY.get(m) or re.split(r"\s+[-–]\s+", m)[0].strip()


def _place_id(scode: str) -> str:
    return "odh-" + re.sub(r"[^a-z0-9]+", "-", scode.lower()).strip("-")


def _utc(ts: str) -> str:
    # "2026-09-27 06:35:00.000+0000"
    return ts[:10] + "T" + ts[11:19] + "+00:00"


class OpenDataHubParkingAdapter(SourceAdapter):
    name = "opendatahub-parking"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for s in fetcher.get_json(STATIONS_URL).get("data", []):
            md = s.get("smetadata") or {}
            capacity, city, name = md.get("capacity"), _city(md.get("municipality")), (s.get("sname") or "").strip()
            if not isinstance(capacity, int) or capacity <= 0 or not city or not name:
                continue
            coord = s.get("scoordinate") or {}
            records.append(
                CapacityRecord(
                    place_id=_place_id(s["scode"]),
                    place_name=name,
                    city_name=city,
                    num_all=capacity,
                    source_id=self.name,
                    address=(md.get("mainaddress") or md.get("address") or None),
                    latitude=coord.get("y"),
                    longitude=coord.get("x"),
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        # only stations kept by fetch_capacity (placeholder-capacity stations
        # still report "free" and would otherwise land without a lots_meta
        # row). Rebuilt from the station list rather than known_garages,
        # which is keyed by name and would merge same-named stations.
        on_file = {c.place_id for c in self.fetch_capacity(fetcher)}
        records = []
        for m in fetcher.get_json(FREE_URL).get("data", []):
            free, ts, place_id = m.get("mvalue"), m.get("mvalidtime"), _place_id(m["scode"])
            if place_id not in on_file or not isinstance(free, (int, float)) or not ts or free < 0 or free >= 9999:
                continue
            records.append(OccupancyRecord(place_id=place_id, ts=_utc(ts), free=int(free)))
        return records
