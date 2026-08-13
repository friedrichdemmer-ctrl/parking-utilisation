#!/usr/bin/env python3
"""Apply hand-researched capacity figures for garages the archive never captured.

The defgsus/parking-data archive's Köln scraper (koeln-apps-parken) never recorded
total capacity, only free-space counts, so those garages had no way to compute a
utilisation percentage despite having years of historical observations. Capacity
was sourced from each garage's public detail page at koeln.de/apps/parken/parkhaus/<slug>
(see capacity_overrides/koeln_raw_scrape.json for the raw scrape and koeln.csv for
the place_id mapping). Safe to re-run: only fills in num_all, never overwrites an
existing value.
"""

import csv
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = Path(os.environ.get("PARKING_DB_PATH", ROOT / "data" / "parking.db"))
OVERRIDES_DIR = ROOT / "capacity_overrides"


def apply_overrides(conn: sqlite3.Connection) -> None:
    for csv_path in sorted(OVERRIDES_DIR.glob("*.csv")):
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = [(row["place_id"], int(row["num_all"])) for row in csv.DictReader(f)]
        cur = conn.executemany(
            "UPDATE lots_meta SET num_all = ? WHERE place_id = ? AND num_all IS NULL",
            [(num_all, place_id) for place_id, num_all in rows],
        )
        conn.commit()
        print(f"{csv_path.name}: {len(rows)} rows in file, {cur.rowcount} applied (rest already had a value)")


def main():
    conn = sqlite3.connect(DB_PATH)
    apply_overrides(conn)
    conn.close()


if __name__ == "__main__":
    main()
