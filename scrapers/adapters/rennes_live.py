"""Live parking occupancy for Rennes, from Rennes Métropole's Opendatasoft
portal (data.rennesmetropole.fr), two datasets, both licence ODbL:

  * "export-api-parking-citedia" -- the 10 city-centre garages run by
    Citédia (Colombier, Gare-Sud, Hoche, Lices, Kléber, Arsenal, ...).
    Read through the v1 records API because it exposes each record's
    "record_timestamp" (the portal's ingest time, refreshed every few
    minutes and in correct UTC -- 14:15:12Z at a 14:16Z fetch); the
    feed itself has no per-garage time.
  * "tco-parcsrelais-star-etat-tr" -- the 8 STAR park-and-ride sites
    (J.F. Kennedy, Henri Fréville, Les Gayeulles, La Poterie, ...), with
    their own "lastupdate" in correct UTC (14:06Z at a 14:07Z fetch,
    updated every ~3 minutes).

The P+R records split capacity by user type; the pair used here is
"capacitesoliste" / "jrdinfosoliste" (ordinary single-occupant cars -- the
bulk of each site). The car-pool counts are not used: "capacitecovoiturage"
is 0 at every site while "jrdinfocovoiturage" reports up to 96 free, so
those fields do not form a consistent pair.

Skipped: Citédia garages whose "status" is not OUVERT/COMPLET, P+R sites
whose "etatouverture" is not OUVERT, readings with free outside
[0, capacity], and readings older than STALE_AFTER.

place_ids: f"rennes-live-{id}" for Citédia (the feed's numeric garage id,
e.g. "1503" = Colombier) and f"rennes-live-pr-{idparc}" for P+R (the
STAR three-letter code, e.g. "jfk"), both stable across runs; the
Opendatasoft recordid is not used.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

CITEDIA_URL = "https://data.rennesmetropole.fr/api/records/1.0/search/?dataset=export-api-parking-citedia&rows=100"
PR_URL = "https://data.rennesmetropole.fr/api/explore/v2.1/catalog/datasets/tco-parcsrelais-star-etat-tr/records?limit=100"
CITEDIA_WEB = "https://data.rennesmetropole.fr/explore/dataset/export-api-parking-citedia/"
PR_WEB = "https://data.rennesmetropole.fr/explore/dataset/tco-parcsrelais-star-etat-tr/"
STALE_AFTER = timedelta(hours=6)

CITEDIA_OPEN = {"OUVERT", "COMPLET"}
# STAR P+R sites outside the city of Rennes itself
PR_COMMUNES = {"CVI": "Cesson-Sévigné"}


def _ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


class RennesLiveAdapter(SourceAdapter):
    name = "rennes-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _rows(self, fetcher):
        """Yield (place_id, name, city, capacity, free, ts, status_ok, lat, lon, web_url)."""
        data = fetcher.get_json(CITEDIA_URL)
        for rec in data.get("records", []):
            f = rec.get("fields", {})
            gid = str(f.get("id") or "").strip()
            name = (f.get("key") or "").strip()
            total, free = f.get("max"), f.get("free")
            if not gid or not name or not isinstance(total, int) or total <= 0:
                continue
            lat, lon = f.get("geo") or [None, None]  # v1 API: [lat, lon]
            try:
                ts = _ts(rec["record_timestamp"])
            except (KeyError, ValueError):
                ts = None
            yield (
                f"{self.name}-{gid}", name, "Rennes", total, free, ts,
                (f.get("status") or "").upper() in CITEDIA_OPEN,
                lat, lon, CITEDIA_WEB,
            )

        data = fetcher.get_json(PR_URL)
        for r in data.get("results", []):
            code = (r.get("idparc") or "").strip()
            name = (r.get("nom") or "").strip()
            total, free = r.get("capacitesoliste"), r.get("jrdinfosoliste")
            if not code or not name or not isinstance(total, int) or total <= 0:
                continue
            geo = r.get("coordonnees") or {}
            try:
                ts = _ts(r["lastupdate"])
            except (KeyError, TypeError, ValueError):
                ts = None
            yield (
                f"{self.name}-pr-{code.lower()}", f"P+R {name}", PR_COMMUNES.get(code, "Rennes"), total, free, ts,
                (r.get("etatouverture") or "").upper() == "OUVERT",
                geo.get("lat"), geo.get("lon"), PR_WEB,
            )

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        return [
            CapacityRecord(
                place_id=pid,
                place_name=name,
                city_name=city,
                num_all=total,
                source_id=self.name,
                latitude=lat,
                longitude=lon,
                source_web_url=web,
            )
            for pid, name, city, total, _free, _ts, _ok, lat, lon, web in self._rows(fetcher)
        ]

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        now = datetime.now(timezone.utc)
        records = []
        for pid, _name, _city, total, free, ts, ok, _lat, _lon, _web in self._rows(fetcher):
            if not ok or not isinstance(free, int) or not 0 <= free <= total or ts is None:
                continue
            if now - ts > STALE_AFTER:
                continue
            records.append(OccupancyRecord(place_id=pid, ts=ts.isoformat(timespec="seconds"), free=free))
        return records
