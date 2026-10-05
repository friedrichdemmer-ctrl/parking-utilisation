#!/usr/bin/env python3
"""Phone push alerts via ntfy (https://ntfy.sh) when a source goes quiet,
plus a weekly digest.

Written after Aachen (APAG) and Konstanz went silent on 2026-09-28/30 and
were only noticed a week later on request. feed_health.py flags single
garages once a day; this watches whole sources, hourly:

- A source is "down" when at least half of its active garages (a reading in
  the last 30 days, not suppressed as frozen) have had no reading for
  LIVE_SILENT_AFTER (sources with a live adapter) or ARCHIVE_SILENT_AFTER
  (sources that only arrive via the community archive, which lags 1-2 days).
- One push lists the sources that newly went down; another lists those
  that came back. State is kept in the alert_state table, so each change is
  pushed once.
- Every Monday a digest summarises feed health and links the live reports.

Disabled unless the NTFY_TOPIC environment variable (a Fly secret) is set.
`python3 alerts.py --dry-run` prints what would be sent without sending.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("PARKING_DB_PATH", Path(__file__).parent / "data" / "parking.db"))
NTFY_URL = os.environ.get("NTFY_URL", "https://ntfy.sh")
APP_URL = "https://parking-utilisation.fly.dev"

LIVE_SILENT_AFTER = timedelta(hours=6)
ARCHIVE_SILENT_AFTER = timedelta(days=3)
ACTIVE_DAYS = 30
DOWN_SHARE = 0.5
# sources that are not live feeds, so silence is normal: Parkraumwende
# München is a volunteer-curated catalogue whose free counts change rarely
NEVER_ALERT = {"parkraumwende-muenchen"}
CHECK_INTERVAL_SECONDS = 3600
DIGEST_WEEKDAY = 0  # Monday
DIGEST_HOUR_UTC = 6

SCHEMA = """CREATE TABLE IF NOT EXISTS alert_state (
    source_id TEXT PRIMARY KEY,
    since TEXT,
    silent INTEGER,
    active INTEGER,
    alerted_at TEXT NOT NULL
)"""


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def down_sources(conn: sqlite3.Connection, now: datetime | None = None) -> dict[str, tuple[int, int, str]]:
    """{source_id: (silent garages, active garages, last reading of the silent ones)}"""
    from scrapers.registry import ADAPTERS
    from sync_archive import DEAD_ARCHIVE_SOURCE_IDS

    now = now or datetime.now(timezone.utc)
    live = {a.name for a in ADAPTERS}
    by_source: dict[str, list[datetime]] = {}
    for source_id, last in conn.execute(
        """SELECT m.source_id, m.last_observed_ts FROM lots_meta m
           WHERE m.last_observed_ts >= ? AND m.place_id NOT IN (SELECT place_id FROM frozen_places)""",
        (_iso(now - timedelta(days=ACTIVE_DAYS)),),
    ):
        if source_id and source_id not in DEAD_ARCHIVE_SOURCE_IDS and source_id not in NEVER_ALERT:
            by_source.setdefault(source_id, []).append(_parse(last))
    down = {}
    for source_id, lasts in by_source.items():
        limit = now - (LIVE_SILENT_AFTER if source_id in live else ARCHIVE_SILENT_AFTER)
        silent = [t for t in lasts if t < limit]
        if silent and len(silent) / len(lasts) >= DOWN_SHARE:
            down[source_id] = (len(silent), len(lasts), _iso(max(silent))[:16].replace("T", " "))
    return down


def _cities(conn: sqlite3.Connection, source_id: str) -> str:
    names = [r[0] for r in conn.execute(
        "SELECT city_name FROM lots_meta WHERE source_id = ? AND city_name IS NOT NULL GROUP BY city_name ORDER BY COUNT(*) DESC LIMIT 3",
        (source_id,))]
    return ", ".join(names)


def send(title: str, message: str, tags: list[str], priority: int = 3, dry_run: bool = False) -> None:
    topic = os.environ.get("NTFY_TOPIC")
    if dry_run or not topic:
        print(f"[alerts]{' (dry run)' if dry_run else ' (NTFY_TOPIC not set)'} {title}\n{message}\n")
        return
    body = json.dumps({"topic": topic, "title": title, "message": message, "tags": tags,
                       "priority": priority, "click": APP_URL}).encode()
    req = urllib.request.Request(NTFY_URL, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "parking-utilisation-alerts"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()


def check_outages(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    conn.execute(SCHEMA)
    now = datetime.now(timezone.utc)
    down = down_sources(conn, now)
    before = {r[0]: r for r in conn.execute("SELECT source_id, since, silent, active, alerted_at FROM alert_state")}
    new = sorted(set(down) - set(before))
    back = sorted(set(before) - set(down))
    if new:
        lines = [f"{s} ({_cities(conn, s)}): {down[s][0]} of {down[s][1]} garages silent, last reading {down[s][2]} UTC" for s in new]
        send(f"Parking feed down: {len(new)} source{'s' if len(new) > 1 else ''}", "\n".join(lines), ["warning"], 4, dry_run)
    if back:
        lines = [f"{s} ({_cities(conn, s)}) is reporting again" for s in back]
        send(f"Parking feed back: {len(back)} source{'s' if len(back) > 1 else ''}", "\n".join(lines), ["white_check_mark"], 3, dry_run)
    if not dry_run:
        with conn:
            conn.executemany("DELETE FROM alert_state WHERE source_id = ?", [(s,) for s in back])
            conn.executemany(
                "INSERT OR IGNORE INTO alert_state (source_id, since, silent, active, alerted_at) VALUES (?, ?, ?, ?, ?)",
                [(s, down[s][2], down[s][0], down[s][1], _iso(now)) for s in new])
    return len(new) + len(back)


def digest(conn: sqlite3.Connection, dry_run: bool = False) -> None:
    conn.execute(SCHEMA)
    status = dict(conn.execute("SELECT status, COUNT(*) FROM feed_health GROUP BY status").fetchall()) \
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'feed_health'").fetchone() else {}
    week_ago = _iso(datetime.now(timezone.utc) - timedelta(days=7))
    new_frozen = conn.execute("SELECT COUNT(*) FROM frozen_places WHERE flagged_at >= ?", (week_ago,)).fetchone()[0]
    live = conn.execute("SELECT COUNT(*) FROM lots_meta WHERE last_observed_ts >= ?",
                        (_iso(datetime.now(timezone.utc) - timedelta(days=3)),)).fetchone()[0]
    errors = conn.execute(
        "SELECT adapter, COUNT(*) FROM scraper_runs WHERE status = 'error' AND run_at >= ? GROUP BY adapter ORDER BY 2 DESC LIMIT 3",
        (week_ago,)).fetchall()
    down = [r[0] for r in conn.execute("SELECT source_id FROM alert_state ORDER BY source_id")]
    lines = [
        f"{live:,} garages reported in the last 3 days.",
        f"Sources down: {', '.join(down) if down else 'none'}.",
        f"Garages flagged: {status.get('stopped', 0)} stopped, {status.get('frozen', 0)} frozen "
        f"({new_frozen} new this week), {status.get('capacity', 0)} capacity, {status.get('oscillating', 0)} oscillating.",
    ]
    if errors:
        lines.append("Most errors this week: " + ", ".join(f"{a} ({n})" for a, n in errors) + ".")
    lines.append(f"Reports: {APP_URL}/report and {APP_URL}/trends")
    send("Parking data: weekly digest", "\n".join(lines), ["bar_chart"], 2, dry_run)


def run_if_due(conn: sqlite3.Connection) -> None:
    """Hourly outage check and the Monday digest, logged in scraper_runs as
    adapter "alerts" (kinds "outages" and "digest")."""
    import traceback

    from scrapers import storage
    from scrapers.runner import _is_due, _last_success_at

    if not os.environ.get("NTFY_TOPIC"):
        return
    now = datetime.now(timezone.utc)
    jobs = []
    if _is_due(_last_success_at(conn, "alerts", "outages"), CHECK_INTERVAL_SECONDS):
        jobs.append(("outages", check_outages))
    last_digest = _last_success_at(conn, "alerts", "digest")
    if now.weekday() == DIGEST_WEEKDAY and now.hour >= DIGEST_HOUR_UTC and (last_digest is None or now - last_digest > timedelta(days=1)):
        jobs.append(("digest", digest))
    for kind, job in jobs:
        try:
            n = job(conn)
            storage.record_run(conn, "alerts", kind, "success", records_written=n or 0)
        except Exception as exc:
            storage.record_run(conn, "alerts", kind, "error", error_message=f"{exc}\n{traceback.format_exc()}")
            print(f"[alerts] {kind} FAILED: {exc}")


if __name__ == "__main__":
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA busy_timeout=30000")
    dry = "--dry-run" in sys.argv
    if "--digest" in sys.argv:
        digest(c, dry)
    else:
        print(f"{check_outages(c, dry)} changes")
