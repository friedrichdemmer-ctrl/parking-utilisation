#!/usr/bin/env python3
"""Utilisation report: how full each garage is, hour by hour, over a typical week.

For every garage with a capacity and readings in the window (the last WEEKS
full Monday-Sunday weeks, in the garage's local time), readings are put into
168 hour-of-week slots and averaged as occupancy = 1 - free/capacity, with
free clamped to [0, capacity] (counter drift produces negative counts and
counts above capacity; see feed_health.py). Garage figures are means over the
slots, so every hour of the week counts equally however often a feed reports.

Left out, with the reason counted in the output:
- garages feed_health.py currently flags (stopped, frozen, oscillating,
  capacity mismatch) -- their readings are not trustworthy;
- garages with no capacity, or under MIN_CAPACITY spaces;
- garages with readings on fewer than MIN_DAYS days, or in fewer than
  MIN_SLOTS of the 168 slots (feeds that only report in opening hours, or
  that started recently).

Writes JSON (default: <db dir>/reports/utilisation_<end date>.json). It
never changes the database.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app import SOURCE_COUNTRY

DB_PATH = Path(os.environ.get("PARKING_DB_PATH", Path(__file__).parent / "data" / "parking.db"))

WEEKS = 8
MIN_DAYS = 7
MIN_SLOTS = 150
MIN_CAPACITY = 10
FULL = 0.90  # an hour counts as "full" when average occupancy is at least this

COUNTRY_TZ = {
    "Germany": "Europe/Berlin", "Netherlands": "Europe/Amsterdam", "France": "Europe/Paris",
    "Belgium": "Europe/Brussels", "Denmark": "Europe/Copenhagen", "Ireland": "Europe/Dublin",
    "Austria": "Europe/Vienna", "Italy": "Europe/Rome", "Spain": "Europe/Madrid",
    "Luxembourg": "Europe/Luxembourg", "Finland": "Europe/Helsinki", "Norway": "Europe/Oslo",
    "Switzerland": "Europe/Zurich", "UK": "Europe/London",
}


def _window(today: date) -> tuple[date, date]:
    end = today - timedelta(days=today.weekday() + 1)  # last Sunday before today
    return end - timedelta(weeks=WEEKS) + timedelta(days=1), end


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def build(conn: sqlite3.Connection, today: date | None = None) -> dict:
    start, end = _window(today or datetime.now(timezone.utc).date())
    # a day of margin either side; readings are then cut to local dates
    lo = (datetime.combine(start, datetime.min.time()) - timedelta(days=1)).strftime("%Y-%m-%d")
    hi = (datetime.combine(end, datetime.min.time()) + timedelta(days=2)).strftime("%Y-%m-%d")
    flagged = dict(conn.execute("SELECT place_id, status FROM feed_health"))
    places = conn.execute(
        "SELECT place_id, place_name, city_name, num_all, source_id, latitude, longitude FROM lots_meta "
        "WHERE last_observed_ts >= ?",
        (lo,),
    ).fetchall()
    excluded: Counter = Counter()
    garages = []
    for place_id, name, city, capacity, source_id, lat, lon in places:
        if place_id in flagged:
            excluded[f"feed health: {flagged[place_id]}"] += 1
            continue
        if not capacity or capacity < MIN_CAPACITY:
            excluded["no capacity, or under 10 spaces"] += 1
            continue
        country = SOURCE_COUNTRY.get(source_id, "Germany")
        tz = ZoneInfo(COUNTRY_TZ[country])
        sums, fulls, counts, days = [0.0] * 168, [0] * 168, [0] * 168, set()
        for ts, free in conn.execute(
            "SELECT ts, free FROM historical_observations WHERE place_id = ? AND ts >= ? AND ts < ?",
            (place_id, lo, hi),
        ):
            local = _parse(ts).astimezone(tz)
            if not start <= local.date() <= end:
                continue
            occ = 1 - min(max(free, 0), capacity) / capacity
            slot = local.weekday() * 24 + local.hour
            sums[slot] += occ
            fulls[slot] += occ >= FULL
            counts[slot] += 1
            days.add(local.date())
        slots = [i for i in range(168) if counts[i]]
        if len(days) < MIN_DAYS or len(slots) < MIN_SLOTS:
            excluded["too little data in the window"] += 1
            continue
        profile = [sums[i] / counts[i] if counts[i] else None for i in range(168)]
        filled = [p for p in profile if p is not None]
        weekday = [profile[i] for i in range(120) if profile[i] is not None]
        weekend = [profile[i] for i in range(120, 168) if profile[i] is not None]
        peak = max(slots, key=lambda i: profile[i])
        garages.append({
            "id": place_id, "name": name, "city": city, "country": country, "source": source_id,
            "capacity": capacity, "lat": lat, "lon": lon, "days": len(days),
            "avg": round(sum(filled) / len(filled), 3),
            "weekday_avg": round(sum(weekday) / len(weekday), 3) if weekday else None,
            "weekend_avg": round(sum(weekend) / len(weekend), 3) if weekend else None,
            "peak": {"dow": peak // 24, "hour": peak % 24, "occ": round(profile[peak], 3)},
            # hours per week whose average occupancy is at least FULL
            "full_hours": sum(1 for p in filled if p >= FULL),
            # share of individual readings at or above FULL, time-weighted by slot
            "full_share": round(sum(fulls[i] / counts[i] for i in slots) / len(slots), 3),
            "profile": [None if p is None else round(p * 100) for p in profile],
        })
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": {"start": start.isoformat(), "end": end.isoformat(), "weeks": WEEKS},
        "method": {"full_threshold": FULL, "min_days": MIN_DAYS, "min_slots": MIN_SLOTS, "min_capacity": MIN_CAPACITY},
        "considered": len(places),
        "included": len(garages),
        "excluded": dict(excluded.most_common()),
        "garages": sorted(garages, key=lambda g: (g["country"], g["city"] or "", g["name"] or "")),
    }


def main() -> None:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.execute("PRAGMA busy_timeout=30000")
    report = build(conn)
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH.parent / "reports" / f"utilisation_{report['window']['end']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    print(f"{out}: {report['included']} garages included of {report['considered']}; excluded {report['excluded']}")


if __name__ == "__main__":
    main()
