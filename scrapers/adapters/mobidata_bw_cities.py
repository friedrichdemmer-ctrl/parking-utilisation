"""New Baden-Württemberg cities added via MobiData BW's per-municipality
sources (see mobidata_bw_common.py for shared API access).

Each of these was checked for name overlap against the existing archive
before being added here as a fresh source -- garages that turned out to be
the same physical facility as something already on file were excluded (see
per-adapter notes) rather than risk a duplicate row. Mannheim, Karlsruhe,
and Ulm are also in MobiData BW but are NOT here: their entries there are
the same garages we already carry from earlier ParkAPI-era sources, so they
get live occupancy matched onto the existing rows instead (see
mobidata_bw_existing.py) rather than a second set of rows.
"""

from __future__ import annotations

from scrapers.adapters.mobidata_bw_common import GARAGE_TYPES, SOURCE_WEB_URL, fetch_items, slug
from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter


class _MobidataBwCityAdapter(SourceAdapter):
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 30 * 60

    source_uids: tuple[str, ...] = ()
    city_name: str = ""
    exclude_names: frozenset[str] = frozenset()

    def _rows(self, fetcher):
        for uid in self.source_uids:
            for item in fetch_items(fetcher, uid):
                if item.get("purpose") != "CAR" or item.get("type") not in GARAGE_TYPES:
                    continue
                name = (item.get("name") or "").strip()
                if not name or name in self.exclude_names:
                    continue
                yield item, name

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for item, name in self._rows(fetcher):
            capacity = item.get("capacity")
            if not capacity:
                continue
            records.append(
                CapacityRecord(
                    place_id=f"{self.name}-{item['id']}-{slug(name)}",
                    place_name=name,
                    city_name=self.city_name,
                    num_all=capacity,
                    source_id=self.name,
                    address=item.get("address"),
                    latitude=item.get("lat"),
                    longitude=item.get("lon"),
                    place_url=item.get("public_url") or None,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for item, name in self._rows(fetcher):
            if not item.get("has_realtime_data"):
                continue
            free = item.get("realtime_free_capacity")
            ts = item.get("realtime_data_updated_at")
            if free is None or not ts:
                continue
            records.append(
                OccupancyRecord(place_id=f"{self.name}-{item['id']}-{slug(name)}", ts=ts, free=int(free))
            )
        return records


class FreiburgMobidataBwAdapter(_MobidataBwCityAdapter):
    name = "mobidata-bw-freiburg"
    source_uids = ("freiburg", "freiburg_p_r_static", "freiburg_p_r_sensors")
    city_name = "Freiburg"


class AalenMobidataBwAdapter(_MobidataBwCityAdapter):
    name = "mobidata-bw-aalen"
    source_uids = ("aalen",)
    city_name = "Aalen"


class HerrenbergMobidataBwAdapter(_MobidataBwCityAdapter):
    name = "mobidata-bw-herrenberg"
    source_uids = ("herrenberg",)
    city_name = "Herrenberg"


class BietigheimBissingenMobidataBwAdapter(_MobidataBwCityAdapter):
    name = "mobidata-bw-bietigheim-bissingen"
    source_uids = ("bietigheim_bissingen",)
    city_name = "Bietigheim-Bissingen"


class BuchenMobidataBwAdapter(_MobidataBwCityAdapter):
    name = "mobidata-bw-buchen"
    source_uids = ("buchen",)
    city_name = "Buchen"


class HeilbronnMobidataBwAdapter(_MobidataBwCityAdapter):
    name = "mobidata-bw-heilbronn"
    source_uids = ("heilbronn_goldbeck",)
    city_name = "Heilbronn"
    # "Heilbronn, Bollwerksturm" is almost certainly the same physical garage
    # as the archive's existing "Am Bollwerksturm" (heilbronn-parken source)
    # -- excluded to avoid a duplicate rather than guess at a match. The
    # other 8 facilities here (a clinic complex, a residential quarter
    # garage, etc.) don't correspond to anything already on file.
    exclude_names = frozenset({"Heilbronn, Bollwerksturm"})
