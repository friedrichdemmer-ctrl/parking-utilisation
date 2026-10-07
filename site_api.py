"""Data endpoints for the public site (site/index.html, served at /):
what is full right now, search, a garage card (with its posted tariff and
indicative takings, garage_prices.py), a city view, and a one-line feed
status for the header.

Built so the site can be browsed without handing out the archive: every
endpoint returns a summary for one thing at a time (search answers at most
SEARCH_LIMIT matches), there is no bulk export, and app.py rate-limits
/api/* per visitor (see limit_api_rate). Typical-week profiles come from the
latest utilisation report (utilisation_report.py) rather than from raw
readings.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request

DB_PATH = Path(os.environ.get("PARKING_DB_PATH", Path(__file__).parent / "data" / "parking.db"))
REPORTS_DIR = DB_PATH.parent / "reports"

LIVE_WINDOW = timedelta(hours=2)    # a garage counts as "now" if it reported within this
NOW_TTL = 120                       # seconds the live snapshot is cached
STATUS_TTL = 300
SEARCH_LIMIT = 20
MIN_CITY_GARAGES = 3                # for the "busiest cities" list

bp = Blueprint("site_api", __name__)
_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, ttl: int, build):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    value = build()
    _cache[key] = (time.time(), value)
    return value


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _country(source_id: str | None) -> str:
    from app import SOURCE_COUNTRY

    return SOURCE_COUNTRY.get(source_id or "", "Germany")


def _report() -> dict:
    """Latest utilisation report, keyed by garage id (reloaded when a newer file appears)."""
    files = sorted(REPORTS_DIR.glob("utilisation_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        return {"garages": {}, "window": None}
    latest = files[-1]
    hit = _cache.get("report")
    if hit and hit[1][0] == (latest, latest.stat().st_mtime):
        return hit[1][1]
    data = json.loads(latest.read_text(encoding="utf-8"))
    value = {"garages": {g["id"]: g for g in data["garages"]}, "window": data["window"]}
    _cache["report"] = (time.time(), ((latest, latest.stat().st_mtime), value))
    return value


def _excluded(conn: sqlite3.Connection) -> set[str]:
    """Garages not shown as live: duplicates of another feed's garage and
    garages whose feed is flagged as frozen, oscillating or off-capacity."""
    from garage_links import duplicates

    out = set(duplicates())
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'feed_health'").fetchone():
        out |= {r[0] for r in conn.execute(
            "SELECT place_id FROM feed_health WHERE status IN ('frozen', 'oscillating', 'capacity')")}
    return out


def _now_snapshot() -> dict:
    from garage_links import NOT_READINGS

    conn = _db()
    cutoff = _iso(datetime.now(timezone.utc) - LIVE_WINDOW)
    skip = _excluded(conn)
    garages = []
    for pid, name, city, cap, lat, lon, src, free, ts in conn.execute(
        """SELECT m.place_id, m.place_name, m.city_name, m.num_all, m.latitude, m.longitude, m.source_id, h.free, h.ts
           FROM lots_meta m JOIN historical_observations h ON h.place_id = m.place_id AND h.ts = m.last_observed_ts
           WHERE m.last_observed_ts >= ? AND m.num_all >= 10""",
        (cutoff,),
    ):
        if pid in skip or src in NOT_READINGS:
            continue
        occ = 1 - min(max(free, 0), cap) / cap
        garages.append({"id": pid, "name": name, "city": city, "country": _country(src), "capacity": cap,
                        "lat": lat, "lon": lon, "occ": round(occ * 100), "ts": ts[:16]})
    conn.close()
    cities: dict[tuple[str, str], list] = {}
    for g in garages:
        cities.setdefault((g["country"], g["city"]), []).append(g)
    city_rows = [
        {"city": c, "country": k, "garages": len(gs), "capacity": sum(g["capacity"] for g in gs),
         "occ": round(sum(g["occ"] * g["capacity"] for g in gs) / sum(g["capacity"] for g in gs))}
        for (k, c), gs in cities.items() if len(gs) >= MIN_CITY_GARAGES
    ]
    total = sum(g["capacity"] for g in garages)
    return {
        "as_of": _iso(datetime.now(timezone.utc)) + "Z",
        "garages": garages,
        "cities": sorted(city_rows, key=lambda c: -c["occ"]),
        "occ": round(sum(g["occ"] * g["capacity"] for g in garages) / total) if total else None,
        "countries": len({g["country"] for g in garages}),
    }


@bp.route("/api/now")
def api_now():
    return jsonify(_cached("now", NOW_TTL, _now_snapshot))


def _totals() -> dict:
    conn = _db()
    garages, cities, countries = 0, set(), set()
    for city, src in conn.execute("SELECT city_name, source_id FROM lots_meta WHERE num_all IS NOT NULL"):
        garages += 1
        cities.add(city)
        countries.add(_country(src))
    conn.close()
    return {"garages": garages, "cities": len(cities), "countries": len(countries)}


@bp.route("/api/totals")
def api_totals():
    return jsonify(_cached("totals", 3600, _totals))


def _status() -> dict:
    """Sources that reported recently vs sources that went quiet (alerts.down_sources)."""
    import alerts

    conn = _db()
    active = {r[0] for r in conn.execute(
        "SELECT DISTINCT source_id FROM lots_meta WHERE last_observed_ts >= ? AND source_id IS NOT NULL",
        (_iso(datetime.now(timezone.utc) - timedelta(days=alerts.ACTIVE_DAYS)),))}
    from sync_archive import DEAD_ARCHIVE_SOURCE_IDS

    active -= set(DEAD_ARCHIVE_SOURCE_IDS) | alerts.NEVER_ALERT
    down = sorted(alerts.down_sources(conn))
    conn.close()
    return {"live": len(active) - len(down), "total": len(active), "down": down}


@bp.route("/api/status-summary")
def api_status_summary():
    return jsonify(_cached("status", STATUS_TTL, _status))


def _index() -> dict:
    """{country: {city: [(place_id, name, capacity, has_history), ...]}} for
    every garage with a known capacity, duplicates of another feed's garage
    left out. Built once an hour; the browse and search endpoints slice it."""
    def build():
        from app import SOURCE_COUNTRY
        from garage_links import duplicates

        dup = set(duplicates())
        conn = _db()
        out: dict = {}
        for pid, name, city, cap, src, last in conn.execute(
            "SELECT place_id, place_name, city_name, num_all, source_id, last_observed_ts FROM lots_meta "
            "WHERE num_all IS NOT NULL AND city_name IS NOT NULL"
        ):
            if pid in dup:
                continue
            out.setdefault(SOURCE_COUNTRY.get(src or "", "Germany"), {}).setdefault(city, []).append(
                (pid, name or pid, cap, bool(last)))
        conn.close()
        return out

    return _cached("index", 3600, build)


# The browse endpoints list one level at a time: countries, then the cities
# of one country, then the garages of one city. Entries with occupancy
# history come first, so the useful ones are at the top of long lists
# (Norway has 398 cities, none with history; the UK 962, a handful).

@bp.route("/api/browse/countries")
def api_browse_countries():
    rows = []
    for country, cs in _index().items():
        gs = [g for city in cs.values() for g in city]
        rows.append({"country": country, "cities": len(cs), "garages": len(gs),
                     "with_data": sum(1 for g in gs if g[3])})
    return jsonify(sorted(rows, key=lambda r: (r["with_data"] == 0, r["country"])))


@bp.route("/api/browse/cities")
def api_browse_cities():
    cs = _index().get(request.args.get("country", ""))
    if cs is None:
        return jsonify({"error": "Unknown country."}), 404
    rows = [{"city": city, "garages": len(gs), "with_data": sum(1 for g in gs if g[3])} for city, gs in cs.items()]
    return jsonify(sorted(rows, key=lambda r: (r["with_data"] == 0, r["city"].lower())))


@bp.route("/api/browse/garages")
def api_browse_garages():
    gs = _index().get(request.args.get("country", ""), {}).get(request.args.get("city", ""))
    if gs is None:
        return jsonify({"error": "Unknown city."}), 404
    rows = [{"id": pid, "name": name, "capacity": cap, "has_data": has} for pid, name, cap, has in gs]
    return jsonify(sorted(rows, key=lambda r: (not r["has_data"], r["name"].lower())))


# The local maps: the competitive set (competitive.py) one city at a time. A
# garage that is also one of ours (competitive/links.csv) carries its live
# occupancy and the id of its page.

@bp.route("/api/local/countries")
def api_local_countries():
    import competitive

    return jsonify(competitive.countries())


@bp.route("/api/local/cities")
def api_local_cities():
    import competitive

    country = request.args.get("country", "")
    rows = competitive.cities(country)
    if not rows:
        return jsonify({"error": "Unknown country."}), 404
    return jsonify(rows)


@bp.route("/api/local/map")
def api_local_map():
    import competitive

    m = competitive.city_map(request.args.get("country", ""), request.args.get("city", ""))
    if m is None:
        return jsonify({"error": "No map for this city."}), 404
    now = {g["id"]: g for g in _cached("now", NOW_TTL, _now_snapshot)["garages"]}
    for g in m["garages"]:
        live = now.get(g["place_id"]) if g["place_id"] else None
        g["occ"], g["occ_ts"] = (live["occ"], live["ts"]) if live else (None, None)
    return jsonify(m)


def _trends() -> dict | None:
    """Latest trends report (reloaded when a newer file appears)."""
    files = sorted(REPORTS_DIR.glob("trends_20*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        return None
    latest = files[-1]
    hit = _cache.get("trends")
    if hit and hit[1][0] == (latest, latest.stat().st_mtime):
        return hit[1][1]
    data = json.loads(latest.read_text(encoding="utf-8"))
    _cache["trends"] = (time.time(), ((latest, latest.stat().st_mtime), data))
    return data


@bp.route("/api/briefing")
def api_briefing():
    """One city: operator positioning, the city's trend against Germany's, EV coverage, and the
    sourced context we have researched for it (annotations/cities/). See city_briefing.py."""
    import city_briefing

    country, city = request.args.get("country", ""), request.args.get("city", "")

    def build():
        out = city_briefing.build(country, city, list(_report()["garages"].values()), _trends())
        if out is not None:
            import freshness

            conn = _db()
            try:
                out["data"] = freshness.of_city(conn, out.get("measured_ids") or [])
            finally:
                conn.close()
        return out

    out = _cached(f"briefing:{country}|{city}", 3600, build)
    if out is None:
        return jsonify({"error": "No briefing for this city."}), 404
    return jsonify(out)


@bp.route("/api/request", methods=["POST"])
def api_request():
    """The "Ask us" form. See requests_store.py for storage, limits and privacy."""
    import requests_store

    if os.environ.get("ASK_ENABLED") != "1":         # parked until the privacy notice is live
        return jsonify({"error": "Not available."}), 404
    data = request.get_json(silent=True) or {}
    fields, problem = requests_store.validate(data)
    if problem == "spam":
        return jsonify({"ok": True})                 # say nothing useful to a bot
    if problem:
        return jsonify({"error": problem}), 400
    ip = request.headers.get("Fly-Client-IP") or request.remote_addr or "?"
    rid, problem = requests_store.add(fields, ip)
    if problem:
        return jsonify({"error": problem}), 429
    return jsonify({"ok": True, "id": rid})


@bp.route("/api/search")
def api_search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"cities": [], "garages": []})
    ql = q.lower()
    cities = []
    for country, cs in _index().items():
        for city, gs in cs.items():
            if ql in city.lower():
                cities.append({"city": city, "country": country, "garages": len(gs),
                               "with_data": sum(1 for g in gs if g[3])})
    cities.sort(key=lambda c: (not c["city"].lower().startswith(ql), c["with_data"] == 0, -c["garages"], c["city"]))
    cities = cities[:8]
    like = f"%{q}%"
    conn = _db()
    skip = _excluded(conn)
    garages = [
        {"id": pid, "name": name, "city": city, "country": _country(src), "capacity": cap, "live": bool(last)}
        for pid, name, city, cap, last, src in conn.execute(
            """SELECT place_id, place_name, city_name, num_all, last_observed_ts, source_id FROM lots_meta
               WHERE num_all IS NOT NULL AND (place_name LIKE ? OR city_name LIKE ?)
               ORDER BY (last_observed_ts IS NULL), (place_name LIKE ?) DESC, place_name LIMIT ?""",
            (like, like, f"{q}%", SEARCH_LIMIT * 2))
        if pid not in skip
    ][:SEARCH_LIMIT - len(cities)]
    conn.close()
    return jsonify({"cities": cities, "garages": garages})


def _garage_summary(row, report: dict, now: dict) -> dict:
    from garage_prices import modelled_revenue, prices, revenue_week
    from garage_types import LABELS, classify

    pid, name, city, cap, lat, lon, src, last = row
    g = report["garages"].get(pid)
    live = now.get(pid)
    price = prices().get(pid)
    return {
        "id": pid, "name": name, "city": city, "country": _country(src), "capacity": cap,
        "lat": lat, "lon": lon, "type": LABELS[classify(name)],
        "now": live["occ"] if live else None, "now_ts": live["ts"] if live else None,
        "last_reading": (last or "")[:16] or None,
        "typical": {k: g[k] for k in ("avg", "weekday_avg", "weekend_avg", "peak", "full_hours", "profile")} if g else None,
        "price": price and dict(price,
                               revenue_week=revenue_week(g["profile"], cap, price["hourly_rate"]) if g else None,
                               modelled=modelled_revenue(g["profile"], cap, price, name) if g else None),
    }


GARAGE_COLS = "place_id, place_name, city_name, num_all, latitude, longitude, source_id, last_observed_ts"


@bp.route("/api/garage/<path:place_id>")
def api_garage(place_id: str):
    conn = _db()
    row = conn.execute(f"SELECT {GARAGE_COLS} FROM lots_meta WHERE place_id = ? AND num_all IS NOT NULL", (place_id,)).fetchone()
    first = conn.execute("SELECT MIN(ts) FROM historical_observations WHERE place_id = ?", (place_id,)).fetchone()[0] if row else None
    # the years that have readings: a garage can have a gap of years (Frankfurt's FFH feed, 2022-2024)
    years = sorted({int(r[0]) for r in conn.execute(
        "SELECT DISTINCT substr(ts, 1, 4) FROM historical_observations WHERE place_id = ?", (place_id,))}) if first else []
    conn.close()
    if not row:
        return jsonify({"error": "No garage with a known capacity has this id."}), 404
    report = _report()
    now = {g["id"]: g for g in _cached("now", NOW_TTL, _now_snapshot)["garages"]}
    summary = _garage_summary(row, report, now)
    summary["first_reading"] = (first or "")[:10] or None
    summary["years"] = years
    return jsonify({"garage": summary, "window": report["window"]})


@bp.route("/api/city/<path:city>")
def api_city(city: str):
    country = request.args.get("country") or None   # Münster, Bruges, Burgdorf and Baden exist in two
    conn = _db()
    skip = _excluded(conn)
    rows = [r for r in conn.execute(f"SELECT {GARAGE_COLS} FROM lots_meta WHERE city_name = ? AND num_all IS NOT NULL", (city,))
            if r[0] not in skip and (country is None or _country(r[6]) == country)]
    freshness = __import__("freshness").of_rows([(r[6], r[7]) for r in rows])
    conn.close()
    if not rows:
        return jsonify({"error": "No garages with a known capacity in this city."}), 404
    report = _report()
    now = {g["id"]: g for g in _cached("now", NOW_TTL, _now_snapshot)["garages"]}
    garages = [_garage_summary(r, report, now) for r in rows]
    # capacity-weighted typical week over the garages in the report
    profiled = [g for g in garages if g["typical"]]
    profile = []
    for s in range(168):
        num = den = 0
        for g in profiled:
            v = g["typical"]["profile"][s]
            if v is not None:
                num += v * g["capacity"]
                den += g["capacity"]
        profile.append(round(num / den) if den else None)
    priced = [g for g in garages if g["price"] and g["price"]["hourly_rate"]]
    rates = sorted(g["price"]["hourly_rate"] for g in priced)
    revenue = [g["price"]["modelled"]["total"] for g in priced if g["price"].get("modelled")]
    live = [g for g in garages if g["now"] is not None]
    for g in garages:
        if g["typical"]:
            g["typical"] = {k: v for k, v in g["typical"].items() if k != "profile"} | {"spark": g["typical"]["profile"]}
    return jsonify({
        "city": city, "country": garages[0]["country"], "garages": sorted(garages, key=lambda g: (g["now"] is None, -(g["capacity"] or 0))),
        "capacity": sum(g["capacity"] for g in garages),
        "now": round(sum(g["now"] * g["capacity"] for g in live) / sum(g["capacity"] for g in live)) if live else None,
        "local_map": __import__("competitive").garages().get((garages[0]["country"], city)) is not None,
        "data": freshness,
        "profile": profile if profiled else None, "profiled": len(profiled), "window": report["window"],
        "prices": {"garages": len(priced), "median_rate": rates[len(rates) // 2] if rates else None,
                   "min_rate": rates[0] if rates else None, "max_rate": rates[-1] if rates else None,
                   "revenue_week": sum(revenue) if revenue else None, "revenue_garages": len(revenue)} if priced else None,
    })
