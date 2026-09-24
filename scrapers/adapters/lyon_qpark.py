"""Q-Park's Lyon garages, via the Métropole de Lyon's static parking
register (data.grandlyon.com WFS).

Capacity-only, same pattern as db_bahnpark.py and copenhagen_qpark.py.
Métropole de Lyon does publish a genuinely live feed for this data
("Parkings de la Métropole de Lyon - disponibilités temps réel v2"), and
2 of these 3 Q-Park garages are flagged in the static register itself as
having it (parkingtempsreel=true, with a idparkingcriter id) -- but as of
writing that live endpoint (and its raw-XML alternative from the same
"Système Criter") both require authentication that wasn't available
without registering, unlike the static register queried here. Revisit if
that changes; for now this only backfills capacity/location, matching the
other "we know the garage exists and its size, not its current occupancy"
sources already in this project.

Only the 3 garages whose "gestionnaire" (operator) field is exactly
"Q PARK" are trusted as Q-Park's, same discipline as copenhagen_qpark.py:
this register also lists Effia, Indigo, Urbis Park, SNCF, and several
others, and guessing from address/name alone risks misattributing a
similar-looking garage to the wrong operator.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

WFS_URL = (
    "https://data.grandlyon.com/geoserver/metropole-de-lyon/ows"
    "?SERVICE=WFS&VERSION=2.0.0&request=GetFeature"
    "&typename=metropole-de-lyon:pvo_patrimoine_voirie.pvoparking"
    "&outputFormat=application/json&SRSNAME=EPSG:4326"
)


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[éèê]", "e", s)
    s = re.sub(r"[àâ]", "a", s)
    s = re.sub(r"[ç]", "c", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class LyonQParkAdapter(SourceAdapter):
    name = "lyon-qpark"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(WFS_URL)
        records = []
        for feat in data.get("features", []):
            props = feat.get("properties", {})
            if props.get("gestionnaire") != "Q PARK":
                continue
            name = (props.get("nom") or "").strip()
            capacity = props.get("capacite")
            if not name or not capacity:
                continue
            lon, lat = (feat.get("geometry") or {}).get("coordinates", [None, None])
            commune = (props.get("commune") or "Lyon").strip()
            records.append(
                CapacityRecord(
                    place_id=f"lyon-qpark-{_slug(props.get('idparking') or name)}",
                    place_name=name,
                    city_name=commune,
                    num_all=int(capacity),
                    source_id=self.name,
                    address=props.get("voieentree"),
                    latitude=lat,
                    longitude=lon,
                    source_web_url="https://data.grandlyon.com/portail/fr/jeux-de-donnees/parkings-metropole-lyon/info",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
