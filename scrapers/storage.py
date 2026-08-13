"""Writes adapter output into the existing lots_meta / historical_observations
schema, plus a scraper_runs table for health tracking. No adapter touches
sqlite directly -- this is the only place that does.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord
from scrapers.util import normalize_name

SCHEMA = """
CREATE TABLE IF NOT EXISTS scraper_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    adapter TEXT NOT NULL,
    kind TEXT NOT NULL,           -- 'capacity' | 'occupancy'
    run_at TEXT NOT NULL,
    status TEXT NOT NULL,         -- 'success' | 'error'
    records_written INTEGER DEFAULT 0,
    records_rejected INTEGER DEFAULT 0,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_scraper_runs_adapter_time ON scraper_runs (adapter, run_at);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def known_garages_for_source(conn: sqlite3.Connection, source_id: str) -> dict[str, str]:
    """normalized place_name -> place_id, for every garage already on file under this source_id."""
    rows = conn.execute(
        "SELECT place_id, place_name FROM lots_meta WHERE source_id = ?", (source_id,)
    ).fetchall()
    return {normalize_name(name): place_id for place_id, name in rows}


def known_capacities_for_source(conn: sqlite3.Connection, source_id: str) -> dict[str, int]:
    rows = conn.execute(
        "SELECT place_id, num_all FROM lots_meta WHERE source_id = ? AND num_all IS NOT NULL", (source_id,)
    ).fetchall()
    return {place_id: num_all for place_id, num_all in rows}


def write_capacity(conn: sqlite3.Connection, records: list[CapacityRecord]) -> int:
    rows = [
        (r.place_id, r.place_name, r.city_name, r.num_all, r.address, r.latitude, r.longitude, r.place_url, r.source_id, r.source_web_url)
        for r in records
    ]
    conn.executemany(
        """INSERT INTO lots_meta
           (place_id, place_name, city_name, num_all, address, latitude, longitude, place_url, source_id, source_web_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(place_id) DO UPDATE SET
             place_name=excluded.place_name, city_name=excluded.city_name, num_all=excluded.num_all,
             address=excluded.address, latitude=excluded.latitude, longitude=excluded.longitude,
             place_url=excluded.place_url, source_web_url=excluded.source_web_url""",
        rows,
    )
    conn.commit()
    return len(rows)


def write_occupancy(conn: sqlite3.Connection, records: list[OccupancyRecord]) -> int:
    rows = [(r.place_id, r.ts, r.free) for r in records]
    conn.executemany(
        "INSERT INTO historical_observations (place_id, ts, free) VALUES (?, ?, ?)", rows
    )
    # keep last_observed_ts current for the freshness UI without a full backfill pass
    conn.executemany(
        "UPDATE lots_meta SET last_observed_ts = ? WHERE place_id = ? AND (last_observed_ts IS NULL OR last_observed_ts < ?)",
        [(r.ts, r.place_id, r.ts) for r in records],
    )
    conn.commit()
    return len(rows)


def record_run(
    conn: sqlite3.Connection,
    adapter: str,
    kind: str,
    status: str,
    records_written: int = 0,
    records_rejected: int = 0,
    error_message: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO scraper_runs (adapter, kind, run_at, status, records_written, records_rejected, error_message)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (adapter, kind, datetime.now(timezone.utc).isoformat(timespec="seconds"), status, records_written, records_rejected, error_message),
    )
    conn.commit()
