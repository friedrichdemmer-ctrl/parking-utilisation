"""Capacity for car parks across Austria, via parken.at -- the garage
directory run for the Austrian chambers of commerce (WKO), which the City
of Vienna's own open-data garage layer (ogdwien:GARAGENOGD) links to for
every entry.

Capacity-only. The site's marker list (one call over an Austria-wide
bounding box, ~800 entries) has names and coordinates; the space count
("stellplaetze") is only in each garage's detail record, so the capacity
run makes one request per garage, spaced out, and only monthly. Entries
with 0 spaces (e-charging stations, P+R sites listed without a count)
are skipped. The per-garage "stpstatus" is only VACANT/OCCUPIED/UNDEFINED,
not a count, so it is not used as occupancy.

Garages that the Salzburg live feed already covers with real counts are
left out here (EXCLUDED_IDS), so they are not listed twice.
"""

from __future__ import annotations

import time

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

AJAX_URL = "https://www.parken.at/include/ajax2.php"
# Austria's extent with a little margin
MARKERS_URL = AJAX_URL + "?markers=true&nelat=49.1&nelon=17.2&swlat=46.3&swlon=9.5&lang=d"
SOURCE_WEB_URL = "https://www.parken.at/"
REQUEST_SPACING_SECONDS = 0.3
MAX_FAILURE_SHARE = 0.1

# parken.at ids of Salzburg garages taken from scrapers/adapters/salzburg_live.py
# instead (matched by position, all within 45 m, and by name)
EXCLUDED_IDS: set[str] = {
    "1207",   # Akademieplatz -> Akademiestraße
    "1028",   # Parkgarage Linzer Gasse
    "1265",   # Mirabell-Congress Garage
    "1277",   # Parkplatz Petersbrunnhof
    "4347",   # P & R Salzburg Süd Alpenstraße
    "1276",   # Wifi-Garage
    "1280",   # Bahnhofsgarage
    "18534",  # Auersperg - Salzburg | APCOA
    "5874",   # Parkgarage am Paracelsusbad
}


class ParkenAtAdapter(SourceAdapter):
    name = "parken-at"
    fetcher_type = "http"
    capacity_interval_seconds = 30 * 24 * 3600
    occupancy_interval_seconds = 30 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        markers = fetcher.get_json(MARKERS_URL)
        records, failures = [], 0
        for m in markers:
            gid = str(m.get("id") or "")
            if not gid or gid in EXCLUDED_IDS:
                continue
            try:
                g = fetcher.get_json(f"{AJAX_URL}?garage={gid}&lang=d")
            except Exception:
                failures += 1
                continue
            finally:
                time.sleep(REQUEST_SPACING_SECONDS)
            spaces = str(g.get("stellplaetze") or "").strip()
            name = (g.get("name") or "").strip()
            if not spaces.isdigit() or int(spaces) <= 0 or not name:
                continue
            street = (g.get("adresse") or "").strip()
            town = " ".join(p for p in ((g.get("plz") or "").strip(), (g.get("ort") or "").strip()) if p)
            records.append(
                CapacityRecord(
                    place_id=f"parken-at-{gid}",
                    place_name=name,
                    city_name=(g.get("ort") or "").strip() or None,
                    num_all=int(spaces),
                    source_id=self.name,
                    address=", ".join(p for p in (street, town) if p) or None,
                    latitude=float(g["lat"]) if g.get("lat") else None,
                    longitude=float(g["lon"]) if g.get("lon") else None,
                    place_url=f"https://www.parken.at/garage/{gid}/",
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        if markers and failures / len(markers) > MAX_FAILURE_SHARE:
            raise RuntimeError(f"{failures} of {len(markers)} garage detail requests failed")
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
