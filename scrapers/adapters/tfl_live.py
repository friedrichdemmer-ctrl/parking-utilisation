"""Transport for London's station car parks, via the TfL Unified API's
static place list (/Place/Type/CarPark).

Capacity-only. TfL's matching occupancy endpoint (/Occupancy/CarPark)
has returned HTTP 500 for years -- TfL staff have said the source data
was lost when the car parks' operator changed -- so fetch_occupancy is a
no-op. 58 London Underground station car parks. A few (Epping, Chesham,
Watford, Chorleywood...) lie outside Greater London: each site's nearest
postcode is looked up via postcodes.io, sites in the London region get
city "London", and the rest use the station's own name as the town.
"""

from __future__ import annotations

import re

from scrapers import uk_postcodes
from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://api.tfl.gov.uk/Place/Type/CarPark"

STATION_SUFFIX = re.compile(r"\s*Stn\s*\(LUL\)\s*$", re.I)


class TflLiveAdapter(SourceAdapter):
    name = "tfl-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        places = fetcher.get_json(API_URL)
        records = []
        for p in places:
            props = {a.get("key"): a.get("value") for a in p.get("additionalProperties", [])}
            capacity = (props.get("NumberOfSpaces") or "").strip()
            if props.get("Open") != "True" or not capacity.isdigit():
                continue
            lat, lon = p.get("lat"), p.get("lon")
            name = (p.get("commonName") or "").strip()
            near = uk_postcodes.nearest(fetcher, lat, lon) if lat and lon else None
            if near is None or near.get("region") == "London":
                city = "London"
            else:
                city = STATION_SUFFIX.sub("", name)
            address = ", ".join(
                v.strip()
                for v in (props.get("Address1"), props.get("Address2"), props.get("Address3"), props.get("PostCode"))
                if v and v.strip()
            )
            records.append(
                CapacityRecord(
                    place_id=f"tfl-live-{p['id']}",
                    place_name=name,
                    city_name=city,
                    num_all=int(capacity),
                    source_id=self.name,
                    address=address or None,
                    latitude=lat,
                    longitude=lon,
                    source_web_url=API_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
