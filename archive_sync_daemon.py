#!/usr/bin/env python3
"""Run sync_archive.sync() forever, once a day.

Daily matches the archive's own update cadence (one new day-file per day) --
checking more often than that would just find nothing new every time.
"""

import sqlite3
import time
import traceback

import sync_archive
from sync_archive import DB_PATH

INTERVAL_SECONDS = 24 * 3600


def wait_for_real_db(poll_seconds: int = 10) -> None:
    """On a fresh volume, entrypoint.sh's bootstrap step also clones the
    archive (to run import_historical.py) at the same time this daemon
    starts -- racing sync_archive's own clone-if-missing against it would
    corrupt the checkout. Same guard scraper_daemon.py uses: wait for the
    real bootstrap to finish and lots_meta to be populated first."""
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
        print("archive_sync_daemon: waiting for bootstrap to finish before starting...", flush=True)
        time.sleep(poll_seconds)


def main() -> None:
    wait_for_real_db()
    while True:
        try:
            sync_archive.sync()
        except Exception:
            traceback.print_exc()
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
