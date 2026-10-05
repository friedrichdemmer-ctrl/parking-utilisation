#!/usr/bin/env python3
"""Multi-year trends: how car-park occupancy has moved since 2020.

Two steps, both read-only on the database:

1. garage_months(conn): for every garage with a capacity, occupancy is
   sampled hourly (at :30, local time) from the latest reading, carried
   forward for up to MAX_GAP, and summarised per calendar month: hours
   sampled, mean occupancy, and daytime (09-18) means for each weekday.
   Months are dropped as unreliable when samples cover under half the month,
   more than 5% of raw readings are above capacity x1.1 or below zero
   (counter drift; see feed_health.py), the month has under 5 distinct
   values (a frozen feed), or it is near full at every hour of the day (a
   counter stuck near 0 free; same rule as utilisation_report.py).

2. analyse(months): turns those into the published series. Garages come and
   go over six years, so levels are never averaged across a changing set:
   - index: linked year on year (see _yoy_index). Each link is the
     capacity-weighted change among garages valid in the same month of both
     years; the index averages 100 over BASE_YEAR.
   - year-on-year by city: same garages, same month, one year apart.
   - seasonality: each month relative to its year's mean, on garages valid
     all year, averaged over the full years 2022-2025.
   - weekday shape: daytime occupancy of each weekday relative to the
     Tuesday-Thursday mean, per year, on garages valid in that year.

Writes JSON (default: <db dir>/reports/trends_<YYYY-MM>.json);
`--html <trends.json> <page.html>` renders it via trends_template.html.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from utilisation_report import COUNTRY_TZ, STUCK_LEVEL, STUCK_RANGE, _parse

DB_PATH = Path(os.environ.get("PARKING_DB_PATH", Path(__file__).parent / "data" / "parking.db"))

MAX_GAP = timedelta(hours=12)
MIN_CAPACITY = 10
MIN_COVERAGE = 0.5      # share of the month's hours that must have a sample
MAX_BAD_SHARE = 0.05    # readings above capacity x1.1 or below zero
MIN_DISTINCT = 5
DAY_HOURS = range(9, 18)
BASE_YEAR = 2023
MIN_PAIR_GARAGES = 20   # chain-link step needs at least this many common garages
MIN_CITY_GARAGES = 3


def garage_months(conn: sqlite3.Connection) -> dict:
    from app import SOURCE_COUNTRY  # Flask is only installed on the server

    garages, months = {}, {}
    for place_id, name, city, capacity, source_id in conn.execute(
        "SELECT place_id, place_name, city_name, num_all, source_id FROM lots_meta WHERE num_all >= ?", (MIN_CAPACITY,)
    ).fetchall():
        readings = sorted((_parse(ts), free) for ts, free in conn.execute(
            "SELECT ts, free FROM historical_observations WHERE place_id = ?", (place_id,)))
        if len(readings) < 100:
            continue
        country = SOURCE_COUNTRY.get(source_id, "Germany")
        tz = ZoneInfo(COUNTRY_TZ[country])
        # per month: [hours, occ_sum, day_sum[7], day_n[7], hour_sum[24], hour_n[24]] and raw-reading quality counts
        acc = defaultdict(lambda: [0, 0.0, [0.0] * 7, [0] * 7, [0.0] * 24, [0] * 24])
        raw = defaultdict(lambda: [0, 0, set()])
        for dt, free in readings:
            k = dt.astimezone(tz).strftime("%Y-%m")
            r = raw[k]
            r[0] += 1
            r[1] += free > capacity * 1.1 or free < 0
            if len(r[2]) < MIN_DISTINCT:
                r[2].add(free)
        t = readings[0][0].replace(minute=30, second=0, microsecond=0)
        i, last = 0, None
        while t <= readings[-1][0]:
            while i < len(readings) and readings[i][0] <= t:
                last = readings[i]
                i += 1
            if last and t - last[0] <= MAX_GAP:
                occ = 1 - min(max(last[1], 0), capacity) / capacity
                local = t.astimezone(tz)
                a = acc[local.strftime("%Y-%m")]
                a[0] += 1
                a[1] += occ
                a[4][local.hour] += occ
                a[5][local.hour] += 1
                if local.hour in DAY_HOURS:
                    a[2][local.weekday()] += occ
                    a[3][local.weekday()] += 1
            t += timedelta(hours=1)
        kept = {}
        for k, (hours, occ_sum, day_sum, day_n, hour_sum, hour_n) in acc.items():
            y, m = map(int, k.split("-"))
            days = ((datetime(y + (m == 12), m % 12 + 1, 1) - datetime(y, m, 1)).days)
            n, bad, distinct = raw.get(k, (0, 0, ()))
            if hours < MIN_COVERAGE * days * 24 or not n or bad / n > MAX_BAD_SHARE or len(distinct) < MIN_DISTINCT:
                continue
            by_hour = [s / c for s, c in zip(hour_sum, hour_n) if c]
            if max(by_hour) - min(by_hour) < STUCK_RANGE and occ_sum / hours >= STUCK_LEVEL:
                continue  # near full around the clock: a stuck counter
            kept[k] = [round(occ_sum / hours, 4)] + [round(s / c, 4) if c else None for s, c in zip(day_sum, day_n)]
        if kept:
            garages[place_id] = {"name": name, "city": city, "country": country, "capacity": capacity}
            months[place_id] = kept
    return {"garages": garages, "months": months}


def _month_list(first: str, last: str) -> list[str]:
    y, m = map(int, first.split("-"))
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _weighted(pairs: list[tuple[float, float]]) -> float:
    return sum(v * w for v, w in pairs) / sum(w for _, w in pairs)


def _yoy_index(months: dict, caps: dict, ids: list[str], keys: list[str], col: int = 0,
               min_pairs: int = MIN_PAIR_GARAGES) -> dict[str, float | None]:
    """Index over `keys` for the garages `ids`, linked year on year.

    The base year's months come from one fixed panel (garages valid in at
    least 10 of its months); every other month is linked to the same month
    one year nearer the base year, using only garages valid in both. Linking
    month to month instead drifted upward by ~15% over 2023-2026 while the
    median garage was flat: garages leave the sample unevenly (a failing
    counter's last months are filtered out), and the error compounds 12
    times a year. Same-month links compound once a year and need no
    seasonal adjustment."""
    def val(g, k):
        m = months[g].get(k)
        return None if m is None else m[col]

    def ratio(a: str, b: str) -> float | None:
        common = [g for g in ids if val(g, a) is not None and val(g, b) is not None]
        if len(common) < min_pairs:
            return None
        x, y = _weighted([(val(g, a), caps[g]) for g in common]), _weighted([(val(g, b), caps[g]) for g in common])
        return y / x if x else None

    base = str(BASE_YEAR)
    panel = [g for g in ids if sum(val(g, f"{base}-{m:02d}") is not None for m in range(1, 13)) >= 10]
    index: dict[str, float | None] = {}
    if len(panel) < min_pairs:
        return {k: None for k in keys}
    for m in range(1, 13):
        k = f"{base}-{m:02d}"
        pairs = [(val(g, k), caps[g]) for g in panel if val(g, k) is not None]
        index[k] = _weighted(pairs) if len(pairs) >= min_pairs else None
    for k in sorted((k for k in keys if k[:4] > base)):
        prev = f"{int(k[:4]) - 1}{k[4:]}"
        r = ratio(prev, k) if index.get(prev) else None
        index[k] = index[prev] * r if r else None
    for k in sorted((k for k in keys if k[:4] < base), reverse=True):
        nxt = f"{int(k[:4]) + 1}{k[4:]}"
        r = ratio(k, nxt) if index.get(nxt) else None
        index[k] = index[nxt] / r if r else None
    return {k: index.get(k) for k in keys}


def analyse(data: dict) -> dict:
    garages, months = data["garages"], data["months"]
    caps = {g: garages[g]["capacity"] for g in garages}
    all_keys = sorted({k for m in months.values() for k in m})
    # start once MIN_PAIR_GARAGES garages report, stop at the last full month
    counts = defaultdict(int)
    for m in months.values():
        for k in m:
            counts[k] += 1
    keys = [k for k in all_keys if counts[k] >= MIN_PAIR_GARAGES]
    this_month = datetime.now(timezone.utc).strftime("%Y-%m")
    keys = [k for k in _month_list(keys[0], keys[-1]) if k < this_month]  # full months only
    ids = list(months)

    def rebase(idx: dict) -> dict:
        base = [v for k, v in idx.items() if k.startswith(str(BASE_YEAR)) and v is not None]
        b = sum(base) / len(base) if len(base) >= 6 else None
        return {k: (round(v / b * 100, 1) if v is not None and b else None) for k, v in idx.items()}

    index = rebase(_yoy_index(months, caps, ids, keys))
    # weekday daytime index (Tue-Thu, cols 2-4 averaged)
    tt = {g: {k: [None, (lambda v: sum(v) / 3 if all(x is not None for x in v) else None)(m[2:5])] for k, m in ms.items()} for g, ms in months.items()}
    index_weekday = rebase(_yoy_index(tt, caps, ids, keys, col=1))
    # the level the index refers to: capacity-weighted mean occupancy of
    # garages valid in each base-year month
    base_levels = []
    for k in keys:
        if k.startswith(str(BASE_YEAR)):
            pairs = [(months[g][k][0], caps[g]) for g in ids if k in months[g]]
            if pairs:
                base_levels.append(_weighted(pairs))
    base_level = round(sum(base_levels) / len(base_levels), 4) if base_levels else None
    garage_count = {k: counts[k] for k in keys}

    # seasonality: per full year 2022-2025, garages valid in all 12 months;
    # each month's level relative to that year's mean, averaged over years
    season = defaultdict(list)
    for y in range(2022, 2026):
        ks = [f"{y}-{m:02d}" for m in range(1, 13)]
        panel = [g for g in ids if all(k in months[g] for k in ks)]
        if len(panel) < MIN_PAIR_GARAGES:
            continue
        levels = [_weighted([(months[g][k][0], caps[g]) for g in panel]) for k in ks]
        avg = sum(levels) / 12
        for m, v in enumerate(levels, 1):
            season[m].append(v / avg)
    seasonality = {m: round(sum(v) / len(v) * 100, 1) for m, v in sorted(season.items())}

    # weekday shape per year: daytime occupancy by weekday relative to Tue-Thu
    years = sorted({k[:4] for k in keys})
    weekday_shape = {}
    for y in years:
        acc = [[] for _ in range(7)]
        for g, ms in months.items():
            yr = [m for k, m in ms.items() if k.startswith(y)]
            if len(yr) < 6:
                continue
            means = [sum(m[1 + d] for m in yr if m[1 + d] is not None) / max(1, sum(m[1 + d] is not None for m in yr)) for d in range(7)]
            mid = sum(means[1:4]) / 3
            if mid > 0.05:
                for d in range(7):
                    acc[d].append((means[d] / mid, caps[g]))
        if acc[0]:
            weekday_shape[y] = {"garages": len(acc[0]), "rel": [round(_weighted(a) * 100, 1) for a in acc]}

    # year-on-year by city: last 12 full months vs the 12 before, same garages and months
    last12, prev12 = keys[-12:], keys[-24:-12]
    by_city = defaultdict(list)
    for g in ids:
        by_city[(garages[g]["country"], garages[g]["city"])].append(g)
    cities = []
    for (country, city), gs in by_city.items():
        pairs_now, pairs_then, used = [], [], set()
        for a, b in zip(last12, prev12):
            for g in gs:
                if a in months[g] and b in months[g]:
                    pairs_now.append((months[g][a][0], caps[g]))
                    pairs_then.append((months[g][b][0], caps[g]))
                    used.add(g)
        if len(used) < MIN_CITY_GARAGES or len(pairs_now) < 6 * len(used):
            continue
        now, then = _weighted(pairs_now), _weighted(pairs_then)
        # long run: same garages, BASE_YEAR-1 .. latest full year where present
        cities.append({
            "city": city, "country": country, "garages": len(used),
            "now": round(now, 3), "then": round(then, 3), "change_pts": round((now - then) * 100, 1),
            "index": {k: v for k, v in rebase(_yoy_index(months, caps, gs, keys, min_pairs=MIN_CITY_GARAGES)).items() if v is not None}
            if len(gs) >= MIN_PAIR_GARAGES else None,
        })
    cities.sort(key=lambda c: -c["garages"])

    # annual averages of the index (full years with 10+ months)
    annual = {}
    for y in years:
        v = [index[k] for k in keys if k.startswith(y) and index.get(k) is not None]
        if len(v) >= 10:
            annual[y] = round(sum(v) / len(v), 1)

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "months": keys, "garages_per_month": garage_count, "garages_total": len(ids),
        "base_year": BASE_YEAR, "base_level": base_level,
        "index": index, "index_weekday_daytime": index_weekday, "annual": annual,
        "seasonality": seasonality, "weekday_shape": weekday_shape,
        "yoy": {"last": [last12[0], last12[-1]], "prev": [prev12[0], prev12[-1]], "cities": cities},
        "method": {"max_gap_h": MAX_GAP.total_seconds() / 3600, "min_coverage": MIN_COVERAGE, "max_bad_share": MAX_BAD_SHARE,
                   "min_pair_garages": MIN_PAIR_GARAGES, "min_city_garages": MIN_CITY_GARAGES},
    }


def render_html(report: dict) -> str:
    data = f"const T={json.dumps(report, ensure_ascii=False, separators=(',', ':'))};\n"
    return (Path(__file__).parent / "trends_template.html").read_text(encoding="utf-8").replace("/*DATA*/", data)


def main() -> None:
    if sys.argv[1:2] == ["--html"]:
        Path(sys.argv[3]).write_text(render_html(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))), encoding="utf-8")
        print(sys.argv[3])
        return
    if sys.argv[1:2] == ["--analyse"]:  # --analyse <months.json> <trends.json>: re-run step 2 only
        report = analyse(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
        Path(sys.argv[3]).write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(sys.argv[3])
        return
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.execute("PRAGMA busy_timeout=30000")
    data = garage_months(conn)
    out_dir = DB_PATH.parent / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m")
    (out_dir / f"garage_months_{stamp}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    report = analyse(data)
    (out_dir / f"trends_{stamp}.json").write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    print(f"trends: {len(data['months'])} garages, months {report['months'][0]}..{report['months'][-1]}")


if __name__ == "__main__":
    main()
