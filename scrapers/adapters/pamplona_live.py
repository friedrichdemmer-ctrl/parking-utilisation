"""Parking for Pamplona, via the city's XML feed (pamplona.es/xml/parkings.xml,
listed on datos.gob.es as "Ayto. de Pamplona: Ocupación de parkings en
tiempo real").

UTF-16 XML with the 10 city-centre garages: total spaces, free spaces
("---" when a garage does not report) and one update time for the whole
file (FECHA, aaaammddHHMM, local time). When first added (2026-09-27) the
file had not updated since 2026-09-17, so for now it mainly contributes
capacities; readings are keyed by that update time, so a frozen file adds
nothing new until it moves again.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "http://www.pamplona.es/xml/parkings.xml"
SOURCE_WEB_URL = "https://datos.gob.es/es/catalogo/l01312016-ayto-de-pamplona-ocupacion-de-parkings-en-tiempo-real"
MADRID = ZoneInfo("Europe/Madrid")


def _text(fetcher) -> str:
    raw = fetcher.get_bytes(API_URL)
    return raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", errors="replace")


def _field(block: str, name: str) -> str:
    m = re.search(rf"<{name}>(.*?)</{name}>", block, re.S)
    return m.group(1).strip() if m else ""


def _garages(text: str):
    return re.findall(r"<APARCAMIENTO>(.*?)</APARCAMIENTO>", text, re.S)


class PamplonaLiveAdapter(SourceAdapter):
    name = "pamplona-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for g in _garages(_text(fetcher)):
            code, name, total = _field(g, "CODIGO"), _field(g, "NOMBRE"), _field(g, "TOTAL")
            if not code or not name or not total.isdigit() or int(total) <= 0:
                continue
            lat, lon = _field(g, "LATITUD"), _field(g, "LONGITUD")
            records.append(
                CapacityRecord(
                    place_id=f"pamplona-live-{code}",
                    place_name=name,
                    city_name="Pamplona",
                    num_all=int(total),
                    source_id=self.name,
                    address=_field(g, "DIRECCION") or None,
                    latitude=float(lat) if lat else None,
                    longitude=float(lon) if lon else None,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        text = _text(fetcher)
        stamp = _field(text, "FECHA")
        if not re.fullmatch(r"\d{12}", stamp):
            return []
        ts = datetime.strptime(stamp, "%Y%m%d%H%M").replace(tzinfo=MADRID).astimezone(timezone.utc).isoformat(timespec="seconds")
        records = []
        for g in _garages(text):
            code, free = _field(g, "CODIGO"), _field(g, "LIBRES")
            if code and free.isdigit():
                records.append(OccupancyRecord(place_id=f"pamplona-live-{code}", ts=ts, free=int(free)))
        return records
