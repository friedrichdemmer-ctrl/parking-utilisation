"""Live parking for the City of Salzburg, via the city's open-data WFS layer
ogdsbg:parkplatz (data.stadt-salzburg.at, "Parkplätze in der Stadt
Salzburg", CC BY 4.0), fed by the parking-guidance system (Yunex Traffic).
The first Austrian live source in this project.

32 sites; about half carry a live count. FREIE_PLAETZE is text such as
"160 (52%)" -- free spaces and the free share -- or "nicht bekannt" for
sites without sensors, which are skipped. BELEGUNG_AKTUALISIERT is
Salzburg local time ("26.9.2026 12:57").

The layer's KAPAZITAET field is empty for every site, so capacities come
from CAPACITY below: parken.at's space count for the same garage (matched
by position and name), checked against the feed's own free/percentage
pairs, which pin the capacity to within a few spaces.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = (
    "https://data.stadt-salzburg.at/geodaten/wfs?service=WFS&version=1.1.0&request=GetFeature"
    "&srsName=urn:x-ogc:def:crs:EPSG:4326&outputFormat=application/json&typeName=ogdsbg:parkplatz"
)
SOURCE_WEB_URL = "https://www.data.gv.at/katalog/dataset/9087fe9a-1dd4-49a1-98b4-8a8c659eb64f"
VIENNA = ZoneInfo("Europe/Vienna")
FREE_RE = re.compile(r"^\s*(\d+)\s*\((\d+)%\)")

# layer ID -> capacity (see module docstring). Derived 2026-09-26 from 7
# samples of the feed: each "N (p%)" reading bounds the capacity to
# [N*100/(p+0.5), N*100/(p-0.5)]; the bounds were intersected across samples.
# Where parken.at's figure fell inside the bounds it is used; otherwise the
# middle of the bounds (the feed's own denominator is what its percentages,
# and so our utilisation, are relative to).
CAPACITY: dict[int, int] = {
    22051: 160,  # Akademiestraße: bounds 160-160 (parken.at "Akademieplatz" 220 does not fit)
    22153: 400,  # Linzergassengarage: bounds 400-400, parken.at 400
    22154: 700,  # Mirabell: bounds 698-702 (parken.at 680 does not fit)
    22156: 340,  # Müllner Parkplatz: bounds 339-342, not on parken.at
    22157: 67,   # Petersbrunnhof: bounds 67-200 (full while sampled), parken.at 67
    22159: 310,  # Park & Ride Süd: bounds 310-311 (parken.at 330 does not fit)
    22162: 273,  # WIFI-Garage: bounds 259-276, parken.at 273
    22163: 126,  # Bahnhofsgarage: bounds 124-129 (parken.at 150 does not fit)
    21952: 89,   # Auersperg-Garage: bounds 88-90 (parken.at 100 does not fit)
    29338: 464,  # Tiergarten Hellbrunn: bounds 464-465, not on parken.at
    29358: 67,   # Parkgarage am Paracelsusbad: bounds 67-67 (parken.at 69 does not fit)
}
# Altstadtgarage A and B were full (0 free) throughout sampling, so their
# split of parken.at's combined 1,311 spaces could not be derived; left out.


def _parse_ts(s: str | None) -> str | None:
    if not s:
        return None
    try:
        dt = datetime.strptime(s.strip(), "%d.%m.%Y %H:%M").replace(tzinfo=VIENNA)
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


class SalzburgLiveAdapter(SourceAdapter):
    name = "salzburg-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _features(self, fetcher):
        for f in fetcher.get_json(API_URL).get("features", []):
            p = f.get("properties") or {}
            if p.get("ID") in CAPACITY and (p.get("BEZEICHNUNG") or "").strip():
                yield f, p

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for f, p in self._features(fetcher):
            lon, lat = ((f.get("geometry") or {}).get("coordinates") or [None, None])[:2]
            records.append(
                CapacityRecord(
                    place_id=f"salzburg-live-{p['ID']}",
                    place_name=p["BEZEICHNUNG"].strip(),
                    city_name="Salzburg",
                    num_all=CAPACITY[p["ID"]],
                    source_id=self.name,
                    address=(p.get("ADRESSE") or "").strip() or None,
                    latitude=lat,
                    longitude=lon,
                    place_url=(p.get("URL") or "").strip() or None,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for f, p in self._features(fetcher):
            m = FREE_RE.match(p.get("FREIE_PLAETZE") or "")
            ts = _parse_ts(p.get("BELEGUNG_AKTUALISIERT"))
            if not m or not ts:
                continue
            records.append(OccupancyRecord(place_id=f"salzburg-live-{p['ID']}", ts=ts, free=int(m.group(1))))
        return records
