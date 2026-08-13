"""Munich garages via the Parkraumwende München civic initiative's open CSV.

Not a live feed -- this is a crowdsourced/manually-curated catalog (many
entries cross-referenced to Munich's own official OpenData LHM portal for
capacity, "Freie Plätze" filled in sporadically by volunteers). Munich has
zero garages in the archive otherwise, so this is worth adding as real
capacity coverage, but the cadence here is honest about what the source
actually is: weekly capacity re-sync, daily occupancy check (catches
whenever a volunteer updates a free-space figure, which is not often) --
not the 30-min cadence used for genuinely live sources like Köln's.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

CSV_URL = "https://data.parkraumwende.de/data/parkraummap.csv"
INCLUDED_TYPES = {"Tiefgarage", "Parkhaus", "Außenstellplatz"}


def _slug(name: str) -> str:
    s = name.lower()
    s = s.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


def _to_float(s: str) -> float | None:
    s = (s or "").strip()
    return float(s) if s else None


def _to_int(s: str) -> int | None:
    s = (s or "").strip()
    return int(float(s)) if s else None


class MuenchenParkraumwendeAdapter(SourceAdapter):
    name = "parkraumwende-muenchen"
    fetcher_type = "http"
    occupancy_interval_seconds = 24 * 3600  # source is crowdsourced, updated sporadically -- daily is honest, not 30 min
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        text = fetcher.get_text(CSV_URL)
        reader = csv.DictReader(io.StringIO(text), delimiter=";")
        for row in reader:
            if row.get("Typ") not in INCLUDED_TYPES:
                continue
            if row.get("Aktiv") != "Ja":
                continue
            if row.get("Ort", "").strip() != "München":
                continue
            if not row.get("Plätze", "").strip():
                continue
            yield row

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for row in self._rows(fetcher):
            name = row["Name"].strip()
            place_id = f"parkraumwende-muenchen-{row['ID']}-{_slug(name)}"
            address_parts = [row.get("Straße", "").strip(), row.get("Hausnummer", "").strip()]
            address = " ".join(p for p in address_parts if p) or None

            records.append(
                CapacityRecord(
                    place_id=place_id,
                    place_name=name,
                    city_name="München",
                    num_all=_to_int(row["Plätze"]),
                    source_id=self.name,
                    address=address,
                    latitude=_to_float(row.get("Latitude", "")),
                    longitude=_to_float(row.get("Longitude", "")),
                    place_url=row.get("URL 1", "").strip() or None,
                    source_web_url="https://data.parkraumwende.de/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        records = []
        for row in self._rows(fetcher):
            free = row.get("Freie Plätze", "").strip()
            if not free:
                continue
            place_id = f"parkraumwende-muenchen-{row['ID']}-{_slug(row['Name'].strip())}"
            records.append(OccupancyRecord(place_id=place_id, ts=now, free=int(float(free))))
        return records
