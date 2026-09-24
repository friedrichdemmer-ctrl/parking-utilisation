"""Liège's off-street car parks, via Wallonia's open data portal
(odwb.be), dataset "parkings-voitures-hors-voirie".

Capacity-only -- no live occupancy field or timestamp exists in this
register, just name/address/capacity/operator per garage, "last_modified"
being an edit date rather than a live reading. Found via the same
country-wide search that found interparking_belgium.py; this one
comes from Wallonia's own regional portal rather than the national
transportdata.be platform. All 33 rows are in Liège -- the only city
this dataset covers -- closing a real gap, since Liège had zero prior
coverage in this project (a previous pass this session found Liège's
CommuniThings/FIWARE sensor network but no public API for it).

No Q-Park garage exists in this register (operators present: Bepark,
Effia, Indigo, Interparking, SNCB, and several small independents).
A couple of entries ("Parking Cité administrative", "Parking Saint-
Georges") likely refer to the same physical garages as two entries in
interparking_belgium.py's national feed ("Cité", "Saint Georges") --
kept as a separate source_id rather than reconciled, the same tradeoff
documented in bordeaux_metropole_live.py for BNLS overlaps.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://www.odwb.be/api/explore/v2.1/catalog/datasets/parkings-voitures-hors-voirie/records?limit=100"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[éèê]", "e", s)
    s = re.sub(r"[àâ]", "a", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class LiegeHorsVoirieAdapter(SourceAdapter):
    name = "liege-hors-voirie"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(API_URL)
        records = []
        for r in data.get("results", []):
            name = (r.get("title") or "").strip()
            capacity = r.get("available_spaces")
            if not name or not capacity:
                continue
            point = r.get("geo_point_2d") or {}
            address = f"{r.get('street_name', '')} {r.get('house_number', '')}".strip()
            records.append(
                CapacityRecord(
                    place_id=f"liege-hors-voirie-{_slug(name)}-{r.get('gid')}",
                    place_name=name,
                    city_name="Liège",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=address or None,
                    latitude=point.get("lat"),
                    longitude=point.get("lon"),
                    place_url=r.get("website"),
                    source_web_url="https://www.odwb.be/explore/dataset/parkings-voitures-hors-voirie/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
