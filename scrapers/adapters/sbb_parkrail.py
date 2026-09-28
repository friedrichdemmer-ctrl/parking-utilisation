"""Capacity for Swiss railway-station car parks (SBB P+Rail and station
parking), via the Open Data Hub's mobility API, which mirrors SBB's
parking data (origin "SBB"; see opendatahub_parking.py for the API).

Capacity-only. ~810 active, publicly accessible car parks, each with a
capacity breakdown in metadata; the "STANDARD" total is used (disabled,
reservable and charging spaces are listed separately, mostly 0) and the
town is the metadata address city. SBB does publish occupancy here, but
only as "currentEstimatedOccupancy" -- a rate SBB estimates, not a count
of cars -- so it is not stored alongside the measured occupancy from
other sources.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://mobility.api.opendatahub.com/v2/flat,node/ParkingStation?limit=-1&where=sorigin.eq.SBB,sactive.eq.true"
SOURCE_WEB_URL = "https://www.sbb.ch/en/station-services/car-parking.html"

# Station car parks already in a Swiss city feed (geneve-live), found by
# matching positions within 250 m and checking names and sizes (2026-09-28):
# the same facility, so the city's record is kept and these are left out.
EXCLUDED_CODES = {
    "SBB:16274",  # P+Rail Chêne-Bourg Gare (5 m from geneve-live "Gare de Chêne-Bourg", 487 vs 475)
    "SBB:01020",  # P+Rail Chambésy (19 m from "Gare de Chambésy")
    "SBB:01008",  # P+Rail Genève Cornavin (inside "Place de Cornavin", 831 vs 791)
    "SBB:16273",  # P+Rail Genève-Eaux-Vives (50 P+Rail spaces inside the 455-space "Gare des Eaux-Vives")
}


def _standard_capacity(md: dict) -> int:
    return sum(c.get("total") or 0 for c in md.get("capacities") or [] if c.get("categoryType") == "STANDARD")


class SbbParkrailAdapter(SourceAdapter):
    name = "sbb-parkrail"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for s in fetcher.get_json(API_URL).get("data", []):
            md = s.get("smetadata") or {}
            address = md.get("address") or {}
            city, capacity, name = (address.get("city") or "").strip(), _standard_capacity(md), (s.get("sname") or "").strip()
            if s["scode"] in EXCLUDED_CODES:
                continue
            if md.get("parkingFacilityCategory") != "CAR" or not md.get("publicAccess") or capacity <= 0 or not city or not name:
                continue
            coord = s.get("scoordinate") or {}
            street = " ".join(p for p in ((address.get("addressLine") or "").strip(), (address.get("postalCode") or "").strip()) if p)
            records.append(
                CapacityRecord(
                    place_id="sbb-parkrail-" + re.sub(r"[^a-z0-9]+", "-", s["scode"].lower()).strip("-"),
                    place_name=f"P+Rail {name}" if md.get("parkingFacilityType") == "PARK_AND_RAIL" else name,
                    city_name=city,
                    num_all=capacity,
                    source_id=self.name,
                    address=", ".join(p for p in (street, city) if p) or None,
                    latitude=coord.get("y"),
                    longitude=coord.get("x"),
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
