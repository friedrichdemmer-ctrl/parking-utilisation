"""Live parking for Málaga's municipal car parks (SMASSA), via the city's
open-data portal (datosabiertos.malaga.eu, "Ocupación aparcamientos
públicos municipales"), refreshed every minute.

The feed is a three-column CSV (dato, id, libres) keyed by a two-letter
code, with no timestamp -- readings are stamped with the fetch time,
truncated to the minute. Names and coordinates come from the portal's
catalogue CSV for the same codes; "SA" (Salitre) is missing from it and
is taken from the "Ubicación de aparcamientos públicos municipales" layer.

Neither file has a capacity, so CAPACITY holds the public (rotation)
space counts from the portal's "Aparcamientos en rotación" layer, which
lists them per car park ("262 Plazas Públicas a Rotación"). Pío Baroja is
not in that layer; its 276 rotation spaces are from the city's own
announcement of the garage (El Español, 2023-07-10). Alcazaba and Camas
have no published count and are left out.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

LIVE_URL = "https://datosabiertos.malaga.eu/recursos/aparcamientos/ocupappublicosmun/ocupappublicosmun.csv"
CATALOGUE_URL = "https://datosabiertos.malaga.eu/recursos/aparcamientos/ocupappublicosmun/catalogo.csv"
SOURCE_WEB_URL = "https://datosabiertos.malaga.eu/dataset/ocupacion-aparcamientos-publicos-municipales"

CAPACITY = {
    "TE": 262,  # Tejón y Rodríguez
    "MA": 450,  # Plaza de la Marina
    "SJ": 702,  # San Juan de la Cruz
    "CY": 455,  # Carlos Haya
    "AN": 621,  # Avenida de Andalucía
    "PA": 135,  # El Palo
    "CE": 436,  # Cervantes
    "SA": 443,  # Salitre
    "PB": 276,  # Pío Baroja
}
# not in the catalogue CSV
EXTRA_SITES = {"SA": ("Salitre", "Calle Salitre, Málaga", 36.7132149, -4.4276681)}


class MalagaLiveAdapter(SourceAdapter):
    name = "malaga-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        sites = dict(EXTRA_SITES)
        for r in csv.DictReader(io.StringIO(fetcher.get_text(CATALOGUE_URL).lstrip("﻿"))):
            lat, lon = float(r["latitude"] or 0), float(r["longitude"] or 0)
            sites[r["id"]] = (r["nombre"].strip(), r["direccion"].strip(), lat or None, lon or None)
        records = []
        for code, capacity in CAPACITY.items():
            if code not in sites:
                continue
            name, address, lat, lon = sites[code]
            records.append(
                CapacityRecord(
                    place_id=f"malaga-live-{code.lower()}", place_name=name, city_name="Málaga", num_all=capacity,
                    source_id=self.name, address=address or None, latitude=lat, longitude=lon,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        ts = datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat(timespec="seconds")
        text = fetcher.get_text(LIVE_URL).lstrip("﻿")
        records = []
        for r in csv.DictReader(io.StringIO(text)):
            code, free = (r.get("id") or "").strip(), (r.get("libres") or "").strip()
            if code in CAPACITY and free.isdigit():
                records.append(OccupancyRecord(place_id=f"malaga-live-{code.lower()}", ts=ts, free=int(free)))
        # the first production run got a 200 with nothing parseable and was
        # recorded as a silent success; make that an error instead
        if not records:
            raise RuntimeError(f"no readings in Málaga feed response: {text[:120]!r}")
        return records
