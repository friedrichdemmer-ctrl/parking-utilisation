"""Writes adapter output into the existing lots_meta / historical_observations
schema, plus a scraper_runs table for health tracking. No adapter touches
sqlite directly -- this is the only place that does.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from scrapers.base import CapacityRecord, OccupancyRecord
from scrapers.util import normalize_name

OVERRIDES_DIR = Path(__file__).resolve().parent.parent / "capacity_overrides"

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
-- Garages whose feed repeats one value (set by feed_health.py). Readings
-- equal to that value are not stored; the first different value clears the
-- entry, so a repaired sensor is picked up automatically.
CREATE TABLE IF NOT EXISTS frozen_places (
    place_id TEXT PRIMARY KEY,
    value INTEGER NOT NULL,
    since TEXT,
    flagged_at TEXT NOT NULL
);
-- Capacity changes over time (see write_capacity / capacity_timeline).
-- lots_meta.num_all stays the current figure; a row here records the figure
-- in force from valid_from ("" = from the start of the history).
CREATE TABLE IF NOT EXISTS capacity_history (
    place_id TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    num_all INTEGER NOT NULL,
    PRIMARY KEY (place_id, valid_from)
);
"""


def frozen_values(conn: sqlite3.Connection) -> dict[str, int]:
    conn.executescript(SCHEMA)
    return dict(conn.execute("SELECT place_id, value FROM frozen_places").fetchall())


def drop_frozen_repeats(conn: sqlite3.Connection, rows: list[tuple[str, str, int]]) -> list[tuple[str, str, int]]:
    """(place_id, ts, free) rows minus repeats of a frozen value; a different
    value un-freezes its garage. Used by write_occupancy and sync_archive."""
    frozen = frozen_values(conn)
    if not frozen:
        return rows
    kept, recovered = [], set()
    for row in rows:
        value = frozen.get(row[0])
        if value is None:
            kept.append(row)
        elif row[2] != value:
            recovered.add(row[0])
            kept.append(row)
    if recovered:
        conn.executemany("DELETE FROM frozen_places WHERE place_id = ?", [(p,) for p in recovered])
    return kept


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


@lru_cache(maxsize=1)
def capacity_corrections() -> dict[str, int]:
    """replace=yes rows of capacity_overrides/*.csv -- capacities known to be
    wrong at source. Applied on every capacity write, so a live adapter's
    weekly refresh does not put the feed's wrong figure back."""
    corrections = {}
    for path in sorted(OVERRIDES_DIR.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("replace") == "yes":
                    corrections[row["place_id"]] = int(row["num_all"])
    return corrections


def _record_capacity_changes(conn: sqlite3.Connection, new: dict[str, int]) -> None:
    """Before lots_meta is overwritten: for each garage whose capacity changes,
    keep the old figure as in force until now (from the start, if this is
    its first recorded change) and the new one from now on. Without this a
    feed that starts counting only part of a garage (Düsseldorf PH 37: 1,081
    -> 200 short-stay spaces when the city feed replaced the archive) would
    re-scale years of past readings to the new figure."""
    conn.executescript(SCHEMA)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    current = {}
    ids = list(new)
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        current.update(conn.execute(
            f"SELECT place_id, num_all FROM lots_meta WHERE num_all IS NOT NULL AND place_id IN ({','.join('?' * len(chunk))})",
            chunk).fetchall())
    for place_id, cap in new.items():
        old = current.get(place_id)
        if old is None or old == cap:
            continue
        conn.execute("INSERT OR IGNORE INTO capacity_history (place_id, valid_from, num_all) VALUES (?, '', ?)", (place_id, old))
        conn.execute("INSERT OR REPLACE INTO capacity_history (place_id, valid_from, num_all) VALUES (?, ?, ?)", (place_id, now, cap))


def capacity_timeline(conn: sqlite3.Connection) -> dict[str, list[tuple[str, int]]]:
    """{place_id: [(valid_from, num_all), ...] sorted} for garages whose
    capacity has changed; replace=yes corrections override the whole
    history (the figure was always wrong). Garages not listed use
    lots_meta.num_all throughout -- see capacity_at()."""
    out: dict[str, list[tuple[str, int]]] = {}
    # reports open the database read-only, so check rather than create
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'capacity_history'").fetchone():
        for place_id, valid_from, cap in conn.execute(
                "SELECT place_id, valid_from, num_all FROM capacity_history ORDER BY place_id, valid_from"):
            out.setdefault(place_id, []).append((valid_from, cap))
    for place_id, cap in capacity_corrections().items():
        out[place_id] = [("", cap)]
    return out


def capacity_at(timeline: list[tuple[str, int]] | None, current: int, ts: str) -> int:
    """Capacity in force at ts (ISO string, compared as text), given a
    garage's timeline from capacity_timeline() and its current num_all."""
    if not timeline:
        return current
    cap = timeline[0][1]
    for valid_from, value in timeline:
        if valid_from <= ts:
            cap = value
        else:
            break
    return cap


def write_capacity(conn: sqlite3.Connection, records: list[CapacityRecord]) -> int:
    fixed = capacity_corrections()
    _record_capacity_changes(conn, {r.place_id: fixed.get(r.place_id, r.num_all) for r in records if r.num_all})
    rows = [
        (r.place_id, r.place_name, r.city_name, fixed.get(r.place_id, r.num_all), r.address, r.latitude, r.longitude, r.place_url, r.source_id, r.source_web_url)
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
    # A source that stops updating keeps re-serving its last reading with the
    # same timestamp; skipping (place_id, ts) pairs already stored keeps those
    # repeats out of the history and makes the returned count 0 for a frozen feed.
    seen: set[tuple[str, str]] = set()
    fresh = []
    for r in records:
        key = (r.place_id, r.ts)
        if key in seen:
            continue
        seen.add(key)
        if conn.execute(
            "SELECT 1 FROM historical_observations WHERE place_id = ? AND ts = ? LIMIT 1", key
        ).fetchone():
            continue
        fresh.append(r)
    rows = drop_frozen_repeats(conn, [(r.place_id, r.ts, r.free) for r in fresh])
    conn.executemany(
        "INSERT INTO historical_observations (place_id, ts, free) VALUES (?, ?, ?)", rows
    )
    # keep last_observed_ts current for the freshness UI without a full backfill pass
    conn.executemany(
        "UPDATE lots_meta SET last_observed_ts = ? WHERE place_id = ? AND (last_observed_ts IS NULL OR last_observed_ts < ?)",
        [(ts, place_id, ts) for place_id, ts, _free in rows],
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
    # Best-effort: this runs from exception handlers too, so a lock here
    # (another daemon writing at the same moment) must never mask the
    # original error by raising a new one -- log and move on instead.
    try:
        conn.execute(
            """INSERT INTO scraper_runs (adapter, kind, run_at, status, records_written, records_rejected, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (adapter, kind, datetime.now(timezone.utc).isoformat(timespec="seconds"), status, records_written, records_rejected, error_message),
        )
        conn.commit()
    except sqlite3.OperationalError as exc:
        print(f"record_run: could not log {adapter}/{kind}/{status} ({exc}); continuing")
