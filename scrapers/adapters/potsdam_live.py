"""Live parking for Potsdam, scraped from the city's mobility portal
(mobil-potsdam.de, "Parken in Potsdam").

Potsdam used to arrive only via the defgsus community archive under
source_id "mobil-potsdam-parken". That archive's scraper broke when the
page's markup changed on 2026-08-25 (the garage name moved into a <th>),
so the city dropped out of the archive entirely. The page itself still
carries live data, so this adapter reads it directly and keeps writing
into the same place_ids -- its name is that legacy source_id, so the
existing history continues.

The page lists 27 sites; on 2026-09-25 only 7 carried a live free count
(the central Karstadt/Zentrum and Schiffbauergasse garages no longer
report). Capacity comes from each site's detail block ("Kapazität"),
which the archive never had. The page has no timestamp, so readings use
the fetch time. place_ids follow the archive's naming (ASCII-folded
name, non-alphanumerics as "-"); four sites were renamed on the page and
are mapped back to their archive names in LEGACY_NAMES.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

PAGE_URL = "https://www.mobil-potsdam.de/de/parken/parken-in-potsdam/"

LEGACY_NAMES = {
    "Tiefgarage Luisenplatz in Potsdam": "Luisenplatz",
    "Parkhaus Zentrum Hegelallee in Potsdam - Karstadt / Zentrum": "Karstadt / Zentrum",
    "Parkhaus Schiffbauergasse in Potsdam / Hans-Otto-Theater": "Schiffbauergasse / Hans-Otto-Theater",
    "P+R Campus Jungfernsee": "Campus Jungfernsee",
}

ROW_RE = re.compile(
    r'<tr class="(?:even )?content" id="roadwork_(\d+)".*?'
    r'<th scope="row" class="col2"><a [^>]*title="([^"]*)".*?'
    r'<td class="col3"[^>]*>(.*?)</td>',
    re.S,
)
DETAIL_RE = re.compile(r'<table class="info-table expandable" id="roadwork_detail_(\d+)">(.*?)</table>', re.S)
FIELD_RE = re.compile(r'<th scope="col">([^<]*):</th>\s*<td[^>]*>(.*?)</td>', re.S)


def _text(s: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def _place_id(name: str) -> str:
    return f"mobil-potsdam-parken-{archive_slug(LEGACY_NAMES.get(name, name))}"


class PotsdamLiveAdapter(SourceAdapter):
    name = "mobil-potsdam-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _sites(self, fetcher) -> dict[str, dict]:
        page = fetcher.get_text(PAGE_URL)
        sites: dict[str, dict] = {}
        for site_id, name, free in ROW_RE.findall(page):
            free = _text(free)
            sites.setdefault(site_id, {"name": _text(name), "free": int(free) if free.isdigit() else None})
        for site_id, block in DETAIL_RE.findall(page):
            if site_id not in sites:
                continue
            fields = {_text(label): _text(value) for label, value in FIELD_RE.findall(block)}
            capacity = fields.get("Kapazität", "")
            sites[site_id]["capacity"] = int(capacity) if capacity.isdigit() else None
            sites[site_id]["address"] = fields.get("Adresse") or None
        return sites

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for site in self._sites(fetcher).values():
            if not site.get("capacity"):
                continue
            records.append(
                CapacityRecord(
                    place_id=_place_id(site["name"]),
                    place_name=site["name"],
                    city_name="Potsdam",
                    num_all=site["capacity"],
                    source_id=self.name,
                    address=site.get("address"),
                    source_web_url=PAGE_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return [
            OccupancyRecord(place_id=_place_id(site["name"]), ts=now, free=site["free"])
            for site in self._sites(fetcher).values()
            if site["free"] is not None
        ]
