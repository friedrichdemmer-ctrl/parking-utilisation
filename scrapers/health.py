"""Health queries over scraper_runs -- the thing the original archive never
had, which is exactly why it took years to notice most of it had gone silent.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone


def adapter_status(conn: sqlite3.Connection, adapter: str) -> dict:
    last_success = conn.execute(
        "SELECT run_at, records_written FROM scraper_runs WHERE adapter=? AND status='success' ORDER BY run_at DESC LIMIT 1",
        (adapter,),
    ).fetchone()
    last_error = conn.execute(
        "SELECT run_at, error_message FROM scraper_runs WHERE adapter=? AND status='error' ORDER BY run_at DESC LIMIT 1",
        (adapter,),
    ).fetchone()
    recent_error_count = conn.execute(
        "SELECT COUNT(*) FROM scraper_runs WHERE adapter=? AND status='error' AND run_at > ?",
        (adapter, (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")),
    ).fetchone()[0]
    return {
        "adapter": adapter,
        "last_success_at": last_success[0] if last_success else None,
        "last_success_records": last_success[1] if last_success else None,
        "last_error_at": last_error[0] if last_error else None,
        "last_error_message": last_error[1] if last_error else None,
        "errors_last_24h": recent_error_count,
    }


def all_adapter_statuses(conn: sqlite3.Connection) -> list[dict]:
    adapters = [r[0] for r in conn.execute("SELECT DISTINCT adapter FROM scraper_runs").fetchall()]
    return [adapter_status(conn, a) for a in adapters]


def is_stale(status: dict, expected_interval_seconds: int, grace_multiplier: float = 3.0) -> bool:
    """Flag an adapter that hasn't succeeded within `grace_multiplier` x its own interval."""
    if status["last_success_at"] is None:
        return True
    last = datetime.fromisoformat(status["last_success_at"])
    return datetime.now(timezone.utc) - last > timedelta(seconds=expected_interval_seconds * grace_multiplier)
