"""Shared fetch helpers for MobiData BW (api.mobidata-bw.de) sources -- the
Baden-Württemberg state mobility-data platform (NVBW, Datenlizenz
Deutschland Namensnennung 2.0). Several adapters in this package each map
onto one municipality's `source_uid` on the same underlying API.
"""

from __future__ import annotations

import re

API_BASE = "https://api.mobidata-bw.de/park-api/api/public/v3/parking-sites"
GARAGE_TYPES = {"CAR_PARK", "UNDERGROUND", "OFF_STREET_PARKING_GROUND"}
SOURCE_WEB_URL = "https://mobidata-bw.de/dataset/gebuendelte-parkdaten-bw"


def slug(name: str) -> str:
    s = name.lower()
    s = s.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


def fetch_items(fetcher, source_uid: str) -> list[dict]:
    data = fetcher.get_json(f"{API_BASE}?source_uid={source_uid}&limit=200")
    return data.get("items", [])
