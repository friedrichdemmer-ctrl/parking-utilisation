"""Q-Park's Saint-Étienne garages, via Saint-Étienne Métropole's static
parking register (WFS, cataloged on transport.data.gouv.fr under the
national etalab/schema-stationnement schema).

Capacity-only, same pattern as the other single-metro Q-Park static
backfills (db_bahnpark.py, copenhagen_qpark.py, lyon_qpark.py,
rouen_qpark.py) -- no live occupancy field exists in this register at
all. Q-Park facilities are identified by their "url" field pointing at
q-park.fr, the same convention the existing BNLS import and the AMP
Metropole adapter use; the register's other ~50 garages point at
saint-etienne.fr, saint-etienne-metropole.fr (P+R sites) or effia.com
instead.
"""

from __future__ import annotations

import re

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

WFS_URL = (
    "https://extranet.saint-etienne.fr/extrasig/geoserver/wfs"
    "?request=getFeature&typeName=vse:Parking_SaintEtienneMetropole&outputformat=application/json"
)


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[éèê]", "e", s)
    s = re.sub(r"[àâ]", "a", s)
    s = re.sub(r"[ôö]", "o", s)
    s = re.sub(r"[ûü]", "u", s)
    s = re.sub(r"[îï]", "i", s)
    s = re.sub(r"[ç]", "c", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


class SaintEtienneQParkAdapter(SourceAdapter):
    name = "saint-etienne-qpark"
    fetcher_type = "http"
    capacity_interval_seconds = 7 * 24 * 3600
    occupancy_interval_seconds = 7 * 24 * 3600  # unused -- fetch_occupancy is a no-op, see module docstring

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        data = fetcher.get_json(WFS_URL)
        records = []
        for feat in data.get("features", []):
            props = feat.get("properties", {})
            if "q-park.fr" not in (props.get("url") or ""):
                continue
            name = (props.get("nom") or "").strip()
            capacity = props.get("nb_places")
            if not name or not capacity:
                continue
            city = (props.get("adresse") or "").split(",")[-1].strip() or "Saint-Étienne"
            records.append(
                CapacityRecord(
                    place_id=f"saint-etienne-qpark-{_slug(props.get('id') or name)}",
                    place_name=name,
                    city_name=city,
                    num_all=int(capacity),
                    source_id=self.name,
                    address=props.get("adresse"),
                    latitude=props.get("ylat"),
                    longitude=props.get("xlong"),
                    place_url=props.get("url"),
                    source_web_url="https://transport.data.gouv.fr/datasets/lieux-de-stationnement-de-saint-etienne-metropole",
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        return []
