"""Live parking occupancy for Le Mans, scraped from the operator's own home
page (Cénovia, the semi-public company running the city's car parks,
www.cenoviapark.fr). No open-data or JSON feed exists (the site's WordPress
REST API has no parking endpoint); the page is server-rendered HTML with one
div.parkings__marker per car park carrying data-lat/data-lng, the name
(span.h6), "Capacité totale ... N places", and -- for car parks wired to the
guidance system -- a card-parking__places block with the free count
(span.text-h4) and an --open/--close state.

Source: https://www.cenoviapark.fr/
Licence: none stated (operator website, not an open-data release);
robots.txt only disallows /wp-admin/.

17 car parks listed, 12 with live counts (République, Quinconces P1/P2,
Jacobins, Filles Dieu, Médiathèque, Rabelais, Gare Nord, Gare Sud P1/P2 and
the hospital's P1/P2 and P3); the rest show capacity only and get a
capacity row. Values were seen to move between fetches minutes apart
(2026-10-05).

Timestamps: the page carries none, so fetch time (UTC) is used.
Skipped from occupancy: car parks marked --close (Les Halles outside its
hours -- closed is not full), those without a count, and free counts above
capacity.

Place ids are a slug of the displayed name rather than data-id, which is a
WordPress post id and could change if a page is recreated.
"""

from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

PAGE_URL = "https://www.cenoviapark.fr/"

BLOCK_SPLIT = '<div class="parkings__marker"'
LAT_RE = re.compile(r'data-lat="([-\d.]+)"\s+data-lng="([-\d.]+)"')
NAME_RE = re.compile(r'<span class="h6[^"]*">\s*([^<]+?)\s*</span>')
CAP_RE = re.compile(r"Capacité totale</span>\s*<span>\s*(\d+)\s*places", re.S)
FREE_RE = re.compile(r'card-parking__places\s+--(open|close)"(.*?)</div>\s*</div>', re.S)
COUNT_RE = re.compile(r'class="text-h4">\s*(\d+)\s*<')


def _slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "unnamed"


class LeMansLiveAdapter(SourceAdapter):
    name = "le-mans-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        page = fetcher.get_text(PAGE_URL)
        seen = set()
        for block in page.split(BLOCK_SPLIT)[1:]:
            name_m, cap_m = NAME_RE.search(block), CAP_RE.search(block)
            if not name_m or not cap_m:
                continue
            name = html.unescape(name_m.group(1)).replace("–", "-").strip()
            slug = _slug(name)
            total = int(cap_m.group(1))
            if slug in seen or total <= 0:
                continue
            seen.add(slug)
            free = None
            state = FREE_RE.search(block)
            if state and state.group(1) == "open":
                count = COUNT_RE.search(state.group(2))
                if count and int(count.group(1)) <= total:
                    free = int(count.group(1))
            ll = LAT_RE.search(block)
            yield slug, name, total, free, (float(ll.group(1)), float(ll.group(2))) if ll else None

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        return [
            CapacityRecord(
                place_id=f"{self.name}-{slug}",
                place_name=name,
                city_name="Le Mans",
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
            if free is not None
        ]
