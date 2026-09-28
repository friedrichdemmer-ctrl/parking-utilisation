#!/usr/bin/env python3
"""Daily check for garages whose feed has quietly stopped or frozen.

Written after finding by hand, on 2026-09-26/27, that Reutlingen had been
re-reporting its 2020 values for six years, 11 Hamburg garages had never
changed value, and Pamplona's feed had stopped -- none of which showed as
an error anywhere, because the adapters kept succeeding.

For every garage that reported in the last 30 days:
- "stopped": no reading in the last 3 days (the same window the coverage
  page uses for "live", which also covers the archive-fed German sources'
  1-2 day lag).
- "frozen": still reporting, but the free count has not changed across at
  least 6 readings spanning at least 24 hours. "since" is the time of the
  last reading with a different value (looking back up to 14 days).

Frozen garages are also recorded in frozen_places (scrapers/storage.py):
from then on, readings equal to the frozen value are not stored, so they
stop piling up and the garage drops out of "live" within 3 days; the first
different value clears the entry. Garages already in frozen_places are
reported as frozen without re-checking.

Results replace the feed_health table on each run; scraper_daemon.py runs
this once a day, and /api/feed-health serves it. It never deletes data.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("PARKING_DB_PATH", Path(__file__).parent / "data" / "parking.db"))

RECENT_DAYS = 30
STOPPED_AFTER = timedelta(days=3)
FROZEN_MIN_READINGS = 6
FROZEN_MIN_SPAN = timedelta(hours=24)
FROZEN_WINDOW = timedelta(hours=48)
LOOKBACK = timedelta(days=14)

SCHEMA = """CREATE TABLE IF NOT EXISTS feed_health (
    place_id TEXT PRIMARY KEY,
    source_id TEXT,
    place_name TEXT,
    city_name TEXT,
    status TEXT NOT NULL,
    since TEXT,
    detail TEXT,
    checked_at TEXT NOT NULL
)"""


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def check(conn: sqlite3.Connection, now: datetime | None = None) -> tuple[list[tuple], list[tuple]]:
    """(findings for feed_health, newly frozen (place_id, value, since))"""
    now = now or datetime.now(timezone.utc)
    recent = _iso(now - timedelta(days=RECENT_DAYS))
    findings, new_frozen = [], []
    frozen = {r[0]: r for r in conn.execute(
        """SELECT f.place_id, m.source_id, m.place_name, m.city_name, f.value, f.since, m.num_all
           FROM frozen_places f LEFT JOIN lots_meta m ON m.place_id = f.place_id""")}
    for place_id, source_id, name, city, value, since, capacity in frozen.values():
        note = " (= capacity: empty, or not counting)" if capacity and value == capacity else ""
        findings.append((place_id, source_id, name, city, "frozen", since, f"free = {value}{note}; repeats not stored"))
    rows = conn.execute(
        "SELECT place_id, source_id, place_name, city_name, last_observed_ts, num_all FROM lots_meta WHERE last_observed_ts >= ?",
        (recent,),
    ).fetchall()
    for place_id, source_id, name, city, last, capacity in rows:
        if place_id in frozen:
            continue
        last_dt = _parse(last)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        if now - last_dt > STOPPED_AFTER:
            findings.append((place_id, source_id, name, city, "stopped", last, f"last reading {last[:16]}"))
            continue
        window = conn.execute(
            "SELECT ts, free FROM historical_observations WHERE place_id = ? AND ts >= ? ORDER BY ts",
            (place_id, _iso(now - FROZEN_WINDOW)),
        ).fetchall()
        if len(window) < FROZEN_MIN_READINGS or len({f for _, f in window}) != 1:
            continue
        if _parse(window[-1][0]) - _parse(window[0][0]) < FROZEN_MIN_SPAN:
            continue
        value = window[0][1]
        changed = conn.execute(
            "SELECT MAX(ts) FROM historical_observations WHERE place_id = ? AND ts >= ? AND free != ?",
            (place_id, _iso(now - LOOKBACK), value),
        ).fetchone()[0]
        since = changed or f"before {_iso(now - LOOKBACK)[:10]}"
        # all spaces free the whole time can be a genuinely unused site (a
        # ski-lift car park off season) rather than a stuck sensor -- say so
        note = " (= capacity: empty, or not counting)" if capacity and value == capacity else ""
        findings.append((place_id, source_id, name, city, "frozen", since, f"free = {value} in every reading{note}"))
        new_frozen.append((place_id, value, since))
    return findings, new_frozen


def run(conn: sqlite3.Connection) -> int:
    from scrapers.storage import ensure_schema

    ensure_schema(conn)  # frozen_places
    conn.execute(SCHEMA)
    checked_at = _iso(datetime.now(timezone.utc))
    findings, new_frozen = check(conn)
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO frozen_places (place_id, value, since, flagged_at) VALUES (?, ?, ?, ?)",
            [(place_id, value, since, checked_at) for place_id, value, since in new_frozen],
        )
        conn.execute("DELETE FROM feed_health")
        conn.executemany(
            "INSERT INTO feed_health (place_id, source_id, place_name, city_name, status, since, detail, checked_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [f + (checked_at,) for f in findings],
        )
    return len(findings)


CHECK_INTERVAL_SECONDS = 24 * 3600


def run_if_due(conn: sqlite3.Connection) -> None:
    """Daily, logged in scraper_runs as adapter "feed-health" (so it shows on
    the health tab and an empty result still counts as a run)."""
    import traceback

    from scrapers import storage
    from scrapers.runner import _is_due, _last_success_at

    if not _is_due(_last_success_at(conn, "feed-health", "check"), CHECK_INTERVAL_SECONDS):
        return
    try:
        n = run(conn)
        storage.record_run(conn, "feed-health", "check", "success", records_written=n)
        print(f"[feed-health] {n} garages flagged")
    except Exception as exc:
        storage.record_run(conn, "feed-health", "check", "error", error_message=f"{exc}\n{traceback.format_exc()}")
        print(f"[feed-health] FAILED: {exc}")


if __name__ == "__main__":
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA busy_timeout=30000")
    print(f"feed_health: {run(c)} garages flagged")
