"""Park-and-ride car parks across Finland, via Fintraffic's national
parking API (parking.fintraffic.fi/api/v1, the LIIPI system that HSL ran
for the Helsinki region until May 2024). The first Finnish source in this
project.

- /facilities: every facility (~780, incl. bicycle parks) with its built
  capacity per vehicle type. Only CAR facilities that are not INACTIVE
  are kept.
- /hubs: stations/hubs with an address and the facilities they group.
  Facilities carry no town themselves, so the town comes from their hub,
  or for the few in no hub (e.g. Tampere's Hiedanranta) from the nearest
  hub within 15 km; facilities with no hub that close are left out.
- /utilizations: live "spacesAvailable" per facility and usage (park and
  ride, commercial), each with the capacity it counts against and a
  timestamp with offset. About 40 facilities report.

The counted capacity can be well below the built one (Tapiola Park is
built for 2,049 but counts 1,200 commercial + 365 park-and-ride), and the
free counts are relative to the counted spaces. So for facilities that
report, capacity is the sum of their CAR utilisation capacities and free
the sum of their spacesAvailable; for the rest it is the built capacity.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API = "https://parking.fintraffic.fi/api/v1"
SOURCE_WEB_URL = "https://parking.fintraffic.fi/"


def _name(n: dict | None) -> str:
    n = n or {}
    return (n.get("fi") or n.get("en") or n.get("sv") or "").strip()


def _centroid(location: dict | None) -> tuple[float | None, float | None]:
    bbox = (location or {}).get("bbox")
    if not bbox or len(bbox) != 4:
        return None, None
    return (bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2


NEAREST_HUB_MAX_KM = 15


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    dlat, dlon = a[0] - b[0], (a[1] - b[1]) * math.cos(math.radians(a[0]))
    return 111.2 * math.hypot(dlat, dlon)


def _counted(utilizations: list[dict]) -> dict[int, tuple[int, int, str]]:
    """facilityId -> (counted capacity, free, latest timestamp) over its CAR rows."""
    cap, free, ts = defaultdict(int), defaultdict(int), {}
    for u in utilizations:
        if u.get("capacityType") != "CAR" or not isinstance(u.get("capacity"), int) or u["capacity"] <= 0:
            continue
        fid = u["facilityId"]
        cap[fid] += u["capacity"]
        free[fid] += int(u.get("spacesAvailable") or 0)
        ts[fid] = max(ts.get(fid, ""), u.get("timestamp") or "")
    return {fid: (cap[fid], free[fid], ts[fid]) for fid in cap}


class FintrafficParkingAdapter(SourceAdapter):
    name = "fintraffic-parking"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        facilities = fetcher.get_json(f"{API}/facilities").get("results", [])
        town, hub_points = {}, []
        for h in fetcher.get_json(f"{API}/hubs").get("results", []):
            # a few hub towns are compound ("Helsinki/Espoo", "Espoo (Kauniainen)")
            t = re.split(r"\s*[/(]", _name(((h.get("address") or {}).get("city"))))[0].strip()
            if not t:
                continue
            for fid in h.get("facilityIds") or []:
                town.setdefault(fid, t)
            coords = (h.get("location") or {}).get("coordinates")
            if coords and len(coords) == 2:
                hub_points.append(((coords[1], coords[0]), t))
        counted = _counted(fetcher.get_json(f"{API}/utilizations"))
        records = []
        for f in facilities:
            fid, built = f.get("id"), (f.get("builtCapacity") or {}).get("CAR", 0)
            if f.get("type") != "CAR" or f.get("status") == "INACTIVE" or not built:
                continue
            lat, lon = _centroid(f.get("location"))
            if fid not in town and lat is not None and hub_points:
                dist, t = min((_km((lat, lon), p), t) for p, t in hub_points)
                if dist <= NEAREST_HUB_MAX_KM:
                    town[fid] = t
            if fid not in town:
                continue
            records.append(
                CapacityRecord(
                    place_id=f"fintraffic-{fid}",
                    place_name=_name(f.get("name")),
                    city_name=town[fid],
                    num_all=counted[fid][0] if fid in counted else int(built),
                    source_id=self.name,
                    latitude=lat,
                    longitude=lon,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for fid, (_cap, free, ts) in _counted(fetcher.get_json(f"{API}/utilizations")).items():
            if not ts:
                continue
            utc = datetime.fromisoformat(ts).astimezone(timezone.utc).isoformat(timespec="seconds")
            records.append(OccupancyRecord(place_id=f"fintraffic-{fid}", ts=utc, free=free))
        return records
