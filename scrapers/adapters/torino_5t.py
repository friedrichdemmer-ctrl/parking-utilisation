"""Live parking for Turin, via 5T's open-data feed (opendata.5t.torino.it/
get_pk, listed on dati.gov.it as "Parcheggi disponibili nelle strutture",
Comune di Torino). 5T runs the city's traffic and parking-guidance system.

One XML document with every structured car park (~40): name, id,
coordinates, capacity ("Total") and, when the site is in service
(status="1"), a free count ("Free"). The document's end_time (UTC) is the
end of the 5-minute measurement window and is used as each reading's
timestamp. Sites with status 0 have no free count and are skipped for
occupancy but keep their capacity record.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://opendata.5t.torino.it/get_pk"
SOURCE_WEB_URL = "https://www.dati.gov.it/view-dataset/dataset?id=parcheggi-disponibili-nelle-strutture"
ROW_RE = re.compile(r"<PK_data ([^>]*)/>")
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def _rows(xml: str) -> list[dict[str, str]]:
    return [dict(ATTR_RE.findall(r)) for r in ROW_RE.findall(xml)]


class Torino5TAdapter(SourceAdapter):
    name = "torino-5t"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for r in _rows(fetcher.get_text(API_URL)):
            total, name = r.get("Total", ""), (r.get("Name") or "").strip()
            if not r.get("ID") or not name or not total.isdigit() or int(total) <= 0:
                continue
            records.append(
                CapacityRecord(
                    place_id=f"torino-5t-{r['ID']}",
                    place_name=name.title(),
                    city_name="Torino",
                    num_all=int(total),
                    source_id=self.name,
                    latitude=float(r["lat"]) if r.get("lat") else None,
                    longitude=float(r["lng"]) if r.get("lng") else None,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        xml = fetcher.get_text(API_URL)
        m = re.search(r'end_time="([^"]+)"', xml)
        if not m:
            return []
        ts = m.group(1).replace("Z", "+00:00").replace(".000+", "+")
        records = []
        for r in _rows(xml):
            free = r.get("Free", "")
            if r.get("status") == "1" and r.get("ID") and free.isdigit():
                records.append(OccupancyRecord(place_id=f"torino-5t-{r['ID']}", ts=ts, free=int(free)))
        return records
