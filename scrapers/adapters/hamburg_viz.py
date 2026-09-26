"""Hamburg garages via the city's official WFS feed (geodienste.hamburg.de),
published by the Behörde für Verkehr und Mobilitätswende (BVM) under
Datenlizenz Deutschland Namensnennung 2.0.

The underlying dataset spans the whole HVV commuter-rail region (it even
includes small Lower Saxony towns' P+R lots via datenherkunft "HVV"), not
just Hamburg city. We filter to datenherkunft == "BWVI_V", the subset
actually sourced from Hamburg's own Parkleitsystem (city parking guidance
system) -- this is also the subset that carries live occupancy, so the
filter both keeps city_name="Hamburg" honest and happens to line up with
where the real data is.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

WFS_URL = (
    "https://geodienste.hamburg.de/wfs_parkhaeuser"
    "?Service=WFS&Version=2.0.0&Request=GetFeature"
    "&typeNames=de.hh.up:parkhaeuser&outputFormat=application%2Fgeo%2Bjson&srsName=EPSG:4326"
)


# Features that report a fresh "received" time every cycle but the same "frei"
# value forever: each had exactly one value across all ~2,000 readings from
# 2026-08-13 (when collection started) to 2026-09-26, e.g. Rödingsmarkt
# always 700, Bahnhof Altona always 100 (= its capacity). Their occupancy
# is not written; capacity records are unaffected.
DEAD_FEATURE_IDS = {
    "DE.HH.UP_PARKHAEUSER_10002",  # Am Hauptbahnhof
    "DE.HH.UP_PARKHAEUSER_10006",  # Parkhaus Stadthöfe (Bleichenhof)
    "DE.HH.UP_PARKHAEUSER_10016",  # Große Reichenstraße
    "DE.HH.UP_PARKHAEUSER_10018",  # Hafentor
    "DE.HH.UP_PARKHAEUSER_10021",  # Holzdamm (ibis)
    "DE.HH.UP_PARKHAEUSER_10027",  # Madison
    "DE.HH.UP_PARKHAEUSER_10031",  # Michel-Garage
    "DE.HH.UP_PARKHAEUSER_10038",  # Rödingsmarkt
    "DE.HH.UP_PARKHAEUSER_10045",  # Bahnhof Altona
    "DE.HH.UP_PARKHAEUSER_10093",  # Harburg Arcaden
    "DE.HH.UP_PARKHAEUSER_10098",  # Marktkauf-Center Harburg
}


def _slug(name: str) -> str:
    s = name.lower()
    s = s.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


def _parse_received(s: str | None) -> str | None:
    # e.g. "13.08.2026, 16:40" -- Europe/Berlin local time, no offset given by the source
    if not s:
        return None
    try:
        dt = datetime.strptime(s, "%d.%m.%Y, %H:%M").replace(tzinfo=ZoneInfo("Europe/Berlin"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


class HamburgVizAdapter(SourceAdapter):
    name = "hamburg-viz-parkhaeuser"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60  # source itself refreshes ~every 5 min; 30 min is plenty for our use
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        data = fetcher.get_json(WFS_URL)
        for feat in data.get("features", []):
            props = feat["properties"]
            if props.get("datenherkunft") != "BWVI_V":
                continue
            if not (props.get("name") or "").strip():
                continue
            yield feat, props

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for feat, props in self._rows(fetcher):
            name = props["name"].strip()
            address_parts = [(props.get("strasse") or "").strip(), (props.get("hausnr") or "").strip()]
            address = " ".join(p for p in address_parts if p) or None
            records.append(
                CapacityRecord(
                    place_id=f"hamburg-viz-{feat['id']}-{_slug(name)}",
                    place_name=name,
                    city_name="Hamburg",
                    num_all=props.get("stellplaetze_gesamt"),
                    source_id=self.name,
                    address=address,
                    place_url=(props.get("link") or "").strip() or None,
                    source_web_url="https://geodienste.hamburg.de/wfs_parkhaeuser",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for feat, props in self._rows(fetcher):
            if props.get("situation") not in ("frei", "besetzt") or feat["id"] in DEAD_FEATURE_IDS:
                continue
            free = props.get("frei")
            ts = _parse_received(props.get("received"))
            if free is None or ts is None:
                continue
            name = props["name"].strip()
            records.append(
                OccupancyRecord(place_id=f"hamburg-viz-{feat['id']}-{_slug(name)}", ts=ts, free=int(free))
            )
        return records
