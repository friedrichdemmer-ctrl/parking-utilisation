#!/usr/bin/env python3
"""Utilisation report: how full each garage is, hour by hour, over a typical week.

For every garage with a capacity and readings in the window (the last WEEKS
full Monday-Sunday weeks, in the garage's local time), occupancy = 1 -
free/capacity is sampled every 15 minutes from the latest reading (see
SAMPLE_EVERY) and averaged into 168 hour-of-week slots, with free clamped to
[0, capacity] (counter drift produces negative counts and counts above
capacity; see feed_health.py). Garage figures are means over the slots, so
every hour of the week counts equally however often a feed reports.

Left out, with the reason counted in the output:
- garages feed_health.py currently flags (stopped, frozen, oscillating,
  capacity mismatch) -- their readings are not trustworthy;
- garages with no capacity, or under MIN_CAPACITY spaces;
- garages with readings on fewer than MIN_DAYS days, or with samples in
  fewer than MIN_SLOTS of the 168 slots (feeds that started recently, or
  that go silent for more than MAX_GAP);
- garages near full every hour of the week with no daily swing (a counter
  stuck at or near 0 free).

Writes JSON (default: <db dir>/reports/utilisation_<end date>.json). It
never changes the database. `--html <report.json> <page.html>` renders a
downloaded report into a self-contained page via report_template.html.
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

DB_PATH = Path(os.environ.get("PARKING_DB_PATH", Path(__file__).parent / "data" / "parking.db"))

WEEKS = 8
MIN_DAYS = 7
MIN_SLOTS = 150
MIN_CAPACITY = 10
# occupancy is sampled every SAMPLE_EVERY from the latest reading, which is
# carried forward for up to MAX_GAP: many feeds only send a reading when the
# count changes, so a quiet night has none, and feeds report at different rates
SAMPLE_EVERY = timedelta(minutes=15)
MAX_GAP = timedelta(hours=12)
FULL = 0.90  # an hour counts as "full" when average occupancy is at least this
# a garage that is near full every hour of the week, with no day/night swing,
# is a counter stuck at or near 0 free rather than real demand (an empty,
# unused P+R site with a flat profile near 0% is plausible and kept)
STUCK_RANGE = 0.15
STUCK_LEVEL = 0.70

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
    from app import SOURCE_COUNTRY  # Flask is only installed on the server

    start, end = _window(today or datetime.now(timezone.utc).date())
    # a day of margin either side; readings are then cut to local dates
    lo = (datetime.combine(start, datetime.min.time()) - timedelta(days=1)).strftime("%Y-%m-%d")
    hi = (datetime.combine(end, datetime.min.time()) + timedelta(days=2)).strftime("%Y-%m-%d")
    window_days = {start + timedelta(days=d) for d in range((end - start).days + 1)}
    from scrapers.storage import capacity_at, capacity_timeline

    timeline = capacity_timeline(conn)
    flagged = dict(conn.execute("SELECT place_id, status FROM feed_health"))
    places = conn.execute(
        "SELECT place_id, place_name, city_name, num_all, source_id, latitude, longitude FROM lots_meta "
        "WHERE last_observed_ts >= ?",
        (lo,),
    ).fetchall()
    excluded: Counter = Counter()
    by_source: Counter = Counter()
    included_by_source: Counter = Counter()
    garages = []
    for place_id, name, city, capacity, source_id, lat, lon in places:
        if place_id in flagged:
            excluded[f"feed health: {flagged[place_id]}"] += 1
            by_source[source_id] += 1
            continue
        if not capacity or capacity < MIN_CAPACITY:
            excluded["no capacity, or under 10 spaces"] += 1
            by_source[source_id] += 1
            continue
        country = SOURCE_COUNTRY.get(source_id, "Germany")
        tz = ZoneInfo(COUNTRY_TZ[country])
        tl = timeline.get(place_id)  # capacity in force at each reading
        readings = sorted(
            (_parse(ts), free, capacity_at(tl, capacity, ts))
            for ts, free in conn.execute(
                "SELECT ts, free FROM historical_observations WHERE place_id = ? AND ts >= ? AND ts < ?",
                (place_id, lo, hi),
            )
        )
        days = {dt.astimezone(tz).date() for dt, _, _ in readings} & window_days
        sums, fulls, counts = [0.0] * 168, [0] * 168, [0] * 168
        t = datetime.combine(start, datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
        stop = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
        i, last = 0, None
        while t < stop:
            while i < len(readings) and readings[i][0] <= t:
                last = readings[i]
                i += 1
            if last and t - last[0] <= MAX_GAP:
                occ = 1 - min(max(last[1], 0), last[2]) / last[2]
                local = t.astimezone(tz)
                slot = local.weekday() * 24 + local.hour
                sums[slot] += occ
                fulls[slot] += occ >= FULL
                counts[slot] += 1
            t += SAMPLE_EVERY
        slots = [i for i in range(168) if counts[i]]
        if len(days) < MIN_DAYS or len(slots) < MIN_SLOTS:
            excluded["too little data in the window"] += 1
            by_source[source_id] += 1
            continue
        profile = [sums[i] / counts[i] if counts[i] else None for i in range(168)]
        filled = [p for p in profile if p is not None]
        if max(filled) - min(filled) < STUCK_RANGE and sum(filled) / len(filled) >= STUCK_LEVEL:
            excluded["near full around the clock, no daily pattern"] += 1
            by_source[source_id] += 1
            continue
        weekday = [profile[i] for i in range(120) if profile[i] is not None]
        weekend = [profile[i] for i in range(120, 168) if profile[i] is not None]
        peak = max(slots, key=lambda i: profile[i])
        included_by_source[source_id] += 1
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
        # source_id: [included, excluded]
        "sources": {s: [included_by_source[s], by_source[s]] for s in sorted(set(by_source) | set(included_by_source))},
        "garages": sorted(garages, key=lambda g: (g["country"], g["city"] or "", g["name"] or "")),
    }


def render_html(report: dict) -> str:
    """The report as a self-contained page (report_template.html plus the data)."""
    meta = {k: report[k] for k in ("window", "method", "considered", "included", "excluded", "generated_at")}
    rows = [
        [g["name"], g["city"], g["country"], g["capacity"], g["full_hours"], [-1 if v is None else v for v in g["profile"]]]
        for g in report["garages"]
    ]
    data = (f"const META={json.dumps(meta, ensure_ascii=False, separators=(',', ':'))};\n"
            f"const G={json.dumps(rows, ensure_ascii=False, separators=(',', ':'))};\n")
    return (Path(__file__).parent / "report_template.html").read_text(encoding="utf-8").replace("/*DATA*/", data)


def main() -> None:
    if sys.argv[1:2] == ["--html"]:  # --html <report.json> <page.html>: render a downloaded report
        report = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        Path(sys.argv[3]).write_text(render_html(report), encoding="utf-8")
        print(f"{sys.argv[3]}: {report['included']} garages")
        return
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.execute("PRAGMA busy_timeout=30000")
    report = build(conn)
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH.parent / "reports" / f"utilisation_{report['window']['end']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    print(f"{out}: {report['included']} garages included of {report['considered']}; excluded {report['excluded']}")


if __name__ == "__main__":
    main()
