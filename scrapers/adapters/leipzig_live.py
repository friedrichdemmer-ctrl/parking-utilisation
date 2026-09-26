"""Leipzig: Park+Ride sites (live) and inner-city garages (capacity-only).

Park+Ride: Stadt Leipzig's open-data WFS layers (geodienste.leipzig.de,
Amt 66) -- "pr_anlage_standort_statisch" for all 15 sites' capacity and
location, and "pr_anlage_belegung_lastrecord" for the latest reading of
the 7 sites with sensors. The two layers use different id schemes, so
readings are joined to sites by name. Reading times are German local time
("26.09.2026 10:15:00"). Two sensor sites (Knauthain, Völkerschlacht-
denkmal 1) have been frozen since 2026-03-09; their stale reading is
stored once and simply never updates.

Inner-city garages: the city's "Parkhäuser in der Leipziger Innenstadt"
page lists 10 garages with capacity (Q-Park Augustusplatz, Höfe am Brühl,
the Hauptbahnhof Promenaden garages, Zoo, ...) but no coordinates and no
live data; coordinates were looked up once via OpenStreetMap and are
stored in GARAGE_COORDS. The city's parking-guidance system's live counts
are not published openly.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

WFS = (
    "https://geodienste.leipzig.de/l5/Amt66/{layer}/MapServer/WFSServer?SERVICE=WFS&VERSION=2.0.0"
    "&REQUEST=GetFeature&TYPENAMES={layer}:{layer}&outputFormat=GEOJSON&SRSNAME=EPSG:4326"
)
PR_STATIC = WFS.format(layer="pr_anlage_standort_statisch")
PR_LIVE = WFS.format(layer="pr_anlage_belegung_lastrecord")
PR_WEB_URL = "https://opendata.leipzig.de/dataset/aktuelle-belegung-park-ride-anlagen-stadt-leipzig"
GARAGES_URL = "https://www.leipzig.de/umwelt-und-verkehr/unterwegs-in-leipzig/auto-motorrad-und-reisemobile/parkhaeuser-innenstadt"
BERLIN = ZoneInfo("Europe/Berlin")

GARAGE_RE = re.compile(r"(Parkhaus [^:]{3,40}?) Anzahl Stellplätze: ([\d.]+)")
GARAGE_COORDS = {
    "Parkhaus Augustusplatz": (51.33901, 12.38089),
    "Parkhaus Am Bundesverwaltungsgericht": (51.33210, 12.36959),
    "Parkhaus Fernbus-Terminal Hbf": (51.34521, 12.38446),
    "Parkhaus Hauptbahnhof Promenaden Ost": (51.34662, 12.38413),
    "Parkhaus Hauptbahnhof Promenaden West": (51.34657, 12.37980),
    "Parkhaus Höfe am Brühl": (51.34366, 12.37669),
    "Parkhaus Martin-Luther-Ring": (51.33778, 12.36999),
    "Parkhaus Marktgalerie": (51.34026, 12.37365),
    "Parkhaus Zentralstraße": (51.33931, 12.36914),
    "Parkhaus Zoo": (51.34895, 12.37250),
}


def _slug(name: str) -> str:
    s = name.lower().replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _pr_place_id(name: str) -> str:
    return f"leipzig-pr-live-{_slug(name)}"


class LeipzigParkRideLiveAdapter(SourceAdapter):
    name = "leipzig-pr-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for f in fetcher.get_json(PR_STATIC).get("features", []):
            p = f.get("properties", {})
            name, capacity = (p.get("parkingfacilityname") or "").strip(), p.get("totalparkingcapacity")
            if not name or not capacity:
                continue
            lon, lat = ((f.get("geometry") or {}).get("coordinates") or [None, None])[:2]
            street = " ".join(v for v in (p.get("parkingfacility_str"), p.get("parkingfacility_hnr")) if v)
            records.append(
                CapacityRecord(
                    place_id=_pr_place_id(name),
                    place_name=f"P+R {name}",
                    city_name=(p.get("parkingfacility_ort") or "Leipzig").strip(),
                    num_all=int(capacity),
                    source_id=self.name,
                    address=street or None,
                    latitude=lat,
                    longitude=lon,
                    source_web_url=PR_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for f in fetcher.get_json(PR_LIVE).get("features", []):
            p = f.get("properties", {})
            name, free, stamp = (p.get("parkingfacilityname") or "").strip(), p.get("totalnumvacantparkingspaces"), p.get("phenomenontime")
            if not name or free is None or not stamp:
                continue
            ts = datetime.strptime(stamp, "%d.%m.%Y %H:%M:%S").replace(tzinfo=BERLIN).astimezone(timezone.utc)
            records.append(OccupancyRecord(place_id=_pr_place_id(name), ts=ts.isoformat(timespec="seconds"), free=int(free)))
        return records


class LeipzigGaragesAdapter(SourceAdapter):
    name = "leipzig-garages"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- no open live data, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        page = fetcher.get_text(GARAGES_URL)
        page = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", page)
        text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())
        records, seen = [], set()
        for name, capacity in GARAGE_RE.findall(text):
            if name in seen:
                continue
            seen.add(name)
            lat, lon = GARAGE_COORDS.get(name, (None, None))
            records.append(
                CapacityRecord(
                    place_id=f"leipzig-garages-{_slug(name)}",
                    place_name=name,
                    city_name="Leipzig",
                    num_all=int(capacity.replace(".", "")),
                    source_id=self.name,
                    latitude=lat,
                    longitude=lon,
                    source_web_url=GARAGES_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
