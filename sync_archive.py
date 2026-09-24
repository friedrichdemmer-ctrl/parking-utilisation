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


def _seed_last_imported_day(conn: sqlite3.Connection) -> str:
    """First run: seed from the latest date already covered by archive-derived
    sources -- anything with no scraper_runs entries, i.e. not a live adapter."""
    row = conn.execute(
        """SELECT MAX(SUBSTR(h.ts, 1, 10)) FROM historical_observations h
           JOIN lots_meta m ON m.place_id = h.place_id
           WHERE m.source_id NOT IN (SELECT DISTINCT adapter FROM scraper_runs)"""
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
                if value:
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
