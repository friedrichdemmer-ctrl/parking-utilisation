"""Live parking occupancy for Reims, scraped from the operator's own home
page (Champagne Parc Auto, www.cpa-champagneparcauto.com), which runs the
city-centre garages. No open-data or JSON feed exists; the page is
server-rendered WordPress HTML with two blocks:

- the "Disponibilités" list: one cpa_searchparking_list_item per garage,
  name in ..._item2 and "N places" (free spaces) in ..._item3;
- the map: one hidden div.iBox per garage (<h1>NAME</h1>, "<span>M</span>
  places" = capacity, beside levels and height) and a google.maps.Marker
  with the same title and its coordinates.

The two are joined on the displayed name.

Source: https://www.cpa-champagneparcauto.com/
Licence: none stated (operator website, not an open-data release);
robots.txt only disallows /wp-admin/.

6 garages (Buirette, Cathédrale, Erlon, Gambetta, Hôtel de Ville,
République). Values were seen to move between fetches minutes apart
(2026-10-05).

Timestamps: the page carries none, so fetch time (UTC) is used.
Skipped: garages without a capacity on the map, and free counts above
capacity.

Place ids are a slug of the displayed name -- there is no other stable id
(the infobox numbers are WordPress post ids, which could change).
"""

from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

PAGE_URL = "https://www.cpa-champagneparcauto.com/"

FREE_RE = re.compile(
    r'cpa_searchparking_list_item2">\s*([^<]+?)\s*</div>\s*<div class="cpa_searchparking_list_item3">\s*(\d+)\s*places?',
    re.S,
)
BOX_RE = re.compile(r'class="iBox">\s*<h1>\s*([^<]+?)\s*</h1>(.*?)</div>', re.S)
CAP_RE = re.compile(r'<span class="spanBleu">\s*(\d+)\s*</span>\s*places', re.S)
MARKER_RE = re.compile(
    r"LatLng\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)\s*,.*?title:\s*'([^']+)'",
    re.S,
)


def _slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "unnamed"


class ReimsLiveAdapter(SourceAdapter):
    name = "reims-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        page = fetcher.get_text(PAGE_URL)
        caps, coords = {}, {}
        for name, body in BOX_RE.findall(page):
            m = CAP_RE.search(body)
            if m:
                caps[_slug(html.unescape(name))] = int(m.group(1))
        for lat, lon, title in MARKER_RE.findall(page):
            coords[_slug(html.unescape(title))] = (float(lat), float(lon))
        seen = set()
        for raw, free in FREE_RE.findall(page):
            name = html.unescape(raw).strip()
            slug = _slug(name)
            total = caps.get(slug)
            if slug in seen or not total or int(free) > total:
                continue
            seen.add(slug)
            yield slug, name.title(), total, int(free), coords.get(slug)

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        return [
            CapacityRecord(
                place_id=f"{self.name}-{slug}",
                place_name=name,
                city_name="Reims",
                num_all=total,
                latitude=coord[0] if coord else None,
                longitude=coord[1] if coord else None,
                source_id=self.name,
                source_web_url=PAGE_URL,
            )
            for slug, name, total, _free, coord in self._rows(fetcher)
        ]

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return [
            OccupancyRecord(place_id=f"{self.name}-{slug}", ts=ts, free=free)
            for slug, _name, _total, free, _coord in self._rows(fetcher)
        ]
