"""Non-Q-Park garages in the same Dutch cities Q-Park operates in, via the
same Nationaal Parkeerregister (NPR) infrastructure as qpark_nl.py.

Rather than re-querying opendata.rdw.nl per area manager, this filters the
full national facility list (~14,900 entries, one HTTP call) by matching
the "(City)" suffix most NPR facility names carry against Q-Park's 33
Dutch cities -- the same city set already established via qpark_nl.py's
collected data. That match was verified before writing this: 858
facilities, versus Q-Park's own 159 in the same cities.

Q-Park's own facilities are excluded by UUID (fetched once from the same
Socrata query qpark_nl.py uses to enumerate them) rather than re-checking
each facility's static operator field -- cheaper, and it's the same
authoritative list qpark_nl.py itself is built from, so exclusion stays
consistent between the two adapters even if either changes independently.

Same live-occupancy caveat as qpark_nl.py: a dynamicDataUrl field on the
facility list doesn't mean anonymous access is actually granted. Reuses
the identical 401-tolerant, staleness-filtered approach, and only attempts
a dynamic fetch for facilities the root list already flags with a
dynamicDataUrl -- fetching all ~700 non-Q-Park facilities' dynamic
endpoints on the fast occupancy cadence just to find most 401 would be
wasteful against an unauthenticated government API.
"""

from __future__ import annotations

import re
import urllib.error
from datetime import datetime, timezone

from scrapers.adapters.qpark_nl import AREAS_URL, MAX_OCCUPANCY_AGE_SECONDS, NPR_BASE, _slug
from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

NPR_ROOT_URL = "https://npropendata.rdw.nl/parkingdata/v2/"
CITY_SUFFIX_RE = re.compile(r"\(([^)]+)\)\s*$")

# The 33 Dutch cities qpark_nl.py found real Q-Park garages in -- kept as an
# explicit list here (rather than derived at runtime) since it's what scopes
# this adapter to "other garages in Q-Park's cities" as opposed to all
# ~14,900 facilities nationwide.
QPARK_NL_CITIES = {
    "Amersfoort", "Amstelveen", "Amsterdam", "Apeldoorn", "Arnhem", "Assen",
    "Bergen op Zoom", "Beverwijk", "Boxtel", "Breda", "Den Bosch", "Den Haag",
    "Deventer", "Diemen", "Dordrecht", "Driebergen-Rijsenburg", "Duivendrecht",
    "Ede", "Eindhoven", "Enschede", "Gorinchem", "Gouda", "Groningen", "Halfweg",
    "Heemstede", "Heerenveen", "Heerlen", "Helmond", "Hengelo", "Hilversum",
    "Hoofddorp", "Leeuwarden", "Leiderdorp", "Maastricht", "Middelburg",
    "Naarden", "Nieuwegein", "Nijmegen", "Oisterwijk", "Oosterhout", "Oss",
    "Oud-Beijerland", "Ridderkerk", "Rijswijk", "Roermond", "Roosendaal",
    "Rotterdam", "Schiedam", "Sittard", "Sneek", "Utrecht",
    "Valkenburg aan de Geul", "Veenendaal", "Venlo", "Vlaardingen", "Weert",
    "Woerden", "Zaandam", "Zutphen", "Zwijndrecht", "Zwolle",
}


def _city_from_facility_name(name: str) -> str | None:
    m = CITY_SUFFIX_RE.search(name or "")
    if not m:
        return None
    city = m.group(1).strip()
    return city if city in QPARK_NL_CITIES else None


def _place_id(uuid: str, name: str) -> str:
    return f"npr-other-nl-{uuid}-{_slug(name)}"


class OtherOperatorsNetherlandsAdapter(SourceAdapter):
    name = "npr-other-nl"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 30 * 60

    def _qpark_uuids(self, fetcher) -> set[str]:
        areas = fetcher.get_json(AREAS_URL)
        return {a["uuid"] for a in areas if a.get("uuid")}

    def _matched_facilities(self, fetcher) -> list[tuple[dict, str]]:
        """Yields (facility, city) for non-Q-Park facilities in Q-Park's cities."""
        qpark_uuids = self._qpark_uuids(fetcher)
        root = fetcher.get_json(NPR_ROOT_URL)
        out = []
        for fac in root.get("ParkingFacilities", []):
            uuid = fac.get("identifier")
            name = fac.get("name") or ""
            if not uuid or uuid in qpark_uuids:
                continue
            city = _city_from_facility_name(name)
            if not city:
                continue
            out.append((fac, city))
        return out

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for fac, city in self._matched_facilities(fetcher):
            uuid = fac["identifier"]
            name = fac.get("name") or ""
            try:
                static = fetcher.get_json(f"{NPR_BASE}/static/{uuid}")
            except Exception as exc:
                print(f"[{self.name}] capacity: failed to fetch static data for {name}: {exc}")
                continue
            info = static.get("parkingFacilityInformation") or {}
            specs = info.get("specifications") or []
            capacity = specs[0].get("capacity") if specs else None
            if not capacity:
                continue
            location = info.get("locationForDisplay") or {}
            access_points = info.get("accessPoints") or []
            address = (access_points[0].get("accessPointAddress") if access_points else None) or {}
            address_str = " ".join(p for p in (address.get("streetName"), address.get("houseNumber")) if p) or None
            actual_city = address.get("city") or city
            records.append(
                CapacityRecord(
                    place_id=_place_id(uuid, name),
                    place_name=name,
                    city_name=actual_city,
                    num_all=int(capacity),
                    source_id=self.name,
                    address=address_str,
                    latitude=location.get("latitude"),
                    longitude=location.get("longitude"),
                    source_web_url="https://opendata.rdw.nl/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for fac, _city in self._matched_facilities(fetcher):
            if "dynamicDataUrl" not in fac:
                continue
            uuid = fac["identifier"]
            name = fac.get("name") or ""
            try:
                dynamic = fetcher.get_json(f"{NPR_BASE}/dynamic/{uuid}")
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 404):
                    continue  # not exposed for us -- most facilities, despite listing a dynamicDataUrl
                print(f"[{self.name}] occupancy: failed to fetch dynamic data for {name}: {exc}")
                continue
            except Exception as exc:
                print(f"[{self.name}] occupancy: failed to fetch dynamic data for {name}: {exc}")
                continue
            status = (dynamic.get("parkingFacilityDynamicInformation") or {}).get("facilityActualStatus") or {}
            free = status.get("vacantSpaces")
            last_updated = status.get("lastUpdated")
            if free is None or last_updated is None:
                continue
            try:
                # This adapter spans many different backend providers behind the
                # same NPR facade (see module docstring), unlike qpark_nl.py's
                # single consistent feed -- they don't all agree on field types
                # (e.g. lastUpdated as a unix number vs a string), so one
                # facility's odd response must never take down the whole run.
                last_updated_f = float(last_updated)
                free_i = int(free)
            except (TypeError, ValueError):
                print(f"[{self.name}] occupancy: unexpected field types for {name}: free={free!r} lastUpdated={last_updated!r}")
                continue
            age_seconds = datetime.now(timezone.utc).timestamp() - last_updated_f
            if age_seconds > MAX_OCCUPANCY_AGE_SECONDS:
                continue  # stale reading -- same issue seen and handled in qpark_nl.py
            ts = datetime.fromtimestamp(last_updated_f, tz=timezone.utc).isoformat(timespec="seconds")
            records.append(OccupancyRecord(place_id=_place_id(uuid, name), ts=ts, free=free_i))
        return records
