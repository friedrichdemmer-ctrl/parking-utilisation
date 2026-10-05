"""Live parking for Düsseldorf, from the city's traffic-management WFS
(vtmanager.duesseldorf.de, layer "vtinfo:Parkhaeuser") -- the data behind
the city's "dynamische Verkehrsinfos" page. The open-data portal's
"Parkhäuser in Düsseldorf" dataset (opendata.duesseldorf.de) is only
static locations and links to that page for live data.

Düsseldorf used to arrive only via the defgsus community archive under
source_id "vtmanager-duesseldorf-parken", which posts a WFS GetFeature
to the same layer; this adapter takes over that source_id (its name).
Here the layer is fetched with a plain GET as GeoJSON in WGS84.

place_ids follow the archive's rule: the first two words of the name
joined by "-" ("PH 01 - Ratinger Tor" -> "PH-01", "Heerdt" -> "Heerdt"),
then archive_slug. That keeps a garage's id stable through renames (PH 11
is now "Stadtmitte", on file as "Karstadt").

Capacity is "kurzparkermax" and free = kurzparkermax - kurzparkerbelegt
(short-stay spaces; the layer has no long-stay counts). Each garage has
its own "daysecto_belegung" timestamp in true UTC (it matched the fetch
time), used as the reading time. Readings are skipped unless "status" is
1 (the only value seen alongside counts) -- garages without live counts
(PH 13, 17, 33, 34, 35, 45, 47, 52 on 2026-10-05) have no status, counts
or timestamp at all. The layer also blanks those fields for a garage
whose last count is a few minutes old (PH 10, 11, 22 and 43 vanished
between two fetches 13 minutes apart, their last counts having been ~6
minutes old), so each poll typically covers 26-30 of the ~30 live
garages; a missing garage is just skipped for that poll.

PH 29 (Friedrichstr.) and PH 37 (Hauptbahnhof-Ost) report 0 occupied
with status 1 and fresh timestamps -- apparently dead counters (their
archive history is constant too); they are kept, since nothing in the
feed distinguishes them, but are worth excluding downstream.
"""

from __future__ import annotations

from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

FEED_URL = (
    "https://vtmanager.duesseldorf.de/geoserverwfs?service=WFS&version=1.1.0&request=GetFeature"
    "&typeName=vtinfo:Parkhaeuser&srsName=EPSG:4326&outputFormat=application/json"
)
WEB_URL = "https://vtmanager.duesseldorf.de/info/?parkquartier#main"


def _place_id(name: str) -> str:
    return f"vtmanager-duesseldorf-parken-{archive_slug('-'.join(name.split()[:2]))}"


class DuesseldorfLiveAdapter(SourceAdapter):
    name = "vtmanager-duesseldorf-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _features(self, fetcher) -> list[dict]:
        return fetcher.get_json(FEED_URL).get("features", [])

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for f in self._features(fetcher):
            p = f.get("properties", {})
            name, capacity = (p.get("name") or "").strip(), p.get("kurzparkermax")
            if not name or not capacity:
                continue
            coords = (f.get("geometry") or {}).get("coordinates") or [None, None]
            address = (p.get("vti_anschrift") or "").replace("<br>", ", ").strip()
            records.append(
                CapacityRecord(
                    place_id=_place_id(name),
                    place_name=name,
                    city_name="Düsseldorf",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=address or None,
                    latitude=coords[1],
                    longitude=coords[0],
                    place_url=p.get("vti_url") or None,
                    source_web_url=WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for f in self._features(fetcher):
            p = f.get("properties", {})
            name, capacity, occupied = (p.get("name") or "").strip(), p.get("kurzparkermax"), p.get("kurzparkerbelegt")
            stamp = p.get("daysecto_belegung")
            if not name or p.get("status") != 1 or not capacity or occupied is None or not stamp:
                continue
            if not 0 <= int(occupied) <= int(capacity):
                continue
            ts = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc)
            records.append(
                OccupancyRecord(
                    place_id=_place_id(name),
                    ts=ts.replace(microsecond=0).isoformat(timespec="seconds"),
                    free=int(capacity) - int(occupied),
                )
            )
        return records
