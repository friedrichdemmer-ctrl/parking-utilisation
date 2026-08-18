"""Q-Park garages in France, via the Base Nationale des Lieux de
Stationnement (BNLS) -- France's national off-street parking registry,
published on transport.data.gouv.fr (the national transport open-data
access point).

Much smaller and more stale than the Netherlands equivalent (the NPR):
this whole national file has only 827 rows nationwide (NL's had ~15,000),
and per transport.data.gouv.fr's own description, consolidation "is not
automated" -- the copy fetched while building this was last updated
2024-01-09, over two years old as of writing. No occupancy data of any
kind is in this schema (capacity/location only), so this is a capacity
backfill, not a live adapter, and the capacity figures themselves may be
stale if a garage's space count has changed since.

30 of the 827 rows are identifiably Q-Park ("q-park"/"qpark" in the name
or URL), spanning Bordeaux, Grenoble, Metz, Chambéry (14 of the 30 --
Chambéry's entire Q-Park network appears to be in here), Paris,
Boulogne-Billancourt, Issy-les-Moulineaux, and Sèvres.

capacity_interval_seconds is set long (30 days) since the upstream source
itself is only manually updated, occasionally -- checking more often than
that would just be re-downloading the same file.
"""

from __future__ import annotations

import csv
import io
import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

BNLS_URL = "https://transport.data.gouv.fr/resources/78899/download"
CITY_RE = re.compile(r"\d{5}[.\s]+(.+?)\.?\s*$")


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[éèêë]", "e", s)
    s = re.sub(r"[àâ]", "a", s)
    s = re.sub(r"[ç]", "c", s)
    s = re.sub(r"[îï]", "i", s)
    s = re.sub(r"[ôö]", "o", s)
    s = re.sub(r"[ùûü]", "u", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


def _city_from_address(address: str) -> str | None:
    m = CITY_RE.search(address or "")
    if not m:
        return None
    return m.group(1).strip().title()


class QParkFranceAdapter(SourceAdapter):
    name = "bnls-qpark-fr"
    fetcher_type = "http"
    capacity_interval_seconds = 30 * 24 * 3600
    occupancy_interval_seconds = 30 * 24 * 3600  # unused -- fetch_occupancy is a no-op, no occupancy field exists in this source

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        text = fetcher.get_text(BNLS_URL)
        reader = csv.DictReader(io.StringIO(text), delimiter=";")
        records = []
        for row in reader:
            name = (row.get("nom") or "").strip()
            url = (row.get("url") or "").strip()
            if "q-park" not in name.lower() and "qpark" not in name.lower() and "q-park" not in url.lower():
                continue
            capacity = row.get("nb_places")
            if not capacity:
                continue
            address = row.get("adresse") or ""
            city = _city_from_address(address)
            if not city:
                continue
            row_id = row.get("id") or name
            lat = row.get("Ylat")
            lon = row.get("Xlong")
            records.append(
                CapacityRecord(
                    place_id=f"bnls-qpark-fr-{row_id}-{_slug(name)}",
                    place_name=name,
                    city_name=city,
                    num_all=int(float(capacity)),
                    source_id=self.name,
                    address=address or None,
                    latitude=float(lat) if lat else None,
                    longitude=float(lon) if lon else None,
                    place_url=url or None,
                    source_web_url="https://www.q-park.fr/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
