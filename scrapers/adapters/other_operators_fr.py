"""Non-Q-Park garages in the same French cities Q-Park operates in, from the
same national registry as qpark_fr.py (BNLS, transport.data.gouv.fr).

Q-Park's own facilities are deliberately excluded here (skipped if the name
or URL mentions Q-Park) since those are already covered by qpark_fr.py
under source_id="bnls-qpark-fr" -- this fills in the *other* garages this
dataset has for the same 8 cities: 256 of them, dominated by Paris's own
extensive network (Concorde, Bastille, Invalides, Champs-Élysées, and
~150 more) plus Bordeaux's network of Indigo/Metpark/Effia/Transdev-run
garages. Same staleness caveat as qpark_fr.py: this national file was last
updated 2024-01-09 and isn't kept current automatically, and has no
occupancy field at all -- capacity only.
"""

from __future__ import annotations

import csv
import io

from scrapers.adapters.qpark_fr import BNLS_URL, _city_from_address, _slug
from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

TARGET_CITIES = {
    "Bordeaux",
    "Grenoble",
    "Metz",
    "Chambéry",
    "Paris",
    "Boulogne-Billancourt",
    "Issy-Les-Moulineaux",
    "Sevres",
}


def _is_qpark(name: str, url: str) -> bool:
    return "q-park" in name.lower() or "qpark" in name.lower() or "q-park" in url.lower()


class OtherOperatorsFranceAdapter(SourceAdapter):
    name = "bnls-other-fr"
    fetcher_type = "http"
    capacity_interval_seconds = 30 * 24 * 3600
    occupancy_interval_seconds = 30 * 24 * 3600  # unused -- fetch_occupancy is a no-op, no occupancy field in this source

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        text = fetcher.get_text(BNLS_URL)
        reader = csv.DictReader(io.StringIO(text), delimiter=";")
        records = []
        for row in reader:
            name = (row.get("nom") or "").strip()
            url = (row.get("url") or "").strip()
            if not name or _is_qpark(name, url):
                continue
            capacity = row.get("nb_places")
            if not capacity:
                continue
            address = row.get("adresse") or ""
            city = _city_from_address(address)
            if city not in TARGET_CITIES:
                continue
            row_id = row.get("id") or name
            lat = row.get("Ylat")
            lon = row.get("Xlong")
            records.append(
                CapacityRecord(
                    place_id=f"bnls-other-fr-{row_id}-{_slug(name)}",
                    place_name=name,
                    city_name=city,
                    num_all=int(float(capacity)),
                    source_id=self.name,
                    address=address or None,
                    latitude=float(lat) if lat else None,
                    longitude=float(lon) if lon else None,
                    place_url=url or None,
                    source_web_url="https://transport.data.gouv.fr/datasets/base-nationale-des-lieux-de-stationnement",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
