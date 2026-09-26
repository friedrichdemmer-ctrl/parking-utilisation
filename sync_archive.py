#!/usr/bin/env python3
"""Incrementally pull new daily data from the defgsus/parking-data community
archive and import only the day-files not yet in historical_observations.

Why this exists: a couple dozen "-parken" sources (Dresden, Bielefeld,
Bonn, and others) went stale on 2026-08-12 with no error anywhere. The
cause wasn't a crash -- those sources are fed entirely by
import_historical.py's bootstrap import, which only ever runs once, on
first boot. The defgsus archive itself kept getting a new day added daily
the whole time (confirmed via its GitHub commit history), so the fix is
to keep pulling it, not to restart anything.

import_historical.py is NOT reusable for this: historical_observations has
no unique constraint on (place_id, ts), so blindly re-running its import
would duplicate every one of the ~15M rows already imported. This tracks
progress explicitly via an `archive_sync_state` table and only ever
imports day-files strictly after the last recorded date, so re-running it
is always safe.
"""

from __future__ import annotations

import csv
import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
ARCHIVE = Path(os.environ.get("PARKING_ARCHIVE_PATH", ROOT / "parking-data-archive"))
DB_PATH = Path(os.environ.get("PARKING_DB_PATH", ROOT / "data" / "parking.db"))
ARCHIVE_GIT_URL = "https://github.com/defgsus/parking-data.git"
ARCHIVE_FIRST_DAY = date(2020, 1, 25)  # the archive's earliest known day-file

STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS archive_sync_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_imported_day TEXT NOT NULL
);
"""


def _pull_archive() -> None:
    if not ARCHIVE.exists():
        subprocess.run(["git", "clone", "--depth", "1", ARCHIVE_GIT_URL, str(ARCHIVE)], check=True)
        return
    # a --depth 1 clone can't just "pull" -- fetch and reset to the remote tip instead
    subprocess.run(["git", "-C", str(ARCHIVE), "fetch", "--depth", "1", "origin", "master"], check=True)
    subprocess.run(["git", "-C", str(ARCHIVE), "reset", "--hard", "origin/master"], check=True)


def _day_file_for(d: date) -> Path:
    return ARCHIVE / "csv" / f"{d.year:04d}" / f"{d.year:04d}-{d.month:02d}" / f"{d.isoformat()}.csv"


# The upstream feed renamed these columns at some point (found via a user
# report that Wiesbaden looked stale): new columns add a "PH-"/"TG-"
# (Parkhaus/Tiefgarage) prefix and abbreviate, e.g.
# "ffh-parken-wiesbaden-PH-City-II" for the garage our archive-derived
# lots_meta has long called "ffh-parken-wiesbaden-City-2". Verified by name
# and, where two garages at the same site made the name ambiguous
# (Parkhaus- vs Tiefgarage-Liliencarre), by the PH-/TG- prefix rather than
# guessed. Without this map, new data for these garages would import
# successfully but under a place_id with no matching lots_meta row --
# invisible in the app, not lost, but not showing up either. "City 1" has
# no current counterpart at all (dropped upstream, not renamed) and stays
# unmapped/stale.
RENAME_MAP: dict[str, str] = {
    "ffh-parken-wiesbaden-PH-City-II": "ffh-parken-wiesbaden-City-2",
    "ffh-parken-wiesbaden-PH-Coulinstr": "ffh-parken-wiesbaden-Coulinstrasse",
    "ffh-parken-wiesbaden-PH-Galeria-Kaufhof": "ffh-parken-wiesbaden-Galeria-Kaufhof",
    "ffh-parken-wiesbaden-PH-Karstadt": "ffh-parken-wiesbaden-Karstadt",
    "ffh-parken-wiesbaden-PH-Kurhaus-Casino": "ffh-parken-wiesbaden-Kurhaus-Casino",
    "ffh-parken-wiesbaden-PH-Lili": "ffh-parken-wiesbaden-Parkhaus-Liliencarre",
    "ffh-parken-wiesbaden-TG-Lili": "ffh-parken-wiesbaden-Tiefgarage-Liliencarre",
    "ffh-parken-wiesbaden-TG-RMCC": "ffh-parken-wiesbaden-RMCC",
    "ffh-parken-wiesbaden-PH-Luisenforum": "ffh-parken-wiesbaden-Luisenforum",
    "ffh-parken-wiesbaden-PH-Luisenplatz": "ffh-parken-wiesbaden-Luisenplatz",
    "ffh-parken-wiesbaden-PH-Markt": "ffh-parken-wiesbaden-Markt",
    "ffh-parken-wiesbaden-PH-Mauritius": "ffh-parken-wiesbaden-Mauritius-Galerie",
    "ffh-parken-wiesbaden-PH-Theater": "ffh-parken-wiesbaden-Theater",

    # Same failure mode found for Lübeck: the upstream feed switched from
    # numeric place_ids ("parken-luebeck-42") to verbose slugified names
    # ("parken-luebeck-Roeckstrasse-Parkplatz-Roeckstrasse-Parkplatz-Luebeck",
    # doubled by an upstream generator bug) at some point. Matched by name to
    # the existing lots_meta entries below -- only the unambiguous 1:1 cases
    # (single old candidate, no combined/duplicate-name old entry to confuse
    # it with). Garages left unmapped (e.g. two "Leuchtenfeld" old entries,
    # "Müllergarten u. Mühlendamm" combining two new names into one old
    # capacity, or genuinely no old counterpart) get their own fresh
    # lots_meta row instead of a guessed capacity -- see
    # migrate_luebeck_orphans.py.
    "parken-luebeck-Am-Bahnhof-Handelshof-Parkplatz-Strassenrand-Am-Bahnhof-Handelshof-Parkplatz-Strassenrand-Lubeck": "parken-luebeck-32",
    "parken-luebeck-Am-Burgfeld-Parkplatz-Am-Burgfeld-Parkplatz-Lubeck": "parken-luebeck-43",
    "parken-luebeck-Am-Fischereihafen-Parkplatz-Am-Fischereihafen-Parkplatz-Travemunde": "parken-luebeck-96",
    "parken-luebeck-Backbord-Parkplatz-Backbord-Parkplatz-Travemunde": "parken-luebeck-54",
    "parken-luebeck-Bauhof-Parkplatz-Bauhof-Parkplatz-Lubeck": "parken-luebeck-23",
    "parken-luebeck-Beckergrube-Parkplatz-Beckergrube-Parkplatz-Lubeck": "parken-luebeck-19",
    "parken-luebeck-Bruckenweg-Parkplatz-Bruckenweg-Parkplatz-Lubeck": "parken-luebeck-28",
    "parken-luebeck-Burgstrasse-Parkplatz-Burgstrasse-Parkplatz-Lubeck": "parken-luebeck-17",
    "parken-luebeck-Fahrstrasse-Parkplatz-Fahrstrasse-Parkplatz-Lubeck": "parken-luebeck-44",
    "parken-luebeck-Fahrvorplatz-Parkplatz-Fahrvorplatz-Parkplatz-Travemunde": "parken-luebeck-65",
    "parken-luebeck-Hafenbahnhof-Parkplatz-Hafenbahnhof-Parkplatz-Travemunde": "parken-luebeck-63",
    "parken-luebeck-Hermann-Lange-Strasse-Parkplatz-Hermann-Lange-Strasse-Parkplatz-Lubeck": "parken-luebeck-35",
    "parken-luebeck-Kanalstrasse-P2-Parkplatz-Kanalstrasse-P2-Parkplatz-Lubeck": "parken-luebeck-88",
    "parken-luebeck-Kanalstrasse-P3-Parkplatz-Kanalstrasse-P3-Parkplatz-Lubeck": "parken-luebeck-89",
    "parken-luebeck-Kanalstrasse-P4-Parkplatz-Kanalstrasse-P4-Parkplatz-Lubeck": "parken-luebeck-90",
    "parken-luebeck-Kanalstrasse-P5-Parkplatz-Kanalstrasse-P5-Parkplatz-Lubeck": "parken-luebeck-91",
    "parken-luebeck-Kowitzberg-Parkplatz-Kowitzberg-Parkplatz-Travemunde": "parken-luebeck-98",
    "parken-luebeck-Kurgartenstrasse-Parkplatz-Kurgartenstrasse-Parkplatz-Travemunde": "parken-luebeck-64",
    "parken-luebeck-Lastadie-P3-Parkplatz-Lastadie-P3-Parkplatz-Lubeck": "parken-luebeck-45",
    "parken-luebeck-Lastadie-P5-Parkplatz-Lastadie-P5-Parkplatz-Lubeck": "parken-luebeck-75",
    "parken-luebeck-Marlesgrube-Parkplatz-Marlesgrube-Parkplatz-Lubeck": "parken-luebeck-21",
    "parken-luebeck-Mowenstein-Parkplatz-Mowenstein-Parkplatz-Travemunde": "parken-luebeck-53",
    "parken-luebeck-MuK-Parkplatz-MuK-Parkplatz-Lubeck": "parken-luebeck-46",
    "parken-luebeck-Muhlenbrucke-Parkplatz-Muhlenbrucke-Parkplatz-Lubeck": "parken-luebeck-27",
    "parken-luebeck-Muhlenstrasse-Parkplatz-Muhlenstrasse-Parkplatz-Lubeck": "parken-luebeck-24",
    "parken-luebeck-Musterbahn-Parkplatz-Musterbahn-Parkplatz-Lubeck": "parken-luebeck-26",
    "parken-luebeck-Obertrave-Parkplatz-Strassenrand-Obertrave-Parkplatz-Strassenrand-Lubeck": "parken-luebeck-20",
    "parken-luebeck-Parade-Parkplatz-Parade-Parkplatz-Lubeck": "parken-luebeck-22",
    "parken-luebeck-Paul-Brummer-Strasse-Parkplatz-Paul-Brummer-Strasse-Parkplatz-Travemunde": "parken-luebeck-71",
    "parken-luebeck-Priwall-Parkplatz-Priwall-Parkplatz-Travemunde": "parken-luebeck-68",
    "parken-luebeck-Radisson-Blu-Parkplatz-Radisson-Blu-Parkplatz-Lubeck": "parken-luebeck-47",
    "parken-luebeck-Retteich-Parkplatz-Retteich-Parkplatz-Lubeck": "parken-luebeck-33",
    "parken-luebeck-Roeckstrasse-Parkplatz-Roeckstrasse-Parkplatz-Lubeck": "parken-luebeck-42",
    "parken-luebeck-Rose-Parkplatz-Rose-Parkplatz-Travemunde": "parken-luebeck-69",
    "parken-luebeck-Strandbahnhof-Parkplatz-Strandbahnhof-Parkplatz-Travemunde": "parken-luebeck-56",
    "parken-luebeck-Trelleborgallee-Parkplatz-Trelleborgallee-Parkplatz-Travemunde": "parken-luebeck-60",
    "parken-luebeck-Vogteistrasse-Parkplatz-Vogteistrasse-Parkplatz-Travemunde": "parken-luebeck-62",
    "parken-luebeck-Wallstrasse-Parkplatz-Wallstrasse-Parkplatz-Lubeck": "parken-luebeck-29",

    # Mop-up of 2026-09-26: the same renames, found by scanning for readings
    # whose place_id has no lots_meta row and matching each to the existing
    # garage of the same source by name (reviewed by hand; hospital, Parkhaus-
    # vs Tiefgarage and combined-row matches rejected). Historical readings
    # were re-keyed by the merge (log: /data/rename_merge_log_2026-09-26.json);
    # these entries keep future archive days landing on the same garages.
    "bonn-bcp-parken-hauptbahnhof": "bonn-bcp-parken-bahnhof",
    "dresden-parken-GALERIA-Karstadt-Kaufhof": "dresden-parken-Karstadt",
    "ffh-parken-frankfurt-MyZeil-PalaisQuartier": "ffh-parken-frankfurt-MyZeil",
    "ffh-parken-kassel-Galeria": "ffh-parken-kassel-Galeria-Kaufhof",
    "ffh-parken-mannheim-C1-Hauptverwaltung-MPB-Parkhaus": "ffh-parken-mannheim-C1",
    "ffh-parken-mannheim-Collini-Center-Mulde-Parkplatz": "ffh-parken-mannheim-Mulde-Collini-Center",
    "hanau-neu-erleben-parken-Parkhaus-Congress-park": "hanau-neu-erleben-parken-Parkhaus-Congress-Park",
    "hanau-neu-erleben-parken-Parkhaus-Nuernberger-Strasse": "hanau-neu-erleben-parken-Parkhaus-Nurnberger-Strasse",
    "hanau-neu-erleben-parken-Tiefgarage-Klinikum-Sued": "hanau-neu-erleben-parken-Tiefgarage-Klinikum-Sud",
    "oldenburg-service-parken-City-Parkhaus-Staulinie": "oldenburg-service-parken-City",
    "oldenburg-service-parken-Parkhaus-Alter-Stadthafen-Cinemaxx": "oldenburg-service-parken-Cinemaxx",
    "oldenburg-service-parken-Parkhaus-Am-Waffenplatz": "oldenburg-service-parken-Waffenplatz",
    "oldenburg-service-parken-Parkhaus-Bahnhof-ZOB": "oldenburg-service-parken-Hbf-ZOB",
    "oldenburg-service-parken-Parkhaus-Galeria-Kaufhof": "oldenburg-service-parken-Galeria-Kaufhof",
    "oldenburg-service-parken-Parkhaus-Heiligengeist-Hoefe": "oldenburg-service-parken-Heiligengeist-Hoefe",
    "oldenburg-service-parken-Parkhaus-Schlosshoefe": "oldenburg-service-parken-Schlosshoefe",
    "oldenburg-service-parken-Parkhaus-Theatergarage": "oldenburg-service-parken-Theatergarage",
    "oldenburg-service-parken-Parkplatz-Pferdemarkt": "oldenburg-service-parken-Pferdemarkt",
    "oldenburg-service-parken-Parkplatz-Theaterwall": "oldenburg-service-parken-Theaterwall",
    "paderborn-parken-P6-Liborigalerie": "paderborn-parken-P6-Libori-Galerie",
    "paderborn-parken-P7-Liboriberg": "paderborn-parken-P7-Le-Mans-Wall-Liboriberg",
    "parken-in-bochum-P8-Konrad-Adenauer-Platz-Bermuda3Eck": "parken-in-bochum-P8-Konrad-Adenauer-Platz",
    "parken-in-bochum-PH-Bochumer-Fenster": "parken-in-bochum-PF-Bochumer-Fenster",
    "parken-in-bochum-PH-Massenbergstrasse": "parken-in-bochum-PM-Massenbergstrasse",
    "parken-mannheim-Hauptbahnhof-P3-Parkhaus": "parken-mannheim-Hauptbahnhof-P3-P4-Parkhaus",
    "sw-bielefeld-parken-Tiefgarage-Marktpassage-nicht-fur-gasbetriebene-Fahrzeuge": "sw-bielefeld-parken-Tiefgarage-Marktpassage",
    "vmz-bremen-parken-Am-Bahnhof": "vmz-bremen-parken-Parkhaus-Am-Bahnhof",
    "vmz-bremen-parken-Am-Brill": "vmz-bremen-parken-Parkhaus-Am-Brill",
    "vmz-bremen-parken-Am-Dom": "vmz-bremen-parken-Parkhaus-Am-Dom",
    "vmz-bremen-parken-Am-Sedanplatz": "vmz-bremen-parken-Parkhaus-Am-Sedanplatz",
    "vmz-bremen-parken-Am-Vegesacker-Hafen": "vmz-bremen-parken-Parkhaus-Am-Vegesacker-Hafen",
    "vmz-bremen-parken-Am-Wall": "vmz-bremen-parken-Parkhaus-Am-Wall",
    "vmz-bremen-parken-Aumunder-Markplatz": "vmz-bremen-parken-Parkhaus-Aumunder-Markplatz",
    "vmz-bremen-parken-Burgerweide": "vmz-bremen-parken-Parkplatz-Burgerweide",
    "vmz-bremen-parken-Burgerweide-Klangbogen": "vmz-bremen-parken-Parkplatz-Burgerweide-Klangbogen",
    "vmz-bremen-parken-City-Gate": "vmz-bremen-parken-Parkhaus-City-Gate",
    "vmz-bremen-parken-Herdentor-Rembertiring": "vmz-bremen-parken-Parkhaus-Herdentor-Rembertiring",
    "vmz-bremen-parken-Hillmannplatz": "vmz-bremen-parken-Parkhaus-Hillmannplatz",
    "vmz-bremen-parken-Katharinenklosterhof": "vmz-bremen-parken-Parkhaus-Katharinenklosterhof",
    "vmz-bremen-parken-Mitte": "vmz-bremen-parken-Parkhaus-Mitte",
    "vmz-bremen-parken-Ostertor-Kulturmeile": "vmz-bremen-parken-Parkhaus-Ostertor-Kulturmeile",
    "vmz-bremen-parken-Pressehaus": "vmz-bremen-parken-Parkhaus-Pressehaus",
    "vmz-bremen-parken-Rovekamp-Musicalth": "vmz-bremen-parken-Parkhaus-Rovekamp-Musicalth",
    "vmz-bremen-parken-Sagerstr": "vmz-bremen-parken-Parkplatz-Sagerstr",
    "vmz-bremen-parken-Stephani": "vmz-bremen-parken-Parkhaus-Stephani",
}


# These legacy archive source_ids receive live occupancy writes from
# scrapers/adapters/mobidata_bw_existing.py's Mannheim/Karlsruhe/Ulm
# adapters, which write into the *existing* place_ids under their original
# archive source_id rather than a new one of their own -- so they never
# show up as their own entry in scraper_runs.adapter. Found the hard way:
# without this, the seed query below picks up today's date from these and
# corrupts the seed for every genuinely archive-only source, since it's one
# aggregate MAX() over the whole set (confirmed on production: seeded
# 2026-09-24 instead of 2026-08-12, silently finding nothing to import).
LIVE_WRITES_UNDER_LEGACY_SOURCE_ID = {"ffh-parken", "parken-mannheim", "karlsruhe-parken", "parken-in-ulm"}


# Archive source_ids now fed directly by an adapter of the same name (see
# scrapers/adapters/{konstanz,potsdam,dortmund,muenster,apag}_live.py).
# Their archive columns are skipped so a source never gets two interleaved
# streams of readings, even if the upstream archive scraper revives.
ADAPTER_OWNED_SOURCE_IDS = (
    "konstanz-parken",
    "mobil-potsdam-parken",
    "digistadt-dortmund-parken",
    "stadt-muenster-parken",
    "apag-parken",
)
ADAPTER_OWNED_PREFIXES = tuple(s + "-" for s in ADAPTER_OWNED_SOURCE_IDS)


def _seed_last_imported_day(conn: sqlite3.Connection) -> str:
    """First run: seed from the latest date already covered by archive-derived
    sources -- anything with no scraper_runs entries, i.e. not a live adapter,
    and not one of the legacy source_ids a live adapter writes into instead."""
    placeholders = ",".join("?" * len(LIVE_WRITES_UNDER_LEGACY_SOURCE_ID))
    row = conn.execute(
        f"""SELECT MAX(SUBSTR(h.ts, 1, 10)) FROM historical_observations h
           JOIN lots_meta m ON m.place_id = h.place_id
           WHERE m.source_id NOT IN (SELECT DISTINCT adapter FROM scraper_runs)
             AND m.source_id NOT IN ({placeholders})""",
        tuple(LIVE_WRITES_UNDER_LEGACY_SOURCE_ID),
    ).fetchone()
    if row and row[0]:
        return row[0]
    return (ARCHIVE_FIRST_DAY - timedelta(days=1)).isoformat()


def _import_day_file(conn: sqlite3.Connection, day_file: Path) -> int:
    last_seen: dict[tuple[str, str], tuple[str, int]] = {}
    with open(day_file, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header or header[0] != "timestamp":
            print(f"  ! skipping malformed file {day_file}", file=sys.stderr)
            return 0
        place_ids = header[1:]
        for row in reader:
            if not row:
                continue
            ts = row[0]
            hour_prefix = ts[:13]
            for place_id, value in zip(place_ids, row[1:]):
                if value and not place_id.startswith(ADAPTER_OWNED_PREFIXES):
                    place_id = RENAME_MAP.get(place_id, place_id)
                    # overwritten each time a later reading lands in the same hour,
                    # matching import_historical.py's own hourly-bucketing rule
                    last_seen[(place_id, hour_prefix)] = (ts, int(value))
    rows = [(place_id, ts, value) for (place_id, _hp), (ts, value) in last_seen.items()]
    conn.executemany("INSERT INTO historical_observations (place_id, ts, free) VALUES (?, ?, ?)", rows)
    conn.commit()
    return len(rows)


def sync() -> None:
    _pull_archive()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(STATE_SCHEMA)

    row = conn.execute("SELECT last_imported_day FROM archive_sync_state WHERE id = 1").fetchone()
    if row:
        last_imported_day = row[0]
    else:
        last_imported_day = _seed_last_imported_day(conn)
        conn.execute("INSERT INTO archive_sync_state (id, last_imported_day) VALUES (1, ?)", (last_imported_day,))
        conn.commit()
        print(f"[sync_archive] seeded last_imported_day = {last_imported_day}")

    cursor = datetime.strptime(last_imported_day, "%Y-%m-%d").date() + timedelta(days=1)
    today = date.today()
    total_rows = 0
    total_days = 0

    while cursor <= today:
        day_file = _day_file_for(cursor)
        if not day_file.exists():
            break  # archive hasn't published this day yet -- stop, retry next run
        n = _import_day_file(conn, day_file)
        total_rows += n
        total_days += 1
        conn.execute("UPDATE archive_sync_state SET last_imported_day = ? WHERE id = 1", (cursor.isoformat(),))
        conn.commit()
        cursor += timedelta(days=1)

    if total_days:
        conn.execute(
            """UPDATE lots_meta SET last_observed_ts = (
                   SELECT MAX(ts) FROM historical_observations h WHERE h.place_id = lots_meta.place_id
               )
               WHERE place_id IN (
                   SELECT DISTINCT place_id FROM historical_observations WHERE ts >= ?
               )""",
            (last_imported_day,),
        )
        conn.commit()

    conn.close()
    print(f"[sync_archive] {total_days} new day(s), {total_rows} rows")


if __name__ == "__main__":
    sync()
