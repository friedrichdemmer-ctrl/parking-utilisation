"""How current a city's occupancy data is, for the city and briefing pages.

Written after finding on 2026-10-07 that six sources had stopped (APAG,
Kaiserslautern, Konstanz, Oldenburg, half of Mannheim, Osnabrück) while
their city pages went on showing the last readings with no sign that they
had stopped arriving. alerts.py pushes a phone alert and feed_health.py
flags single garages, but neither reaches a reader of the site.

A city's data is "stale" when every garage that was reporting has now been
silent for longer than its source allows: 6 hours for a source with a live
adapter, 3 days for one that only arrives through the community archive
(which lags 1-2 days). The same thresholds as alerts.py, so the site and
the alerts agree. A city whose garages have never reported is not stale --
it has no live data at all, which the page already says.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from functools import lru_cache

LIVE_SILENT_AFTER = timedelta(hours=6)
ARCHIVE_SILENT_AFTER = timedelta(days=3)


@lru_cache(maxsize=1)
def _live_sources() -> frozenset[str]:
    from scrapers.registry import ADAPTERS

    return frozenset(a.name for a in ADAPTERS)


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def silent_after(source_id: str | None) -> timedelta:
    return LIVE_SILENT_AFTER if (source_id or "") in _live_sources() else ARCHIVE_SILENT_AFTER


def of_rows(rows, now: datetime | None = None) -> dict | None:
    """rows: (source_id, last_observed_ts) for the garages of one city.

    Returns None when none of them has ever reported; otherwise
    {"last_reading", "stale", "reporting", "silent", "sources"} where
    "sources" names the stopped sources, newest reading first."""
    now = now or datetime.now(timezone.utc)
    seen = [(src, _parse(ts)) for src, ts in rows if ts]
    if not seen:
        return None
    silent = [(src, ts) for src, ts in seen if now - ts > silent_after(src)]
    last = max(ts for _, ts in seen)
    stopped: dict[str, datetime] = {}
    for src, ts in silent:
        stopped[src] = max(ts, stopped.get(src, ts))
    return {
        "last_reading": last.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stale": len(silent) == len(seen),
        "reporting": len(seen) - len(silent),
        "silent": len(silent),
        "sources": [{"source_id": s, "last_reading": t.strftime("%Y-%m-%dT%H:%M:%SZ")}
                    for s, t in sorted(stopped.items(), key=lambda kv: -kv[1].timestamp())],
    }


def of_city(conn: sqlite3.Connection, place_ids) -> dict | None:
    ids = list(place_ids)
    rows: list[tuple[str | None, str | None]] = []
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        rows += conn.execute(
            f"SELECT source_id, last_observed_ts FROM lots_meta WHERE place_id IN ({','.join('?' * len(chunk))})",
            chunk).fetchall()
    return of_rows(rows)
