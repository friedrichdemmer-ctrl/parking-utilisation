"""Live parking for Frauenfeld (Switzerland), via the canton of
Thurgau's open-data portal (data.tg.ch, "Parkplatzbelegung Stadt
Frauenfeld", CC0).

Six municipal car parks (Oberes/Unteres Mätteli, Marktplatz 2-Std and
10-Std, Freie-Strasse/Bankplatz, Parkhaus Altstadt). The dataset is a
rolling series for the current day at 5-minute steps, so each run reads
the newest records and keeps the latest per car park ("visualplan_id").
Capacity is total_spots minus deactivated_spots.
"""

from __future__ import annotations

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

API_URL = "https://data.tg.ch/api/v2/catalog/datasets/frauenfeld-1/records?limit=100&order_by=timestamp%20desc"
SOURCE_WEB_URL = "https://data.tg.ch/explore/dataset/frauenfeld-1/"


class FrauenfeldLiveAdapter(SourceAdapter):
    name = "frauenfeld-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _latest(self, fetcher) -> list[dict]:
        latest: dict[int, dict] = {}
        for rec in fetcher.get_json(API_URL).get("records", []):
            f = rec.get("record", {}).get("fields", {})
            if f.get("visualplan_id") is not None:
                latest.setdefault(f["visualplan_id"], f)
        return list(latest.values())

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for f in self._latest(fetcher):
            capacity = (f.get("total_spots") or 0) - (f.get("deactivated_spots") or 0)
            name = (f.get("name") or "").strip()
            if not name or capacity <= 0:
                continue
            point = f.get("koordinaten") or {}
            records.append(
                CapacityRecord(
                    place_id=f"frauenfeld-live-{f['visualplan_id']}",
                    place_name=name,
                    city_name="Frauenfeld",
                    num_all=capacity,
                    source_id=self.name,
                    latitude=point.get("lat"),
                    longitude=point.get("lon"),
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return [
            OccupancyRecord(place_id=f"frauenfeld-live-{f['visualplan_id']}", ts=f["timestamp"], free=int(f["available_spots"]))
            for f in self._latest(fetcher)
            if f.get("available_spots") is not None and f.get("timestamp")
        ]
