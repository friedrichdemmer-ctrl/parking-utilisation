"""Live parking occupancy for Brest, scraped from the operator's own home
page (Brest'Park, www.brest-park.fr), whose "Disponibilité des places en
temps réel" block is server-rendered HTML: one "<p class="parking">Name :</p>
<p class="places">N places / M</p>" pair per car park.

Source: https://www.brest-park.fr/
Licence: none stated (operator website, not an open-data release). Brest
métropole's open data ("Parkings", DEP_STA_Parkings on data.gouv.fr /
geo.brest-metropole.fr ArcGIS) is static capacity only -- no live counts
were found in any machine-readable form, hence the HTML.

8 car parks on the page (7 used, see Skipped): the city-centre garages Coat-ar-Gueven, Liberté, Jaurès and
Les Capucins, plus the barrier-controlled surface "enclos" (Gares,
Sangnier, Château, Parc à Chaînes). No P+R. Capacities on the page differ
slightly from the open-data file (e.g. Coat-ar-Gueven 690 vs 720); the
page's own figure is used.

Timestamps: the page carries none, so fetch time (UTC) is used. Values
were confirmed to move between fetches minutes apart.

Skipped: entries that do not parse as "N places / M", capacity <= 0, and
Parc à Chaînes (FROZEN below), which read exactly "80 places / 80" (fully
free) on every fetch over 15 minutes on a weekday afternoon while every
other site moved -- almost certainly a non-counting site; recording it
would store a constant "empty". Re-check before un-skipping.
A free count above capacity is skipped rather than stored.

Place ids are a slug of the displayed name -- there is no other id.
"""

from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

PAGE_URL = "https://www.brest-park.fr/"

ROW_RE = re.compile(
    r'<p class="parking">\s*(?P<name>[^<]+?)\s*:?\s*</p>\s*<p class="places">\s*(?P<free>\d+)\s*places?\s*/\s*(?P<total>\d+)',
    re.S,
)


# slugs of sites whose count does not move (see docstring)
FROZEN = {"parc-a-chaines"}


def _slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "unnamed"


class BrestLiveAdapter(SourceAdapter):
    name = "brest-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        page = fetcher.get_text(PAGE_URL)
        seen = set()
        for m in ROW_RE.finditer(page):
            name = html.unescape(m.group("name")).strip().rstrip(":").strip()
            free, total = int(m.group("free")), int(m.group("total"))
            slug = _slug(name)
            if not name or total <= 0 or free > total or slug in seen or slug in FROZEN:
                continue
            seen.add(slug)
            yield slug, name, total, free

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        return [
            CapacityRecord(
                place_id=f"{self.name}-{slug}",
                place_name=name,
                city_name="Brest",
                num_all=total,
                source_id=self.name,
                source_web_url=PAGE_URL,
            )
            for slug, name, total, _free in self._rows(fetcher)
        ]

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return [
            OccupancyRecord(place_id=f"{self.name}-{slug}", ts=ts, free=free)
            for slug, _name, _total, free in self._rows(fetcher)
        ]
