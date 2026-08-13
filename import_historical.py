#!/usr/bin/env python3
"""One-time bulk import of the defgsus/parking-data historical archive into parking.db.

Imports meta-data.csv into `lots_meta` and every daily csv/YYYY/YYYY-MM/YYYY-MM-DD.csv
file into `historical_observations`, keeping only the sparse recorded values (no
forward-fill materialization) so storage stays proportional to actual readings.
"""

import csv
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
ARCHIVE = Path(os.environ.get("PARKING_ARCHIVE_PATH", ROOT / "parking-data-archive"))
DB_PATH = Path(os.environ.get("PARKING_DB_PATH", ROOT / "data" / "parking.db"))
BATCH_SIZE = 50_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS lots_meta (
    place_id TEXT PRIMARY KEY,
    place_name TEXT,
    city_name TEXT,
    num_all INTEGER,
    address TEXT,
    latitude REAL,
    longitude REAL,
    place_url TEXT,
    source_id TEXT,
    source_web_url TEXT
);

CREATE TABLE IF NOT EXISTS historical_observations (
    place_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    free INTEGER NOT NULL
);
"""


def import_meta(conn: sqlite3.Connection) -> None:
    with open(ARCHIVE / "meta-data.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [
            (
                r["place_id"],
                r["place_name"],
                r["city_name"],
                int(r["num_all"]) if r.get("num_all") else None,
                r.get("address"),
                float(r["latitude"]) if r.get("latitude") else None,
                float(r["longitude"]) if r.get("longitude") else None,
                r.get("place_url"),
                r.get("source_id"),
                r.get("source_web_url"),
            )
            for r in reader
        ]
    conn.executemany(
        """INSERT INTO lots_meta
           (place_id, place_name, city_name, num_all, address, latitude, longitude, place_url, source_id, source_web_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(place_id) DO UPDATE SET
             place_name=excluded.place_name, city_name=excluded.city_name, num_all=excluded.num_all,
             address=excluded.address, latitude=excluded.latitude, longitude=excluded.longitude,
             place_url=excluded.place_url, source_id=excluded.source_id, source_web_url=excluded.source_web_url""",
        rows,
    )
    conn.commit()
    print(f"lots_meta: {len(rows)} rows")


def iter_day_files():
    for year_dir in sorted(ARCHIVE.glob("csv/*")):
        if not year_dir.is_dir():
            continue
        for month_dir in sorted(year_dir.glob("*")):
            if not month_dir.is_dir():
                continue
            for day_file in sorted(month_dir.glob("*.csv")):
                yield day_file


def import_observations(conn: sqlite3.Connection) -> None:
    buffer = []
    total_rows = 0
    total_files = 0
    start = time.time()

    def flush():
        nonlocal buffer
        if buffer:
            conn.executemany(
                "INSERT INTO historical_observations (place_id, ts, free) VALUES (?, ?, ?)",
                buffer,
            )
            buffer = []

    for day_file in iter_day_files():
        with open(day_file, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header or header[0] != "timestamp":
                print(f"  ! skipping malformed file {day_file}", file=sys.stderr)
                continue
            place_ids = header[1:]
            for row in reader:
                if not row:
                    continue
                ts = row[0]
                for place_id, value in zip(place_ids, row[1:]):
                    if value:
                        buffer.append((place_id, ts, int(value)))
                        if len(buffer) >= BATCH_SIZE:
                            total_rows += len(buffer)
                            flush()

        total_files += 1
        if total_files % 100 == 0:
            flush()
            conn.commit()
            elapsed = time.time() - start
            print(f"  {total_files}/2332 files, {total_rows} rows, {elapsed:.0f}s elapsed", flush=True)

    flush()
    conn.commit()
    elapsed = time.time() - start
    print(f"historical_observations: {total_files} files, {total_rows} rows in {elapsed:.0f}s")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.executescript(SCHEMA)

    import_meta(conn)
    import_observations(conn)

    print("building indexes...")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_place_ts ON historical_observations (place_id, ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_ts ON historical_observations (ts)")
    conn.commit()
    conn.close()
    print("done")


if __name__ == "__main__":
    main()
