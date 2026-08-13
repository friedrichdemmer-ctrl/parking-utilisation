#!/usr/bin/env python3
"""Re-cluster historical_observations by (place_id, ts) so per-garage lookups are sequential disk reads."""

import os
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(os.environ.get("PARKING_DB_PATH", Path(__file__).parent / "data" / "parking.db"))


def main():
    # Default to disk-backed sorting so this runs on modest hosts (~200MB cache);
    # set RECLUSTER_CACHE_KB / RECLUSTER_TEMP_STORE=MEMORY for a faster in-memory
    # sort on a machine with enough RAM (used ~7.6GB RSS locally at temp_store=MEMORY).
    cache_kb = int(os.environ.get("RECLUSTER_CACHE_KB", "200000"))
    temp_store = os.environ.get("RECLUSTER_TEMP_STORE", "FILE")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(f"PRAGMA temp_store={temp_store}")
    conn.execute(f"PRAGMA cache_size=-{cache_kb}")

    t0 = time.time()
    print("dropping old indexes...")
    conn.execute("DROP INDEX IF EXISTS idx_hist_place_ts")
    conn.execute("DROP INDEX IF EXISTS idx_hist_ts")

    print("creating sorted copy...")
    conn.execute("CREATE TABLE historical_observations_sorted (place_id TEXT NOT NULL, ts TEXT NOT NULL, free INTEGER NOT NULL)")
    conn.execute(
        """INSERT INTO historical_observations_sorted (place_id, ts, free)
           SELECT place_id, ts, free FROM historical_observations ORDER BY place_id, ts"""
    )
    conn.commit()
    print(f"sorted copy done in {time.time()-t0:.0f}s")

    print("swapping tables...")
    conn.execute("DROP TABLE historical_observations")
    conn.execute("ALTER TABLE historical_observations_sorted RENAME TO historical_observations")
    conn.commit()

    print("rebuilding indexes...")
    conn.execute("CREATE INDEX idx_hist_place_ts ON historical_observations (place_id, ts)")
    conn.execute("CREATE INDEX idx_hist_ts ON historical_observations (ts)")
    conn.commit()
    print(f"indexes done, total {time.time()-t0:.0f}s")

    print("vacuuming to reclaim space...")
    conn.execute("VACUUM")
    print(f"all done in {time.time()-t0:.0f}s")
    conn.close()


if __name__ == "__main__":
    main()
