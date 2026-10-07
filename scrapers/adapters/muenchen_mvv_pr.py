"""Live occupancy of Munich's park-and-ride car parks, from the MVV (Münchner
Verkehrs- und Tarifverbund) P+R map.

The MVV page "Aktuelle P+R-Belegung" is a map that loads two small JSON
documents from mvv-muenchen.de, no login:

- /index.php?type=1751357074 -- every P+R facility in the MVV area (~360)
  with its global_id ("de:9162:1460:20": the first part after "de:" is the
  municipality key, 9162 = Landeshauptstadt München), station, designation,
  coordinates and capacity.
- /?type=1751549237&parkingId=<global_id> -- the facility's detail: tariffs,
  "real_time_data" ("true" for the ~23 with sensors), "capacity",
  "available_spaces", "parking_occupancy" and "data_collection_date" (epoch
  seconds, UTC). 15 of the 32 Munich facilities report in real time.

"available_spaces" is the count we store. "parking_occupancy" (a percentage)
agrees with it for most facilities but not for Heimeranplatz, Mangfallplatz,
Moosach, Olympiazentrum and the two Westfriedhof car parks (Moosach: 124 of
282 free, which is 56% occupied, against a published 25%); the page's own
hourly forecast for the current hour equals "available_spaces", so that is
the figure the operator stands behind.

Only Munich municipality facilities (key 9162) are kept: the same endpoint
also serves Grafing, Petershausen and Agatharied, which can be added by
widening MUNICH_KEYS.

The data is a live snapshot with no history, so readings accumulate only from
the day this adapter first ran (2026-10-07). The park-and-ride company's
facilities are the city's periphery and transfer sites, not its centre: the
central garages publish no open occupancy feed (see annotations/cities/
germany_munchen).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import quote

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

BASE = "https://www.mvv-muenchen.de"
LIST_URL = BASE + "/index.php?type=1751357074"
DETAIL_URL = BASE + "/?type=1751549237&parkingId={}"
SOURCE_WEB_URL = BASE + "/plaene-bahnhoefe/park-ride/"
MUNICH_KEYS = {"9162", "09162"}


PREFIX = "mvv-pr-muenchen-"


def _place_id(global_id: str) -> str:
    return PREFIX + re.sub(r"[^a-z0-9]+", "-", global_id.lower()).strip("-")


def _global_id(place_id: str) -> str:
    """Inverse of _place_id: 'mvv-pr-muenchen-de-9162-1460-20' -> 'de:9162:1460:20'."""
    return place_id[len(PREFIX):].replace("-", ":")


def _is_munich(global_id: str) -> bool:
    parts = global_id.split(":")
    return len(parts) > 1 and parts[1] in MUNICH_KEYS


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class MuenchenMvvParkAndRideAdapter(SourceAdapter):
    name = "mvv-pr-muenchen"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _facilities(self, fetcher) -> list[tuple[dict, dict]]:
        """(list entry, detail row) for each Munich facility that reports in real time."""
        out = []
        for entry in fetcher.get_json(LIST_URL):
            gid = entry.get("global_id") or ""
            if not _is_munich(gid):
                continue
            for row in fetcher.get_json(DETAIL_URL.format(quote(gid))):
                if row.get("global_id") == gid and str(row.get("real_time_data")).lower() == "true":
                    out.append((entry, row))
        return out

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for entry, row in self._facilities(fetcher):
            if not row.get("capacity"):
                continue
            records.append(CapacityRecord(
                place_id=_place_id(row["global_id"]),
                place_name=f"P+R {row['station']} - {row['designation']}".strip(),
                city_name="München",
                num_all=int(row["capacity"]),
                source_id=self.name,
                latitude=_float(entry.get("latitude")),
                longitude=_float(entry.get("longitude")),
                place_url=row.get("link") or None,
                source_web_url=SOURCE_WEB_URL,
            ))
        return records

    def _known_rows(self, fetcher, known_garages: dict[str, str]) -> list[dict]:
        """Detail rows for the facilities already on file: one request each, without the ~360-entry
        list. The first run (nothing on file yet) falls back to discovery."""
        gids = [_global_id(pid) for pid in set(known_garages.values()) if pid.startswith(PREFIX)]
        if not gids:
            return [row for _entry, row in self._facilities(fetcher)]
        out = []
        for gid in sorted(gids):
            out += [r for r in fetcher.get_json(DETAIL_URL.format(quote(gid)))
                    if r.get("global_id") == gid and str(r.get("real_time_data")).lower() == "true"]
        return out

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for row in self._known_rows(fetcher, known_garages):
            available, stamp = row.get("available_spaces"), row.get("data_collection_date")
            if available is None or not stamp:
                continue
            ts = datetime.fromtimestamp(int(stamp), timezone.utc).isoformat(timespec="seconds")
            records.append(OccupancyRecord(place_id=_place_id(row["global_id"]), ts=ts, free=int(available)))
        return records
