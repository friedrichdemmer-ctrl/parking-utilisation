"""Zürich public garages and live parking guidance (Switzerland).

Capacity: Stadt Zürich's open-data layer "Öffentlich zugängliche
Parkhäuser" (WFS poi_parkhaus_view) -- 136 public garages with name,
address, public spaces and coordinates. Occupancy: the Parkleitsystem
Zürich RSS feed (pls-zh.ch), whose items carry "open / <free>" and a GMT
pubDate. The two are joined on each garage's pls-zh.ch link ("pid=..."),
which the WFS layer records as link_pls; 34 of the feed's 36 items match.
The other two are surface car parks the layer doesn't list and are
skipped. Readings for garages not "open" are skipped, since a closed
garage would read as full.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

WFS_URL = (
    "https://www.ogd.stadt-zuerich.ch/wfs/geoportal/Oeffentlich_zugaengliche_Parkhaeuser"
    "?SERVICE=WFS&REQUEST=GetFeature&VERSION=1.1.0&TYPENAME=poi_parkhaus_view&outputFormat=GeoJSON&srsName=EPSG:4326"
)
RSS_URL = "https://www.pls-zh.ch/plsFeed/rss"
SOURCE_WEB_URL = "https://data.stadt-zuerich.ch/dataset/geo_oeffentlich_zugaengliche_parkhaeuser"

PID_RE = re.compile(r"pid=([^&\"<\s]+)")
ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)


def _tag(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", block, re.S)
    return html.unescape(m.group(1)).strip() if m else ""


class ZuerichLiveAdapter(SourceAdapter):
    name = "zuerich-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _garages(self, fetcher) -> list[dict]:
        return fetcher.get_json(WFS_URL).get("features", [])

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for f in self._garages(fetcher):
            p = f.get("properties", {})
            poi_id, name, capacity = p.get("poi_id"), (p.get("name") or "").strip(), p.get("anzahl_oeffentliche_pp")
            if not poi_id or not name or not capacity:
                continue
            lon, lat = ((f.get("geometry") or {}).get("coordinates") or [None, None])[:2]
            records.append(
                CapacityRecord(
                    place_id=f"zuerich-live-{poi_id}",
                    place_name=name,
                    city_name="Zürich",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=(p.get("adresse") or "").strip() or None,
                    latitude=lat,
                    longitude=lon,
                    place_url=p.get("link_pls") or None,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        by_pid = {}
        for f in self._garages(fetcher):
            p = f.get("properties", {})
            m = PID_RE.search(p.get("link_pls") or "")
            if m and p.get("poi_id") and p.get("anzahl_oeffentliche_pp"):
                by_pid[m.group(1)] = p["poi_id"]
        records = []
        for item in ITEM_RE.findall(fetcher.get_text(RSS_URL)):
            m = PID_RE.search(_tag(item, "link"))
            status, _, free = _tag(item, "description").partition("/")
            if not m or m.group(1) not in by_pid or status.strip() != "open" or not free.strip().isdigit():
                continue
            ts = parsedate_to_datetime(_tag(item, "pubDate")).astimezone(timezone.utc)
            records.append(
                OccupancyRecord(
                    place_id=f"zuerich-live-{by_pid[m.group(1)]}",
                    ts=ts.isoformat(timespec="seconds"),
                    free=int(free.strip()),
                )
            )
        return records
