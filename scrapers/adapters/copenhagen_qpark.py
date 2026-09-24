"""Q-Park's Copenhagen garages, via the City of Copenhagen's own WFS parking
layer (published as open data through opendata.dk, "Parkeringshuse").

Denmark's first Q-Park source in this project. Found while sweeping
Denmark for Q-Park coverage: the two other Danish leads that looked
promising turned out dead (Aarhus's own "Parkeringshuse i Aarhus" open
dataset has been stuck since 2022-12-13, and its municipal GIS map
404s) or off-shape for this schema (Aarhus's live sensor dataset is
on-street segments, not garages).

Capacity-only, like db_bahnpark.py -- this WFS layer is a location/
capacity register for garages *within the municipality's payment zone*,
not a live occupancy feed (no free-space field anywhere in the schema).
Q-Park operators aren't tagged as such systematically -- most entries'
free-text "bemaerkning" remark names a different operator (Jeudan,
Europark, OnePark, Center for Parkering) or none at all -- so only the
two rows whose remark explicitly says "Q-park" are trusted as Q-Park's,
rather than guessing from address alone. This deliberately leaves out
"Nørreport" and "Vesterport", which Q-Park's own site lists for
Copenhagen but which don't appear anywhere in this municipal layer
(privately operated, outside what the city itself tracks).
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

WFS_URL = (
    "https://wfs-kbhkort.kk.dk/k101/ows"
    "?service=WFS&version=1.0.0&request=GetFeature&typeName=k101:p_hus&outputFormat=json&SRSNAME=EPSG:4326"
)


def _slug(name: str) -> str:
    s = name.lower()
    s = s.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class CopenhagenQParkAdapter(SourceAdapter):
    name = "copenhagen-qpark"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(WFS_URL)
        records = []
        for feat in data.get("features", []):
            props = feat.get("properties", {})
            remark = (props.get("bemaerkning") or "").lower()
            if "q-park" not in remark:
                continue
            capacity = props.get("antal_pladser")
            if not capacity:
                continue
            street = (props.get("vejnavn") or "").strip()
            house_no = (props.get("husnr") or "").strip()
            name = f"{street} {house_no}".strip()
            lon, lat = (feat.get("geometry") or {}).get("coordinates", [None, None])
            records.append(
                CapacityRecord(
                    place_id=f"copenhagen-qpark-{_slug(name)}",
                    place_name=name,
                    city_name="Copenhagen",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=f"{street} {house_no}, {props.get('postdistrikt') or ''}".strip(", "),
                    latitude=lat,
                    longitude=lon,
                    source_web_url="https://www.opendata.dk/city-of-copenhagen/parkeringshuse",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
