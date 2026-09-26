"""Live parking for Konstanz, via the city's geoportal layer
"Parkplaetze_Parkleitsystem" (services.gis.konstanz.digital, listed on
the Open Data BW portal as "Parkdaten Konstanz").

Konstanz used to arrive only via the defgsus community archive under
source_id "konstanz-parken", where 6 of its 10 garages had gone stale and
none had a capacity. This layer carries capacity, the parking-guidance
system's free count and an update time for 11 sites, so this adapter
takes over that source_id (sync_archive.py skips it from now on) and
fills in the missing capacities, which also makes the older archive
history usable. The city's separate "Parkhausbelegung" dataset only
points to Mobilithek and is not open; this layer is.

The layer's "updated" epoch is off by the German UTC offset: watching a
refresh land at 08:05 UTC showed a raw value of 06:03 (the server treats a
UTC value as local and converts it again), so the offset is added back.

Readings are skipped for sites marked not open ("opening_s" != "ja") --
a closed garage reports 0 free, which would look full -- and for sites
with no update time (the two university car parks have none).
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

BERLIN = ZoneInfo("Europe/Berlin")
LAYER_URL = "https://services.gis.konstanz.digital/geoportal/rest/services/Fachdaten/Parkplaetze_Parkleitsystem/MapServer/0"
API_URL = LAYER_URL + "/query?where=1%3D1&outFields=*&outSR=4326&f=json"

LEGACY_NAMES = {
    "Parkhaus LAGO": "Lago",
    "Parkhaus Fischmarkt": "Fischmarkt",
    "Parkhaus Marktstätte": "Marktstätte",
    "Parkhaus Augustiner / Karstadt": "Augustiner / Karstadt",
    "Parkhaus Benediktinerplatz": "Benediktiner",
    "Tiefgarage Seerheincenter": "Seerheincenter",
    "Parkhaus Altstadt": "Altstadt",
    "Parkplatz Döbele": "Döbele",
}


def _place_id(name: str) -> str:
    return f"konstanz-parken-{archive_slug(LEGACY_NAMES.get(name, name))}"


class KonstanzLiveAdapter(SourceAdapter):
    name = "konstanz-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _sites(self, fetcher) -> list[dict]:
        return [f.get("attributes", {}) for f in fetcher.get_json(API_URL).get("features", [])]

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for a in self._sites(fetcher):
            name, capacity = (a.get("name") or "").strip(), a.get("max_cap")
            if not name or not capacity:
                continue
            records.append(
                CapacityRecord(
                    place_id=_place_id(name),
                    place_name=name,
                    city_name="Konstanz",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=(a.get("address") or "").strip() or None,
                    latitude=a.get("lat"),
                    longitude=a.get("lon"),
                    place_url=a.get("public_url") or None,
                    source_web_url=LAYER_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for a in self._sites(fetcher):
            name, free, updated = (a.get("name") or "").strip(), a.get("real_fcap"), a.get("updated")
            if not name or free is None or not updated or not a.get("max_cap") or a.get("opening_s") != "ja":
                continue
            raw = datetime.fromtimestamp(updated / 1000, tz=timezone.utc)
            ts = (raw + BERLIN.utcoffset(raw.replace(tzinfo=None))).isoformat(timespec="seconds")
            records.append(OccupancyRecord(place_id=_place_id(name), ts=ts, free=int(free)))
        return records
