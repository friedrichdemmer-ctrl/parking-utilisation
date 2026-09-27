"""Capacity for car parks in the Basque Country (Bilbao, Donostia / San
Sebastián, Vitoria-Gasteiz and a few smaller towns), via the Basque
Government's tourism open data ("Parkings de Euskadi", opendata.euskadi.eus).

Capacity-only. The list (~40 garages) has names and coordinates; each
garage's own XML record ("dataXML") has a Spanish description, and the
space count appears only there, in prose: "Contiene 755 plazas", "tiene
450 plazas", "capacidad para 338 vehículos". A count is taken only when it
is unambiguous: a single number before "plazas"/"vehículos", or several
where the first is at least five times every other (a total followed by a
sub-count, e.g. "1.135 plazas ... 16 para personas con discapacidad").
Anything else (e.g. Catedral, "489 ... 182 plazas") is skipped rather than
guessed.
"""

from __future__ import annotations

import html
import re
import time

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

LIST_URL = "https://opendata.euskadi.eus/contenidos/ds_recursos_turisticos/parkings_de_euskadi/opendata/transporte.json"
SOURCE_WEB_URL = "https://opendata.euskadi.eus/catalogo/-/parkings-de-euskadi/"
REQUEST_SPACING_SECONDS = 0.3
COUNT_RE = re.compile(r"(\d{1,3}(?:\.\d{3})*|\d+)\s*(?:plazas|vehículos|vehiculos)", re.I)


def capacity_from_description(text: str) -> int | None:
    nums = [int(n.replace(".", "")) for n in COUNT_RE.findall(text)]
    if not nums:
        return None
    first = nums[0]
    if all(first >= 5 * n for n in nums[1:]):
        return first
    return None


class EuskadiParkingsAdapter(SourceAdapter):
    name = "euskadi-parkings"
    fetcher_type = "http"
    capacity_interval_seconds = 30 * 24 * 3600
    occupancy_interval_seconds = 30 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for g in fetcher.get_json(LIST_URL):
            url = g.get("dataXML")
            if not url:
                continue
            xml = fetcher.get_bytes(url).decode("cp1252", errors="replace")
            time.sleep(REQUEST_SPACING_SECONDS)
            code = re.search(r"<codigo><!\[CDATA\[(\d+)\]\]>", xml)
            desc = re.search(r"<descripcion><!\[CDATA\[(.*?)\]\]>", xml, re.S)
            if not code or not desc:
                continue
            capacity = capacity_from_description(html.unescape(re.sub(r"<[^>]+>", " ", desc.group(1))))
            name, city = (g.get("documentName") or "").strip(), (g.get("municipality") or "").strip()
            if not capacity or not name or not city:
                continue
            lat, lon = g.get("latwgs84"), g.get("lonwgs84")
            records.append(
                CapacityRecord(
                    place_id=f"euskadi-parkings-{code.group(1)}",
                    place_name=name,
                    city_name=city,
                    num_all=capacity,
                    source_id=self.name,
                    latitude=float(lat) if lat else None,
                    longitude=float(lon) if lon else None,
                    place_url=g.get("friendlyUrl") or None,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
