"""Berlin garages/parking lots via the Verkehrsinformationszentrale (VIZ)
Berlin's official GeoServer WFS feed, the same data source behind the
"Parkhäuser und Parkplätze" layer on viz.berlin.de.

Capacity is populated for essentially every facility (a real Senate-run
catalog, not guesswork). A handful of entries also carry a live occupancy
percentage ("auslastung") with a timestamp -- but on inspection every one of
those timestamps was frozen at the same moment days in the past, so that
part of the feed is not reliably live. fetch_occupancy() is left returning
nothing until that's confirmed to actually update; this adapter exists for
the capacity catalog only, for now.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

WFS_URL = (
    "https://api.viz.berlin.de/geoserver/mdh/ows"
    "?service=WFS&version=2.0.0&request=GetFeature"
    "&typeName=mdh:parken_be_belegung&outputFormat=application/json"
)


def _slug(name: str) -> str:
    s = name.lower()
    s = s.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class BerlinVizAdapter(SourceAdapter):
    name = "viz-berlin-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 24 * 3600
    capacity_interval_seconds = 7 * 24 * 3600  # official catalog, doesn't need frequent resync

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(WFS_URL)
        records = []
        for feat in data.get("features", []):
            props = feat["properties"]
            name = (props.get("name") or "").strip()
            if not name:
                continue
            place_id = f"viz-berlin-{props['parkhaus_id']}-{_slug(name)}"
            coords = (feat.get("geometry") or {}).get("coordinates")
            records.append(
                CapacityRecord(
                    place_id=place_id,
                    place_name=name,
                    city_name="Berlin",
                    num_all=props.get("capacity"),
                    source_id=self.name,
                    address=(props.get("addresse") or "").strip() or None,
                    source_web_url="https://viz.berlin.de/verkehr-in-berlin/parken/parkhauser-und-parkplatze/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
