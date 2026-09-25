"""UK-wide car parks from the Department for Transport's 2014 "Car Parks"
dataset (built for the Transport Direct journey planner), via the copy
Esri UK / Transport for West Midlands still host on ArcGIS Online. DfT's
own download link now redirects to a 2014 closure notice.

Capacity-only, and frozen: DfT stopped maintaining it in 2014, so some
sites will have closed, been renamed or changed operator since. It is
the only source for most commercial garages (NCP, Q-Park, APCOA, Euro Car
Parks, Vinci) outside the cities with council data, e.g. central London,
Belfast, Liverpool. Open Government Licence v3.0.

4,676 sites (4,650 in Great Britain, 26 in Northern Ireland). Skipped:
33 with no space count, and 164 already covered by a fresher source
(TfL, City of London, Hillingdon, Harrow, Bristol, Leeds, York, Dundee,
Perth & Kinross, Tyne & Wear, Ards & North Down). Because the dataset
never changes, that overlap -- and which sites lie in Greater London --
was worked out once and stored in dft_uk_carparks.json, keyed by the
dataset's autoID. Overlap rule: a fresher site within 250 m sharing a
distinctive name word, within 150 m with capacity within 10%, or within
400 m with a shared word and capacity within 25%; retail parks never
match non-retail sites; plus four hand-checked pairs. Sites in Greater
London get city "London" like the other London sources; others use the
dataset's own town.
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

LAYER_URL = "https://services.arcgis.com/WQ9KVmV6xGGMnCiQ/arcgis/rest/services/UKCarParks_WFL/FeatureServer/0"
PAGE_SIZE = 2000

_DERIVED = json.loads((Path(__file__).with_suffix(".json")).read_text())
EXCLUDED = set(_DERIVED["excluded"])
LONDON = set(_DERIVED["london"])
TOWN_FALLBACK = {int(k): v for k, v in _DERIVED["town_fallback"].items()}


def _page_url(offset: int) -> str:
    params = {
        "where": "1=1",
        "outFields": "autoID,Car_Park_Name,Street_1,Town,Postcode,Number_of_Spaces,Latitude,Longitude",
        "orderByFields": "autoID",
        "resultOffset": offset,
        "resultRecordCount": PAGE_SIZE,
        "f": "json",
    }
    return f"{LAYER_URL}/query?{urllib.parse.urlencode(params)}"


class DftUkCarParksAdapter(SourceAdapter):
    name = "dft-uk-carparks"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def _rows(self, fetcher) -> list[dict]:
        rows, offset = [], 0
        while True:
            data = fetcher.get_json(_page_url(offset))
            features = data.get("features", [])
            rows += [f.get("attributes", {}) for f in features]
            offset += len(features)
            if not features or not data.get("exceededTransferLimit"):
                return rows

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for a in self._rows(fetcher):
            auto_id = a.get("autoID")
            name = (a.get("Car_Park_Name") or "").strip()
            capacity = a.get("Number_of_Spaces")
            if auto_id is None or auto_id in EXCLUDED or not name or not capacity:
                continue
            town = (a.get("Town") or "").strip() or TOWN_FALLBACK.get(auto_id)
            city = "London" if auto_id in LONDON else town
            if not city:
                continue
            address = ", ".join(
                v.strip() for v in (a.get("Street_1"), a.get("Town"), a.get("Postcode")) if v and v.strip()
            )
            records.append(
                CapacityRecord(
                    place_id=f"dft-uk-carparks-{auto_id}",
                    place_name=name,
                    city_name=city,
                    num_all=int(capacity),
                    source_id=self.name,
                    address=address or None,
                    latitude=a.get("Latitude") or None,
                    longitude=a.get("Longitude") or None,
                    source_web_url="https://www.arcgis.com/home/item.html?id=bd03477bcb2f46e3a034bcbfc7664a5e",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
