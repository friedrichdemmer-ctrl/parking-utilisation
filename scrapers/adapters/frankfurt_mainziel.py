"""Frankfurt am Main garages via mainziel.de, the city's official mobility
information platform (TLS cert issued to "Stadt Frankfurt am Main").

The formal open-data catalog entry for this dataset (offenedaten.frankfurt.de
/dataset/parkdaten-dynamisch) was unreachable during research -- a TLS
hostname mismatch plus repeated 503s, most likely that specific subdomain
having infra trouble rather than the data being unavailable. This feed is
the same underlying GeoServer WFS pattern already verified for Hamburg and
Berlin's official portals, served unauthenticated straight to the city's own
public traffic map, but we don't have as clean a paper trail on licensing
here as we do for Hamburg's explicit Datenlizenz Deutschland grant.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

WFS_URL = (
    "https://mainziel.de/geoserver/vtinfo/ows"
    "?service=WFS&version=2.0.0&request=GetFeature"
    "&typeName=vtinfo:Parkhaeuser&outputFormat=json"
)


def _slug(name: str) -> str:
    s = name.lower()
    s = s.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class FrankfurtMainzielAdapter(SourceAdapter):
    name = "frankfurt-mainziel"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(WFS_URL)
        records = []
        for feat in data.get("features", []):
            props = feat["properties"]
            name = (props.get("name") or "").strip()
            if not name:
                continue
            address = ((props.get("vti_anschrift") or "").split("<br>")[0]).strip() or None
            records.append(
                CapacityRecord(
                    place_id=f"frankfurt-mainziel-{feat['id']}-{_slug(name)}",
                    place_name=name,
                    city_name="Frankfurt",
                    num_all=props.get("stellplaetzekurzparker_statisch"),
                    source_id=self.name,
                    address=address,
                    source_web_url="https://mainziel.de/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        data = fetcher.get_json(WFS_URL)
        records = []
        for feat in data.get("features", []):
            props = feat["properties"]
            name = (props.get("name") or "").strip()
            free = props.get("kurzparkerfrei")
            ts = props.get("daysecto_belegung")
            if not name or free is None or not ts:
                continue
            records.append(
                OccupancyRecord(place_id=f"frankfurt-mainziel-{feat['id']}-{_slug(name)}", ts=ts, free=int(free))
            )
        return records
