#!/usr/bin/env python3
"""Runs registered source adapters forever, each on its own cadence.

Checks every 5 minutes for due adapters rather than sleeping for a fixed
interval, since adapters can have very different cadences (occupancy every
30 min, capacity weekly) -- a single fixed sleep would either waste cycles
or delay whichever adapter has the shortest interval.
"""

import os
import sqlite3
import time
import traceback
from pathlib import Path

from scrapers.registry import ADAPTERS
from scrapers.runner import run_due_adapters

DB_PATH = Path(os.environ.get("PARKING_DB_PATH", Path(__file__).parent / "data" / "parking.db"))
CHECK_INTERVAL_SECONDS = 300


def wait_for_real_db(poll_seconds: int = 10) -> None:
    """sqlite3.connect() silently creates an empty file if DB_PATH doesn't
    exist yet -- if this daemon started that connection before the real
    bootstrap (import_historical.py) ran, entrypoint.sh's "does the DB exist"
    check would see that stub file and skip the real import entirely. Wait
    for lots_meta to actually exist and be populated before touching it.
    """
    while True:
        if DB_PATH.exists():
            try:
                conn = sqlite3.connect(DB_PATH)
                n = conn.execute("SELECT COUNT(*) FROM lots_meta").fetchone()[0]
                conn.close()
                if n > 0:
                    return
            except sqlite3.OperationalError:
                pass  # table doesn't exist yet -- bootstrap still running
        print("scraper_daemon: waiting for bootstrap to finish before starting...", flush=True)
        time.sleep(poll_seconds)


def main() -> None:
    wait_for_real_db()
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("PRAGMA busy_timeout=30000")
            run_due_adapters(conn, ADAPTERS)
            conn.close()
        except Exception:
            traceback.print_exc()
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
