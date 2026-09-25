"""Tyne & Wear and Durham car parks (England), via Newcastle University's
Urban Observatory, which mirrors the region's UTMC car-park feeds.

Capacity-only. The mirror's link to the UTMC feeds is marked inactive
and no occupancy readings were found anywhere from 2022 to today, so only
each car park's total-spaces figure is used. The live feed itself is
netraveldata.co.uk, which needs an account; its registration form was
failing for the user, so this is the stopgap until that account exists.
Because the mirror stopped updating, some sites may since have
changed or closed.

101 car parks across Newcastle, Gateshead, North and South Tyneside,
Sunderland and Durham city, including one Q-Park (Stowell Street). A
"Test Car Park" row is dropped. The mirror has no coordinates: rows whose
address ends in a postcode are geocoded via postcodes.io, and the ~28
without one use coordinates looked up once via OpenStreetMap (keyed by
the stable UTMC site id). "St. George's" couldn't be placed reliably and
has none. Metrocentre's zones share the shopping centre's position.
"""

from __future__ import annotations

import re

from scrapers import uk_postcodes
from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = 'https://api.newcastle.urbanobservatory.ac.uk/api/v2/sensors/entity?metric=%22Occupied%20spaces%22&pageSize=100&page={page}'
SOURCE_WEB_URL = "https://newcastle.urbanobservatory.ac.uk/"

POSTCODE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\s*$", re.I)

EXCLUDED_SITE_IDS = {"CP_GH_TEST"}

# (lat, lon, city) for sites whose address carries no postcode.
NO_POSTCODE_SITES = {
    "PR001": (55.00998, -1.57849, "Newcastle upon Tyne"),
    "PR003": (55.01392, -1.67807, "Newcastle upon Tyne"),
    "PR004": (54.94608, -1.42261, "South Tyneside"),
    "PR005": (54.95679, -1.48510, "South Tyneside"),
    "PR007": (55.01442, -1.66592, "Newcastle upon Tyne"),
    "PR009": (55.01184, -1.62204, "Newcastle upon Tyne"),
    "PR012": (55.03321, -1.51956, "North Tyneside"),
    "CP0043": (54.96983, -1.60952, "Newcastle upon Tyne"),
    "CP0050": (54.97525, -1.61517, "Newcastle upon Tyne"),
    "CP_NC_CLARRD": (54.98249, -1.61816, "Newcastle upon Tyne"),
    "CP_NC_GRAING": (54.96960, -1.62243, "Newcastle upon Tyne"),
    "CP_NC_MANORS": (54.97220, -1.60680, "Newcastle upon Tyne"),
    "CP_NC_STGEOR": (None, None, "Newcastle upon Tyne"),
    "CP_GH_MCCOAC": (54.95716, -1.67258, "Gateshead"),
    "CP_GH_MCGRNZ": (54.95716, -1.67258, "Gateshead"),
    "CP_GH_MCREDZ": (54.95716, -1.67258, "Gateshead"),
    "CP_GH_QUARRY": (54.96603, -1.59719, "Gateshead"),
    "VMSLCP003": (54.95143, -1.55495, "Gateshead"),
    "DURCPDW0007": (54.79563, -1.52236, "Durham"),
    "DURCPDW0008": (54.76160, -1.57947, "Durham"),
    "DURCPDW0009": (54.79231, -1.60097, "Durham"),
    "DURCPDW0010": (54.79563, -1.52236, "Durham"),
    "DURCPNPA0006": (54.77683, -1.57361, "Durham"),
    "DURCPORB0001": (54.77907, -1.57844, "Durham"),
    "DURCPORB0002": (54.77908, -1.57499, "Durham"),
    "DURCPORB0003": (54.78130, -1.57248, "Durham"),
    "DURCPORB0004": (54.78172, -1.57620, "Durham"),
    "DURCPORB0005": (54.77696, -1.57827, "Durham"),
}


def _district(result: dict) -> str | None:
    d = result.get("admin_district")
    if isinstance(d, list):
        d = d[0] if d else None
    return "Durham" if d == "County Durham" else d


class TyneWearLiveAdapter(SourceAdapter):
    name = "tyne-wear-live"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def _entities(self, fetcher) -> list[dict]:
        entities, page, page_count = [], 1, 1
        while page <= page_count:
            data = fetcher.get_json(API_URL.format(page=page))
            entities += data.get("items", [])
            page_count = data.get("pagination", {}).get("pageCount", 1)
            page += 1
        return entities

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for e in self._entities(fetcher):
            feed = next((f for f in e.get("feed", []) if f.get("metric") == "Occupied spaces"), None)
            if not feed or not feed.get("brokerage"):
                continue
            site_id = feed["brokerage"][0].get("sourceId")
            capacity = (feed.get("meta") or {}).get("totalSpaces")
            name = ((e.get("meta") or {}).get("name") or "").strip()
            address = ((e.get("meta") or {}).get("address") or "").strip()
            if not site_id or site_id in EXCLUDED_SITE_IDS or not name or not capacity:
                continue
            if site_id in NO_POSTCODE_SITES:
                lat, lon, city = NO_POSTCODE_SITES[site_id]
            else:
                m = POSTCODE.search(address)
                geo = (uk_postcodes.lookup(fetcher, m.group(1)) if m else None) or {}
                lat, lon, city = geo.get("latitude"), geo.get("longitude"), _district(geo)
            records.append(
                CapacityRecord(
                    place_id=f"tyne-wear-live-{site_id}",
                    place_name=name,
                    city_name=city or "Newcastle upon Tyne",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=address if address != name else None,
                    latitude=lat,
                    longitude=lon,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
