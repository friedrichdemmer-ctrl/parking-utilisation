"""Live parking occupancy for Lyon Parc Auto (LPA) garages in the Métropole
de Lyon, via two data.grandlyon.com feeds that share a stable "identifier"
key (LPA0xxx):

- the static register ("parking_lpa_2_0_0_types") for name/address/
  capacity/coordinates
- the live feed ("lpa_mobilite.donnees/parking_temps_reel") for free-space
  counts, refreshed roughly every minute per its own "dct:date" timestamp

Not Q-Park -- LPA is a distinct, Lyon-Métropole-affiliated operator (already
present in this project only via lyon_qpark.py's 3 unrelated Q-Park
garages, which this doesn't touch or duplicate). Found via a direct
data.gouv.fr search for "parking temps réel" that surfaced several live
French feeds at once. All 31 live identifiers matched cleanly against the
37-entry static register with no ambiguity, unlike the Angers case (name-
only matching) which was skipped as too fragile.

Capacity is read from the "capacity" list entry with vehicle type "mv:Car"
and no restricted "mv:userGroup" (i.e. the general public car count, not
the disabled-permit or EV/motorbike sub-allocations that some garages also
list under "capacity").
"""

from __future__ import annotations

from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

STATIC_URL = "https://data.grandlyon.com/geoserver/lyon-parc-auto/ows?SERVICE=WFS&VERSION=2.0.0&request=GetFeature&typename=lyon-parc-auto:lpa_mobilite.parking_lpa_2_0_0&outputFormat=application/json&SRSNAME=EPSG:4326"
LIVE_URL = "https://download.data.grandlyon.com/files/rdata/lpa_mobilite.donnees/parking_temps_reel.json"


def _car_capacity(props: dict) -> int | None:
    for c in props.get("capacity", []):
        if c.get("mv:validForVehicle") == "mv:Car" and c.get("mv:userGroup") is None:
            return c.get("mv:maximumValue")
    return None


class LyonParcAutoLiveAdapter(SourceAdapter):
    name = "lyon-parc-auto-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _static_by_id(self, fetcher) -> dict:
        data = fetcher.get_json(STATIC_URL)
        by_id = {}
        for f in data.get("features", []):
            props = f["properties"]
            capacity = _car_capacity(props)
            if not capacity:
                continue
            entrances = props.get("entrance") or []
            geo = entrances[0].get("schema:geo") if entrances else {}
            addr = props.get("address") or {}
            by_id[props["identifier"]] = {
                "name": props.get("name") or props["identifier"],
                "capacity": capacity,
                "lat": geo.get("schema:latitude"),
                "lon": geo.get("schema:longitude"),
                "address": addr.get("schema:streetAddress"),
                "url": props.get("url"),
            }
        return by_id

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        by_id = self._static_by_id(fetcher)
        records = []
        for identifier, info in by_id.items():
            records.append(
                CapacityRecord(
                    place_id=f"lyon-parc-auto-live-{identifier}",
                    place_name=info["name"],
                    city_name="Lyon",
                    num_all=info["capacity"],
                    source_id=self.name,
                    address=info["address"],
                    latitude=info["lat"],
                    longitude=info["lon"],
                    place_url=info["url"],
                    source_web_url="https://data.grandlyon.com/jeux-de-donnees/parkings-lyon-parc-auto-metropole-lyon-disponibilites-temps-reel/info",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for rec in fetcher.get_json(LIVE_URL):
            if rec.get("ferme"):
                continue
            identifier = rec.get("Parking_schema:identifier")
            free = rec.get("mv:currentValue")
            ts_raw = rec.get("dct:date")
            if not identifier or free is None or not ts_raw:
                continue
            ts = datetime.fromisoformat(ts_raw).astimezone(timezone.utc).isoformat(timespec="seconds")
            records.append(OccupancyRecord(place_id=f"lyon-parc-auto-live-{identifier}", ts=ts, free=free))
        return records
