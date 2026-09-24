"""Live parking occupancy across Métropole Aix-Marseille-Provence, via its
Opendatasoft portal (data.ampmetropole.fr).

Found while sweeping France's missing Q-Park cities: 8 of the dataset's 79
garages are explicitly Q-Park's (identified by their "site" field pointing
at q-park.fr, the same way the existing BNLS import identifies Q-Park
facilities) -- spanning Marseille, Aubagne, and La Ciotat. The dataset
covers several other operators too (Effia, Interparking, RTM, Indigo, a
municipal one) across Marseille, Cassis, Aix-en-Provence and Senas as
well; since fetching the whole dataset costs the same as fetching just the
Q-Park rows, all of it is kept rather than filtered down -- in scope per
"also cover non-Q-Park towns where effort is low."

Only rows with tempsreel == "True" are used (40 of 79 as of writing) --
the rest are real garages with known capacity but no live feed behind
them, same "not every garage in a dataset is actually live" pattern seen
elsewhere in this project.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = (
    "https://data.ampmetropole.fr/api/explore/v2.1/catalog/datasets/"
    "disponibilites-des-places-de-parkings/records?limit=100"
)


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[éèê]", "e", s)
    s = re.sub(r"[àâ]", "a", s)
    s = re.sub(r"[ôö]", "o", s)
    s = re.sub(r"[ûü]", "u", s)
    s = re.sub(r"[îï]", "i", s)
    s = re.sub(r"[ç]", "c", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


def _parse_ts(s: str | None) -> str | None:
    # e.g. "2026-09-24 17:25:09" -- Europe/Paris local time, no offset given
    if not s:
        return None
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Europe/Paris"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


class AmpMetropoleLiveAdapter(SourceAdapter):
    name = "amp-metropole-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        data = fetcher.get_json(API_URL)
        for r in data.get("results", []):
            if r.get("tempsreel") != "True":
                continue
            name = (r.get("nom") or "").strip()
            commune = (r.get("commune") or "").strip().title()
            capacity = r.get("voitureplacescapacite")
            available = r.get("voitureplacesdisponibles")
            ts = _parse_ts(r.get("datemajpy"))
            if not name or not commune or not capacity or available is None or ts is None:
                continue
            yield r, name, commune, int(capacity), int(available), ts

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for r, name, commune, capacity, _avail, _ts in self._rows(fetcher):
            place_id = f"amp-metropole-live-{_slug(commune)}-{_slug(name)}"
            point = r.get("pointgeo") or {}
            records.append(
                CapacityRecord(
                    place_id=place_id,
                    place_name=name,
                    city_name=commune,
                    num_all=capacity,
                    source_id=self.name,
                    address=r.get("adresse"),
                    latitude=point.get("lat"),
                    longitude=point.get("lon"),
                    place_url=r.get("site"),
                    source_web_url="https://data.ampmetropole.fr/explore/dataset/disponibilites-des-places-de-parkings/",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for _r, name, commune, _capacity, available, ts in self._rows(fetcher):
            place_id = f"amp-metropole-live-{_slug(commune)}-{_slug(name)}"
            records.append(OccupancyRecord(place_id=place_id, ts=ts, free=available))
        return records
