"""Heidelberg's live parking feed, via its "datenplattform" (Digital-Agentur
Heidelberg GmbH's open data platform for the city).

api.parkendd.de lists Heidelberg as "active_support" and this project's
legacy collector.py has been polling it for six weeks, but every lot it
returns turned out frozen at one value the whole time (api.parkendd.de
itself is stale, "last_downloaded" reading 2024-08-01) -- and the URL that
old feed pointed to now just 301-redirects to a rebuilt site (parken.
heidelberg.de), garage line-up changed since (e.g. old "Crowne Plaza" is now
"Hilton", capacities updated). Found the real static/dynamic JSON endpoints
by pulling the new site's JS bundle rather than the network tab, since the
requests fire from inline <link rel=preload>-style resource hints the
browser tooling here didn't surface as an XHR entry -- confirmed via
performance.getEntriesByType('resource') in-page instead.

Two endpoints, joined on parkingSiteId: /static has name/capacity/address/
coordinates (rarely changes), /dynamic has current free-space counts with a
per-record timestamp. Garages under maintenance ("Störung" in the UI) are
simply absent from /dynamic rather than present with a null reading -- same
filter (`free is None`) handles both that and the couple of entries present
with a null freeSpotNumber (e.g. P26 P+R Kirchheim was seen with nulls
across the board despite appearing "Offen").
"""

from __future__ import annotations

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

STATIC_URL = "https://parking.datenplattform.heidelberg.de/static"
DYNAMIC_URL = "https://parking.datenplattform.heidelberg.de/dynamic"


class HeidelbergLiveAdapter(SourceAdapter):
    name = "heidelberg-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(STATIC_URL)
        records = []
        for item in data:
            site_id = item.get("parkingSiteId")
            name = (item.get("name") or "").strip()
            total = item.get("totalSpotNumber")
            if not site_id or not name or not total:
                continue
            address_parts = [item.get("streetAddress"), item.get("addressLocality")]
            address = ", ".join(p for p in address_parts if p) or None
            lat = item.get("lat")
            lon = item.get("lon")
            records.append(
                CapacityRecord(
                    place_id=f"heidelberg-live-{site_id}",
                    place_name=name,
                    city_name="Heidelberg",
                    num_all=int(total),
                    source_id=self.name,
                    address=address,
                    latitude=float(lat) if lat else None,
                    longitude=float(lon) if lon else None,
                    source_web_url="https://parken.heidelberg.de/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        data = fetcher.get_json(DYNAMIC_URL)
        records = []
        for item in data:
            site_id = item.get("parkingSiteId")
            free = item.get("freeSpotNumber")
            ts = item.get("observationDateTime")
            if not site_id or free is None or not ts:
                continue
            records.append(OccupancyRecord(place_id=f"heidelberg-live-{site_id}", ts=ts, free=int(free)))
        return records
