"""Live parking for Mannheim, from the JSON interface behind
parken-mannheim.de, the site of Mannheimer Parkhausbetriebe (MPB), the
city's own garage operator: https://api.parken-mannheim.de/ (one GET, a list
of facilities with "free_slots", "slots" and "updated"). The site's map
script calls it directly and it answers with CORS "*"; no licence is stated.

Mannheim used to arrive via the defgsus community archive under two
source_ids -- "parken-mannheim" (scraping this site) and "ffh-parken"
(radio FFH's copy of the same MPB data) -- and the archive has had no
parken-mannheim columns since 2026-08 (its ffh-parken Mannheim columns were
renamed upstream and land on no lots_meta row). 16 of the garages have since
been fed from MobiData BW (mobidata_bw_existing.py), whose numbers differ from
this feed (e.g. D3 117 vs 107 free a few minutes apart) and whose H6 and M4a
have not changed since 2026-08-13. This feed is the operator's own and also
covers C1, Collini-Center Mulde, the Klinikum garages and the SAP Arena / Messe
lots that have had nothing on file for years. It is meant to replace
MannheimMobidataBwOccupancyAdapter, not to run alongside it.

Like that adapter, one reading fans out to the place_ids both legacy sources
used for the same garage. Matching is on MPB's facility identifier, which the
FFH page also used as its facility id, so it survives renames on the site.
Two combined archive rows: "Hauptbahnhof P3/P4" gets P3 (sync_archive.py's
RENAME_MAP already sends the archive's later P3-only column there) and P4 gets
a row of its own; "N1/N2 Stadthaus" is one facility in this feed too, so the
separate ffh-parken N1 and N2 rows get nothing. Not in the feed: Collini-Center
Tiefgarage, Nationaltheater. Facilities not on file get new rows named after
the feed (archive-style place_id), except the Messe P20 overflow lot, which
reports 6000 of 6000 free at all times.

"updated" is local German time without an offset (15:18:00 at a 13:19 UTC
fetch) and is converted to UTC. The feed has no open/closed flag; event lots
(SAP Arena P3, Alter Messplatz) read 0 free outside events and are kept as
reported -- check them before relying on their utilisation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter
from scrapers.util import archive_slug

API_URL = "https://api.parken-mannheim.de/"
SOURCE_WEB_URL = "https://www.parken-mannheim.de/"
BERLIN = ZoneInfo("Europe/Berlin")

# MPB identifier -> (parken-mannheim place_id, ffh-parken place_id or None)
ON_FILE: dict[str, tuple[str, str | None]] = {
    "597f25bc-7cbf-452b-a6d3-b640abb8c51f": ("parken-mannheim-C1-Hauptverwaltung-MPB-Parkhaus", "ffh-parken-mannheim-C1"),
    "656e6f2a-004c-4dc7-b5c5-26c111788165": ("parken-mannheim-Collini-Center-Mulde-Parkplatz", "ffh-parken-mannheim-Mulde-Collini-Center"),
    "PH11": ("parken-mannheim-D3-Tiefgarage", "ffh-parken-mannheim-D3"),
    "dd821ad7-ecc0-491b-9553-39b30515418b": ("parken-mannheim-D5-Reiss-Museum-Tiefgarage", "ffh-parken-mannheim-D5-Reiss-Museum"),
    "839b9ba8-5f90-453b-850f-f7e2ee38b216": ("parken-mannheim-G1-Marktplatz-Tiefgarage", "ffh-parken-mannheim-G1-Marktplatz"),
    "9c6cbb8f-6f51-47cf-9d6b-df11befa0023": ("parken-mannheim-H6-Tiefgarage", "ffh-parken-mannheim-H6"),
    "548778f9-8756-4488-8b99-4b4223cabafa": ("parken-mannheim-Hauptbahnhof-P1-Tiefgarage", "ffh-parken-mannheim-Hbf-P1"),
    "a0524b0f-f3ca-488a-9bcd-844913947545": ("parken-mannheim-Hauptbahnhof-P2-Parkhaus", "ffh-parken-mannheim-Hbf-P2"),
    "d25ec82f-649f-4213-b139-5e8f553489de": ("parken-mannheim-Hauptbahnhof-P3-P4-Parkhaus", "ffh-parken-mannheim-Hbf-P3"),
    "b3e246cf-b858-4891-a3a2-3984b0e8810f": ("parken-mannheim-Hauptbahnhof-P5-Parkhaus", None),
    "262e7f6a-f692-4453-ac7a-748fe6c61edb": ("parken-mannheim-Klinikum-Tiefgarage", "ffh-parken-mannheim-Klinikum"),
    "5167280d-8809-4df3-b342-0b8cbd6bca00": ("parken-mannheim-Klinikum-P3", None),
    "6a6d210a-39c6-408d-899c-3387015c9d69": ("parken-mannheim-Kunsthalle-Tiefgarage", None),
    "59c77768-d24e-4409-8f64-56bcb3109c4e": ("parken-mannheim-M4a-Parkplatz", "ffh-parken-mannheim-Parkplatz-M4a"),
    "e5974820-22fa-43df-9368-4e5f4f9f0594": ("parken-mannheim-N1-N2-Stadthaus-Parkhaus", None),
    "caaa8b47-6691-4b22-bac6-754927d95841": ("parken-mannheim-N6-Komforthaus", "ffh-parken-mannheim-N6-Komfort"),
    "30f686f4-5dc9-456f-b241-aebbd67ecbc2": ("parken-mannheim-N6-Standardhaus", "ffh-parken-mannheim-N6-Standard-Holiday-Inn"),
    "14b6ebb8-90db-46d1-ad62-9c89926a912a": ("parken-mannheim-U2-Tiefgarage", "ffh-parken-mannheim-U2"),
    "934480a6-ca43-49c1-9be0-9f7f9d3bdf26": ("parken-mannheim-SAP-Arena-P1-Parkhaus", "ffh-parken-mannheim-SAP-Arena-P1"),
    "31de496c-f38c-4a25-911a-aabec4854e53": ("parken-mannheim-SAP-Arena-P2-Parkhaus", "ffh-parken-mannheim-SAP-Arena-P2"),
    "PH07": ("parken-mannheim-SAP-Arena-P3-Parkhaus", "ffh-parken-mannheim-SAP-Arena-P3"),
    "f2b93679-67f1-40a5-896d-635d541e8a23": ("parken-mannheim-SAP-Arena-P6-P8-Parkplatz", "ffh-parken-mannheim-Messe-P6-P8"),
}
SKIPPED = {"b8874acd-39d9-424c-9405-1fc3307b7df8"}  # Messe Großparkplatz P20, constant 6000/6000


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _place_ids(item: dict) -> tuple[str, ...]:
    ident = item.get("identifier") or ""
    if ident in ON_FILE:
        return tuple(p for p in ON_FILE[ident] if p)
    return (f"parken-mannheim-{archive_slug(item.get('title') or '')}",)


class MannheimLiveAdapter(SourceAdapter):
    name = "parken-mannheim"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def _items(self, fetcher) -> list[dict]:
        return [
            i for i in fetcher.get_json(API_URL)
            if (i.get("title") or "").strip() and i.get("identifier") not in SKIPPED
        ]

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        # Only this source's own rows: the ffh-parken rows keep the capacity
        # they have (the FFH adapter does not cover Mannheim).
        records = []
        for item in self._items(fetcher):
            capacity = _int(item.get("slots"))
            if not capacity:
                continue
            records.append(
                CapacityRecord(
                    place_id=_place_ids(item)[0],
                    place_name=item["title"].strip(),
                    city_name="Mannheim",
                    num_all=capacity,
                    source_id=self.name,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for item in self._items(fetcher):
            free, updated = _int(item.get("free_slots")), item.get("updated")
            if free is None or not updated:
                continue
            local = datetime.strptime(updated, "%Y-%m-%d %H:%M:%S").replace(tzinfo=BERLIN)
            ts = local.astimezone(timezone.utc).isoformat(timespec="seconds")
            for place_id in _place_ids(item):
                records.append(OccupancyRecord(place_id=place_id, ts=ts, free=free))
        return records
