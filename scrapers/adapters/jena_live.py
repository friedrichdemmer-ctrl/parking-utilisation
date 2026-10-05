"""Live parking for Jena, via Kommunal Service Jena's DATEX II
"Parkplatzbelegung" publication on the city's open-data portal
(wissensallmende.jena.de, dataset "Parken", licence CC BY 3.0 DE --
attribution: Stadt Jena / Kommunal Service Jena).

Jena used to arrive only via the defgsus community archive under
source_id "mobilitaet-jena", which scrapes the HTML table on
mobilitaet.jena.de/de/parken. That table and this feed carry the same
numbers; the feed is machine-readable and has a per-site status time, so
this adapter takes over that source_id and keeps writing into the
archive's place_ids (f"mobilitaet-jena-{archive_slug(name)}" -- the DATEX
facility reference id is the same plain name the page shows).

Only the 10 sites wired to the guidance system are in the status
publication; the other ~30 entries on the page ("Letzte Aktualisierung:
nie") have no live count at all, and the archive only ever recorded a
daily 0 for them, so they are not covered here. The portal labels every
distribution "Testdatei, keine gesicherten Daten", but the status file is
republished every minute and matches the city's own page.

Capacity: the feed's totalParkingCapacityShortTermOverride. It disagrees
with several older archive figures (e.g. Goethe Galerie 523 vs 740 on
file, Krautgasse 200 vs 381) but matches the highest free count the
archive has ever seen for those sites, so the feed is taken as right.
Coordinates and addresses come from the portal's static-data JSON when it
can be fetched; capacity does not depend on it.

Timestamps: parkingFacilityStatusTime, already UTC ("Z"), and verified
against the fetch time (status times 1-15 minutes old). Sites with no
status time or no vacant count are skipped.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

STATUS_URL = "https://piveau-hub-store.nomad-dmz.jena.de/data/66f698a98c9ecc037d225207"
STATIC_URL = "https://piveau-hub-store.nomad-dmz.jena.de/data/64c27d71028162587b492f0e"
DATASET_URL = "https://wissensallmende.jena.de/datasets/parken"
NS = {"d2": "http://datex2.eu/schema/2/2_0"}


def _place_id(name: str) -> str:
    return f"mobilitaet-jena-{archive_slug(name)}"


def _int(text: str | None) -> int | None:
    try:
        return int(float(text)) if text not in (None, "") else None
    except ValueError:
        return None


class JenaLiveAdapter(SourceAdapter):
    name = "mobilitaet-jena"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _status(self, fetcher) -> list[dict]:
        root = ET.fromstring(fetcher.get_text(STATUS_URL))
        sites = []
        for st in root.iter(f"{{{NS['d2']}}}parkingFacilityStatus"):
            ref = st.find("d2:parkingFacilityReference", NS)
            name = (ref.get("id") or "").strip() if ref is not None else ""
            if not name:
                continue
            sites.append(
                {
                    "name": name,
                    "time": st.findtext("d2:parkingFacilityStatusTime", None, NS),
                    "free": _int(st.findtext("d2:totalNumberOfVacantParkingSpaces", None, NS)),
                    "capacity": _int(st.findtext("d2:totalParkingCapacityShortTermOverride", None, NS)),
                }
            )
        return sites

    def _static(self, fetcher) -> dict[str, dict]:
        # best-effort metadata (coords/address); never block capacity on it
        try:
            data = json.loads(fetcher.get_text(STATIC_URL))
        except Exception:
            return {}
        out = {}
        for p in data.get("parkingPlaces", []):
            general = p.get("general") or {}
            details = p.get("details") or {}
            coords = general.get("coordinates") or {}
            address = (details.get("parkingPlaceAddress") or {}).get("parkingPlaceAddress")
            if general.get("name"):
                out[general["name"].strip()] = {"lat": coords.get("lat"), "lng": coords.get("lng"), "address": address}
        return out

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        static = self._static(fetcher)
        records = []
        for s in self._status(fetcher):
            if not s["capacity"]:
                continue
            meta = static.get(s["name"], {})
            records.append(
                CapacityRecord(
                    place_id=_place_id(s["name"]),
                    place_name=s["name"],
                    city_name="Jena",
                    num_all=s["capacity"],
                    source_id=self.name,
                    address=meta.get("address"),
                    latitude=meta.get("lat"),
                    longitude=meta.get("lng"),
                    source_web_url=DATASET_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for s in self._status(fetcher):
            if s["free"] is None or not s["time"]:
                continue
            ts = datetime.fromisoformat(s["time"].replace("Z", "+00:00")).astimezone(timezone.utc)
            records.append(
                OccupancyRecord(place_id=_place_id(s["name"]), ts=ts.isoformat(timespec="seconds"), free=s["free"])
            )
        return records
