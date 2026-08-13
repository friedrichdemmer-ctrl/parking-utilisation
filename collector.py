#!/usr/bin/env python3
"""Poll api.parkendd.de and append a snapshot of every German parking lot to SQLite."""

import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_ROOT = "https://api.parkendd.de/"
DB_PATH = Path(os.environ.get("PARKING_DB_PATH", Path(__file__).parent / "data" / "parking.db"))
REQUEST_TIMEOUT = 15
DELAY_BETWEEN_CITIES = 0.3

SCHEMA = """
CREATE TABLE IF NOT EXISTS cities (
    city TEXT PRIMARY KEY,
    lat REAL,
    lng REAL,
    source TEXT,
    url TEXT,
    active_support INTEGER,
    last_seen TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collected_at TEXT NOT NULL,
    city TEXT NOT NULL,
    lot_id TEXT NOT NULL,
    name TEXT,
    address TEXT,
    lat REAL,
    lng REAL,
    total INTEGER,
    free INTEGER,
    state TEXT,
    lot_type TEXT,
    lot_last_updated TEXT
);

CREATE INDEX IF NOT EXISTS idx_snapshots_city_time ON snapshots (city, collected_at);
CREATE INDEX IF NOT EXISTS idx_snapshots_lot ON snapshots (lot_id, collected_at);
"""


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "parking-utilisation-collector/1.0"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.load(resp)


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout=30000")  # other daemons (scraper_daemon, gunicorn) share this file
    conn.executescript(SCHEMA)
    return conn


def collect() -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = get_db()

    try:
        root = fetch_json(API_ROOT)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"[{now}] FATAL: could not reach {API_ROOT}: {exc}", file=sys.stderr)
        sys.exit(1)

    cities = root.get("cities", {})
    print(f"[{now}] {len(cities)} cities listed at {API_ROOT}")

    total_lots = 0
    ok_cities = 0
    failed_cities = []

    for city_name, meta in cities.items():
        coords = meta.get("coords") or {}
        conn.execute(
            """INSERT INTO cities (city, lat, lng, source, url, active_support, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(city) DO UPDATE SET
                 lat=excluded.lat, lng=excluded.lng, source=excluded.source,
                 url=excluded.url, active_support=excluded.active_support,
                 last_seen=excluded.last_seen""",
            (
                city_name,
                coords.get("lat"),
                coords.get("lng"),
                meta.get("source"),
                meta.get("url"),
                int(bool(meta.get("active_support"))),
                now,
            ),
        )

        try:
            detail = fetch_json(API_ROOT + urllib.request.quote(city_name))
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            failed_cities.append(city_name)
            print(f"  ! {city_name}: {exc}", file=sys.stderr)
            time.sleep(DELAY_BETWEEN_CITIES)
            continue

        lot_last_updated = detail.get("last_updated")
        rows = []
        for lot in detail.get("lots", []):
            lot_coords = lot.get("coords") or {}
            rows.append(
                (
                    now,
                    city_name,
                    lot.get("id"),
                    lot.get("name"),
                    lot.get("address"),
                    lot_coords.get("lat"),
                    lot_coords.get("lng"),
                    lot.get("total"),
                    lot.get("free"),
                    lot.get("state"),
                    lot.get("lot_type"),
                    lot_last_updated,
                )
            )

        conn.executemany(
            """INSERT INTO snapshots
               (collected_at, city, lot_id, name, address, lat, lng, total, free, state, lot_type, lot_last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        total_lots += len(rows)
        ok_cities += 1
        time.sleep(DELAY_BETWEEN_CITIES)

    conn.commit()
    conn.close()

    print(
        f"[{now}] done: {ok_cities}/{len(cities)} cities OK, {total_lots} lot rows written"
        + (f", failed: {', '.join(failed_cities)}" if failed_cities else "")
    )


if __name__ == "__main__":
    collect()
