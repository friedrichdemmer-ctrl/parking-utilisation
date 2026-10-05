#!/usr/bin/env python3
"""Keeps the published reports current: /report (utilisation) and /yield
(revenue), rebuilt weekly, and /trends (multi-year), rebuilt monthly.

scraper_daemon.py calls spawn_if_due() every 5 minutes; a due build runs as
a separate process (`python3 reports_job.py utilisation|trends`), so the
trends build -- several minutes over the whole history -- never holds up the
scrapers. A lock file per kind (holding the build's pid) stops a second
build starting while one runs.
Builds write <db dir>/reports/<kind>_latest.html (served by app.py) plus a
dated JSON, and are logged in scraper_runs as adapter "reports".
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("PARKING_DB_PATH", Path(__file__).parent / "data" / "parking.db"))
REPORTS_DIR = DB_PATH.parent / "reports"
LOCK_MAX_AGE = 3 * 3600  # a lock older than this is from a crashed build
UTILISATION_INTERVAL_SECONDS = 7 * 24 * 3600


def latest_path(kind: str) -> Path:
    return REPORTS_DIR / f"{kind}_latest.html"


def _lock(kind: str) -> Path:
    return REPORTS_DIR / f".building-{kind}"


def _alive(lock: Path) -> bool:
    """Whether the build that wrote the lock is still running -- a deploy
    restarts the machine mid-build and leaves the lock behind."""
    try:
        return Path(f"/proc/{int(lock.read_text().strip())}").exists()
    except (ValueError, OSError):
        return False


def _due(conn: sqlite3.Connection, kind: str) -> bool:
    from scrapers.runner import _is_due, _last_success_at

    last = _last_success_at(conn, "reports", kind)
    if kind in ("utilisation", "yield"):
        return _is_due(last, UTILISATION_INTERVAL_SECONDS)
    # trends: once a month, from the 2nd (the previous month is then complete)
    now = datetime.now(timezone.utc)
    return now.day >= 2 and (last is None or (last.year, last.month) != (now.year, now.month))


def spawn_if_due(conn: sqlite3.Connection) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    for kind in ("utilisation", "trends", "yield"):
        lock = _lock(kind)
        if lock.exists() and time.time() - lock.stat().st_mtime < LOCK_MAX_AGE and _alive(lock):
            continue
        if _due(conn, kind):
            proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), kind],
                                    cwd=Path(__file__).parent, start_new_session=True)
            lock.write_text(str(proc.pid))
            print(f"[reports] {kind} build started (pid {proc.pid})")


def build(kind: str) -> None:
    from scrapers import storage

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ro = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    ro.execute("PRAGMA busy_timeout=30000")
    try:
        if kind == "utilisation":
            import utilisation_report as r
            report = r.build(ro)
            n = report["included"]
            name = f"utilisation_{report['window']['end']}"
        elif kind == "yield":
            # reads the latest utilisation report, so it follows that build
            import yield_report as r
            report = r.build()
            n = report["reliable"]
            name = f"yield_{stamp}"
        else:
            import trends_report as r
            months = r.garage_months(ro)
            report = r.analyse(months)
            n = len(months["months"])
            name = f"trends_{stamp}"
        (REPORTS_DIR / f"{name}.json").write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
        tmp = latest_path(kind).with_suffix(".tmp")
        tmp.write_text(r.render_html(report), encoding="utf-8")
        tmp.replace(latest_path(kind))  # atomic, so /report never serves half a file
        status, err = "success", None
        print(f"[reports] {kind}: {n} garages -> {latest_path(kind)}")
    except Exception as exc:
        status, err, n = "error", f"{exc}\n{traceback.format_exc()}", 0
        print(f"[reports] {kind} FAILED: {exc}")
    finally:
        ro.close()
        _lock(kind).unlink(missing_ok=True)
    rw = sqlite3.connect(DB_PATH)
    rw.execute("PRAGMA busy_timeout=30000")
    storage.record_run(rw, "reports", kind, status, records_written=n, error_message=err)
    rw.close()


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "utilisation")
