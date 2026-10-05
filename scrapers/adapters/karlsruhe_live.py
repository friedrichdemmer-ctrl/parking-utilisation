"""Live parking for Karlsruhe, from the TechnologieRegion Karlsruhe's
mobility GeoServer (mobil.trk.de, layer TBA:parkhaeuser) -- the data behind
the city's parking guidance page web1.karlsruhe.de/service/Parken/. Its
sibling layers (park_ride, freies_parken, ...) are published on
transparenz.karlsruhe.de under CC BY 4.0.

Karlsruhe used to arrive via the defgsus community archive under source_id
"karlsruhe-parken", which scraped the city page; the page's markup changed
and the archive has had no karlsruhe-parken columns since 2026-08. 18 of the
21 garages on file have since been fed from MobiData BW
(mobidata_bw_existing.py), which republishes this same layer: values and
timestamps were identical for every garage on 2026-10-05, so if both run,
write_occupancy's (place_id, ts) check drops the second copy. This layer also
carries Staatstheater and Landesbibliothek, which MobiData leaves out (stale
on file since 2022-07).

The layer covers the whole TechnologieRegion (Rastatt, Baden-Baden,
Bruchsal, ... and Alsace); only gemeinde == "Karlsruhe" is read here. Times
("stand_freieparkplaetze") are per garage and genuinely UTC (13:10Z at a
13:16Z fetch). Readings are skipped when the site is marked closed, has no
real-time count, or its "echtzeit_status" is not "OK": the three garages
reporting "Störung" (Herrenstraße / Zirkel, Postgalerie, Ludwigsplatz) have
shown one constant value since 2026-08-13 according to lots_meta.
"""

from __future__ import annotations

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

API_URL = (
    "https://mobil.trk.de/geoserver/TBA/ows?service=WFS&version=1.0.0&request=GetFeature"
    "&typeName=TBA%3Aparkhaeuser&outputFormat=application%2Fjson&srsName=EPSG%3A4326"
)
SOURCE_WEB_URL = "https://web1.karlsruhe.de/service/Parken/"

# feed name -> archive place name, where they differ ("Zirkel (P&C)" on file has no counterpart)
LEGACY_NAMES = {
    "Staatstheater": "Am Staatstheater",
    "Herrenstraße / Zirkel": "Herrenstraße/Zirkel",
    "IHK": "Industrie und Handelskammer",
    "Kreuzstraße": "Kreuzstraße (C&A)",
    "Mendelssohnplatz": "Mendelssohnplatz (Scheck-In)",
    "Postgalerie": "Post Galerie",
}


def _place_id(name: str) -> str:
    return f"karlsruhe-parken-{archive_slug(LEGACY_NAMES.get(name, name))}"


class KarlsruheLiveAdapter(SourceAdapter):
    name = "karlsruhe-parken"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _sites(self, fetcher) -> list[dict]:
        sites = []
        for f in fetcher.get_json(API_URL).get("features", []):
            p = f.get("properties") or {}
            if p.get("gemeinde") != "Karlsruhe" or not (p.get("parkhaus_name") or "").strip():
                continue
            coords = (f.get("geometry") or {}).get("coordinates") or [None, None]
            sites.append({**p, "_lon": coords[0], "_lat": coords[1]})
        return sites

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for p in self._sites(fetcher):
            name, capacity = p["parkhaus_name"].strip(), p.get("gesamte_parkplaetze")
            # sites without a real-time count are not part of this source's history
            if not capacity or p.get("echtzeit_belegung") != "T":
                continue
            records.append(
                CapacityRecord(
                    place_id=_place_id(name),
                    place_name=LEGACY_NAMES.get(name, name),
                    city_name="Karlsruhe",
                    num_all=int(capacity),
                    source_id=self.name,
                    address=(p.get("parkhaus_strasse") or "").strip() or None,
                    latitude=p["_lat"],
                    longitude=p["_lon"],
                    place_url=p.get("parkhaus_internet") or None,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for p in self._sites(fetcher):
            free, ts = p.get("freie_parkplaetze"), p.get("stand_freieparkplaetze")
            if (
                free is None
                or not ts
                or p.get("echtzeit_belegung") != "T"
                or p.get("geschlossen") != "F"
                or p.get("echtzeit_status") != "OK"
            ):
                continue
            # kept verbatim ("...Z"), the same string MobiData BW serves, so the
            # (place_id, ts) duplicate check works if both adapters run
            records.append(OccupancyRecord(place_id=_place_id(p["parkhaus_name"].strip()), ts=ts, free=int(free)))
        return records
