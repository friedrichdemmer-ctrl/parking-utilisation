#!/usr/bin/env python3
"""Local web app for browsing German parking garage utilisation history.

Three views:
- Query & Download: garage-or-town scope, operator filter, date range,
  granularity (1h/2h/4h) -> avg utilisation per slot-of-day, CSV download.
- Year Heatmap: one garage, one year -> day x hour heatmap.
- Daily Comparison: multiple entities (garage or town) over a date range ->
  one avg-utilisation-per-day line per entity, CSV download.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, Response, jsonify, redirect, request

DB_PATH = Path(os.environ.get("PARKING_DB_PATH", Path(__file__).parent / "data" / "parking.db"))
BERLIN = ZoneInfo("Europe/Berlin")
CURRENT_YEAR = datetime.now().year

# lots_meta has no country column -- every source not listed here defaults to
# Germany. Every new non-German adapter needs an entry here, or it silently
# gets counted as Germany on /api/coverage.
_COUNTRY_SOURCES = {
    "Netherlands": ["npr-qpark-nl", "npr-other-nl", "amsterdam-live", "assen-live"],
    "France": [
        "bnls-qpark-fr", "bnls-other-fr", "amp-metropole-live", "bordeaux-metropole-live",
        "grenoble-live", "la-rochelle-live", "lyon-parc-auto-live", "lyon-qpark", "mel-lille-live",
        "nantes-naolib-live", "rouen-qpark", "saint-etienne-qpark", "strasbourg-live",
        "toulouse-qpark", "tours-live",
        "montpellier-live", "rennes-live", "angers-live", "orleans-live", "poitiers-live",
        "clermont-ferrand-live", "caen-live", "brest-live", "nimes-live", "reims-live", "le-mans-live",
    ],
    "Belgium": ["gent-live", "interparking-belgium", "kortrijk-live", "liege-hors-voirie", "verviers-live"],
    "Denmark": ["copenhagen-qpark", "vejle-live"],
    "Ireland": ["cork-live", "galway-live", "waterford-live"],
    "Austria": ["parken-at", "salzburg-live"],
    "Italy": ["bologna-live", "opendatahub-parking", "torino-5t", "firenze-live"],
    "Spain": ["madrid-live", "malaga-live", "pamplona-live", "euskadi-parkings", "vigo-live", "laspalmas-sagulpa"],
    "Luxembourg": ["luxembourg-vdl"],
    "Finland": ["fintraffic-parking"],
    "Norway": ["parkeringsregisteret-no"],
    "Switzerland": ["sbb-parkrail", "basel-live", "zuerich-live", "st-gallen-live", "frauenfeld-live", "geneve-live", "luzern-live"],
    "UK": [
        "dft-uk-carparks", "tfl-live", "city-of-london-live", "hillingdon-live", "harrow-live",
        "bristol-live", "leeds-live", "york-live", "tyne-wear-live", "dundee-live",
        "perth-kinross-live", "angus-live", "ards-north-down-live", "causeway-coast-glens-live",
        "fermanagh-omagh-live", "mid-ulster-live",
    ],
}
SOURCE_COUNTRY = {source: country for country, sources in _COUNTRY_SOURCES.items() for source in sources}

app = Flask(__name__)

from site_api import bp as site_api_bp  # noqa: E402  (needs SOURCE_COUNTRY above)

app.register_blueprint(site_api_bp)

# Per-visitor limit on the JSON API, so the archive can be browsed but not
# bulk-copied by looping over garages. In-memory per gunicorn worker, so the
# effective limit is a small multiple of this; fine for its purpose.
API_RATE_LIMIT = 240          # requests
API_RATE_WINDOW = 5 * 60      # seconds
_api_hits: dict[str, list[float]] = {}


@app.before_request
def limit_api_rate():
    if not request.path.startswith("/api/"):
        return None
    import time

    ip = request.headers.get("Fly-Client-IP") or request.remote_addr or "?"
    now = time.time()
    hits = [t for t in _api_hits.get(ip, []) if now - t < API_RATE_WINDOW]
    if len(hits) >= API_RATE_LIMIT:
        _api_hits[ip] = hits
        return jsonify({"error": "Too many requests. Try again in a few minutes."}), 429
    hits.append(now)
    _api_hits[ip] = hits
    if len(_api_hits) > 5000:  # forget idle visitors
        for k in [k for k, v in _api_hits.items() if not v or now - v[-1] > API_RATE_WINDOW]:
            _api_hits.pop(k, None)
    return None


def _downloads_allowed() -> bool:
    """CSV exports are not public: they need ?token= matching the
    DOWNLOAD_TOKEN secret (unset = no downloads at all)."""
    token = os.environ.get("DOWNLOAD_TOKEN")
    return bool(token) and request.args.get("token") == token


@app.before_request
def check_db_ready():
    if not DB_PATH.exists():
        return Response(
            "<h1>Building the database</h1>"
            "<p>First boot imports ~88 million historical records and reorders them "
            "for fast queries -- this takes roughly 10-20 minutes. Refresh shortly.</p>",
            mimetype="text/html",
        )


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def local_dt(ts: str) -> datetime:
    return datetime.fromisoformat(ts).astimezone(BERLIN)


def resolve_scope_lots(conn: sqlite3.Connection, scope_type: str, scope_value: str, operator: str | None,
                       country: str | None = None):
    """Return list of (place_id, num_all, place_name) for the given scope, capacity known only."""
    if scope_type == "garage":
        row = conn.execute(
            "SELECT place_id, num_all, place_name FROM lots_meta WHERE place_id = ? AND num_all IS NOT NULL",
            (scope_value,),
        ).fetchone()
        return [(row["place_id"], row["num_all"], row["place_name"])] if row else []
    else:  # 'city'
        from garage_links import duplicates

        q = "SELECT place_id, num_all, place_name, source_id FROM lots_meta WHERE city_name = ? AND num_all IS NOT NULL"
        params = [scope_value]
        if operator:
            q += " AND source_id = ?"
            params.append(operator)
        dup = duplicates()   # the same garage reached through two feeds counts once
        return [(r["place_id"], r["num_all"], r["place_name"]) for r in conn.execute(q, params).fetchall()
                if r["place_id"] not in dup
                and (country is None or SOURCE_COUNTRY.get(r["source_id"] or "", "Germany") == country)]


def fetch_observations(conn: sqlite3.Connection, place_ids: list[str], start: str | None, end: str | None):
    placeholders = ",".join("?" * len(place_ids))
    q = f"SELECT place_id, ts, free FROM historical_observations WHERE place_id IN ({placeholders})"
    params = list(place_ids)
    if start:
        q += " AND ts >= ?"
        params.append(start + "T00:00:00")
    if end:
        q += " AND ts <= ?"
        params.append(end + "T23:59:59")
    return conn.execute(q, params).fetchall()


def compute_slot_of_day(scope_type: str, scope_value: str, operator: str | None, start: str | None, end: str | None, granularity: int):
    conn = get_db()
    lots = resolve_scope_lots(conn, scope_type, scope_value, operator)
    if not lots:
        conn.close()
        return None, "No garage(s) with known capacity match this selection."
    cap = {p: c for p, c, _ in lots}
    rows = fetch_observations(conn, list(cap.keys()), start, end)
    conn.close()
    if not rows:
        return None, "No observations in this selection/date range."

    per_lot_slot = defaultdict(list)
    for row in rows:
        dt = local_dt(row["ts"])
        slot = (dt.hour // granularity) * granularity
        num_all = cap[row["place_id"]]
        util = max(0.0, min(100.0, (num_all - row["free"]) / num_all * 100))
        per_lot_slot[(row["place_id"], slot)].append(util)

    slot_weighted = defaultdict(lambda: [0.0, 0])
    slot_samples = defaultdict(int)
    for (place_id, slot), vals in per_lot_slot.items():
        avg = sum(vals) / len(vals)
        w = cap[place_id]
        slot_weighted[slot][0] += avg * w
        slot_weighted[slot][1] += w
        slot_samples[slot] += len(vals)

    result = []
    for slot_start in range(0, 24, granularity):
        w = slot_weighted.get(slot_start)
        avg = round(w[0] / w[1], 1) if w and w[1] > 0 else None
        result.append(
            {
                "slot": f"{slot_start:02d}:00-{(slot_start + granularity) % 24:02d}:00",
                "avg_utilisation_pct": avg,
                "sample_count": slot_samples.get(slot_start, 0),
                "garages_count": len(lots),
            }
        )
    return result, None


def compute_heatmap(place_id: str, year: int, granularity: int):
    """Grid keyed by week-of-year (0-based, Jan 1 = week 0) x weekday (0=Mon..6=Sun) x slot-of-day,
    in the garage's own local time and against the capacity in force at each reading."""
    from utilisation_report import COUNTRY_TZ
    from scrapers.storage import capacity_at, capacity_timeline

    conn = get_db()
    meta = conn.execute(
        "SELECT place_name, city_name, num_all, source_id FROM lots_meta WHERE place_id = ?", (place_id,)
    ).fetchone()
    if meta is None or not meta["num_all"]:
        conn.close()
        return None, None, "This garage has no known capacity in the archive."
    tz = ZoneInfo(COUNTRY_TZ[SOURCE_COUNTRY.get(meta["source_id"] or "", "Germany")])
    tl = capacity_timeline(conn).get(place_id)
    rows = conn.execute(
        "SELECT ts, free FROM historical_observations WHERE place_id = ? AND ts >= ? AND ts <= ?",
        (place_id, f"{year}-01-01T00:00:00", f"{year}-12-31T23:59:59"),
    ).fetchall()
    conn.close()

    cells = defaultdict(list)
    for row in rows:
        dt = datetime.fromisoformat(row["ts"]).astimezone(tz)
        if dt.year != year:
            continue
        cap = capacity_at(tl, meta["num_all"], row["ts"])
        week_idx = (dt.timetuple().tm_yday - 1) // 7
        slot = (dt.hour // granularity) * granularity
        util = max(0.0, min(100.0, (cap - row["free"]) / cap * 100))
        cells[(week_idx, dt.weekday(), slot)].append(util)

    grid: dict = {}
    for (week_idx, weekday, slot), vals in cells.items():
        grid.setdefault(str(week_idx), {}).setdefault(str(weekday), {})[str(slot)] = round(sum(vals) / len(vals), 1)

    return meta, grid, None


def compute_daily_series(scope_type: str, scope_value: str, operator: str | None, start: str | None, end: str | None,
                         country: str | None = None):
    conn = get_db()
    lots = resolve_scope_lots(conn, scope_type, scope_value, operator, country)
    if not lots:
        conn.close()
        return None, "No garage(s) with known capacity match this selection."
    cap = {p: c for p, c, _ in lots}
    rows = fetch_observations(conn, list(cap.keys()), start, end)
    conn.close()
    if not rows:
        return [], None

    per_lot_day = defaultdict(list)
    for row in rows:
        dt = local_dt(row["ts"])
        num_all = cap[row["place_id"]]
        util = max(0.0, min(100.0, (num_all - row["free"]) / num_all * 100))
        per_lot_day[(row["place_id"], dt.date().isoformat())].append(util)

    day_weighted = defaultdict(lambda: [0.0, 0])
    for (place_id, date_str), vals in per_lot_day.items():
        avg = sum(vals) / len(vals)
        w = cap[place_id]
        day_weighted[date_str][0] += avg * w
        day_weighted[date_str][1] += w

    result = [
        {"date": date_str, "avg_utilisation_pct": round(vw[0] / vw[1], 1)}
        for date_str, vw in sorted(day_weighted.items())
        if vw[1] > 0
    ]
    return result, None


def label_for(scope_type: str, scope_value: str, operator: str | None) -> str:
    return f"{scope_value} ({'garage' if scope_type == 'garage' else 'whole town'}{', operator=' + operator if operator else ''})"


# Self-contained report pages, rebuilt by reports_job.py (utilisation weekly,
# trends monthly). The page skeleton is added here; the files hold the body.


def _report_page(kind: str) -> Response:
    path = DB_PATH.parent / "reports" / f"{kind}_latest.html"
    if not path.exists():
        return Response("<p>This report has not been built yet; it appears within an hour of a deploy.</p>",
                        status=404, mimetype="text/html")
    head = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
    body = path.read_text(encoding="utf-8").replace('<div class="wrap">', SITE_BAR + '<div class="wrap">', 1)
    return Response(head + body + "</html>", mimetype="text/html",
                    headers={"Cache-Control": "public, max-age=300"})


# The site's header bar, added to the report pages so they read as part of
# the site. Uses the reports' own colour tokens (--accent, --ink, --rule...).
SITE_ROOT = "/"
SITE_BAR = f"""<style>
.sitebar{{display:flex;flex-wrap:wrap;align-items:center;gap:.4rem 1.4rem;padding:.7rem max(16px,4vw);border-bottom:1px solid var(--rule);background:var(--surface);font:500 .92rem var(--font-body)}}
.sitebar a{{color:var(--ink-2);text-decoration:none}}.sitebar a:hover{{color:var(--ink)}}
.sitebar .sb-brand{{display:flex;align-items:center;gap:.5rem;color:var(--ink);font:600 1.05rem var(--font-display);margin-right:.6rem}}
.sitebar .sb-on{{color:var(--ink);box-shadow:inset 0 -2px 0 var(--accent)}}
</style>
<nav class="sitebar" aria-label="Site"><a class="sb-brand" href="{SITE_ROOT}"><span class="psign" aria-hidden="true">P</span>Parking utilisation</a>
<a href="{SITE_ROOT}#overview">Overview</a><a href="{SITE_ROOT}#explore">Explore</a><a href="{SITE_ROOT}#local">Local maps</a><a href="{SITE_ROOT}#compare">Compare</a><a class="sb-on" href="{SITE_ROOT}#reports">Reports</a></nav>"""


SITE_PAGE = Path(__file__).parent / "site" / "index.html"


@app.route("/")
def site_page():
    """The site (site/index.html); its sections are client-side (#overview, #explore...).
    It replaced the old form-and-table page on 2026-10-05."""
    return Response(SITE_PAGE.read_text(encoding="utf-8"), mimetype="text/html", headers={"Cache-Control": "no-cache"})


@app.route("/new")
def old_site_link():
    return redirect("/", code=301)


@app.route("/report")
def utilisation_page():
    return _report_page("utilisation")


@app.route("/trends")
def trends_page():
    return _report_page("trends")


@app.route("/yield")
def yield_page():
    return _report_page("yield")


@app.route("/api/cities")
def api_cities():
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT city_name FROM lots_meta WHERE city_name IS NOT NULL ORDER BY city_name"
    ).fetchall()
    conn.close()
    return jsonify([r["city_name"] for r in rows])


@app.route("/api/operators")
def api_operators():
    conn = get_db()
    rows = conn.execute(
        """SELECT source_id, COUNT(DISTINCT city_name) ncities FROM lots_meta
           WHERE source_id IS NOT NULL GROUP BY source_id ORDER BY source_id"""
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/coverage")
def api_coverage():
    conn = get_db()
    totals = conn.execute(
        "SELECT COUNT(DISTINCT city_name), COUNT(*), "
        "SUM(CASE WHEN num_all IS NOT NULL THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN last_observed_ts IS NOT NULL THEN 1 ELSE 0 END) FROM lots_meta"
    ).fetchone()
    # 3 days, not 1: ~20 German sources are fed once a day from the defgsus
    # archive, whose newest day-file lags ~1-2 days behind. ts formats vary in
    # suffix ("+00:00", "Z", ".053Z"), but all share this prefix.
    live_cutoff = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S")
    sources = conn.execute(
        """SELECT source_id,
                  COUNT(DISTINCT city_name) ncities,
                  COUNT(*) total,
                  SUM(CASE WHEN num_all IS NOT NULL THEN 1 ELSE 0 END) has_cap,
                  SUM(CASE WHEN last_observed_ts IS NOT NULL THEN 1 ELSE 0 END) has_obs,
                  SUM(CASE WHEN last_observed_ts >= ? THEN 1 ELSE 0 END) live_recent,
                  MAX(last_observed_ts) last_ts
           FROM lots_meta WHERE source_id IS NOT NULL
           GROUP BY source_id ORDER BY total DESC""",
        (live_cutoff,),
    ).fetchall()
    conn.close()

    source_list = [dict(r) for r in sources]
    for s in source_list:
        s["country"] = SOURCE_COUNTRY.get(s["source_id"], "Germany")

    by_country: dict[str, dict] = defaultdict(
        lambda: {"garages": 0, "has_obs": 0, "live_recent": 0, "cities": set(), "sources": 0}
    )
    for s in source_list:
        c = by_country[s["country"]]
        c["garages"] += s["total"]
        c["has_obs"] += s["has_obs"]
        c["live_recent"] += s["live_recent"]
        c["sources"] += 1
    # city sets need the raw rows, not the per-source aggregate -- recount directly
    conn = get_db()
    city_rows = conn.execute(
        "SELECT city_name, source_id FROM lots_meta WHERE source_id IS NOT NULL GROUP BY city_name, source_id"
    ).fetchall()
    conn.close()
    for r in city_rows:
        country = SOURCE_COUNTRY.get(r["source_id"], "Germany")
        by_country[country]["cities"].add(r["city_name"])
    countries = [
        {
            "country": name,
            "garages": v["garages"],
            "with_utilisation": v["has_obs"],
            "live_recent": v["live_recent"],
            "capacity_only": v["garages"] - v["has_obs"],
            "cities": len(v["cities"]),
            "sources": v["sources"],
        }
        for name, v in sorted(by_country.items(), key=lambda kv: -kv[1]["garages"])
    ]

    return jsonify(
        {
            "totals": {
                "cities": totals[0],
                "garages": totals[1],
                "with_capacity": totals[2],
                "with_utilisation": totals[3],
            },
            "countries": countries,
            "sources": source_list,
        }
    )


@app.route("/api/scraper-health")
def api_scraper_health():
    conn = get_db()
    conn.executescript(  # scraper_runs may not exist yet on a DB that predates the scraper framework
        """CREATE TABLE IF NOT EXISTS scraper_runs (
               id INTEGER PRIMARY KEY AUTOINCREMENT, adapter TEXT NOT NULL, kind TEXT NOT NULL,
               run_at TEXT NOT NULL, status TEXT NOT NULL, records_written INTEGER DEFAULT 0,
               records_rejected INTEGER DEFAULT 0, error_message TEXT
           )"""
    )

    latest = conn.execute(
        """SELECT sr.adapter, sr.kind, sr.status, sr.run_at
           FROM scraper_runs sr
           JOIN (SELECT adapter, kind, MAX(run_at) AS run_at FROM scraper_runs GROUP BY adapter, kind) m
             ON m.adapter = sr.adapter AND m.kind = sr.kind AND m.run_at = sr.run_at
           ORDER BY sr.adapter, sr.kind"""
    ).fetchall()
    last_success = dict(
        conn.execute(
            "SELECT adapter || '/' || kind, MAX(run_at) FROM scraper_runs WHERE status='success' GROUP BY adapter, kind"
        ).fetchall()
    )
    recent_errors = conn.execute(
        """SELECT adapter, kind, run_at, error_message FROM scraper_runs
           WHERE status='error' ORDER BY run_at DESC LIMIT 20"""
    ).fetchall()
    conn.close()

    adapters = [
        {
            "adapter": r["adapter"],
            "kind": r["kind"],
            "status": r["status"],
            "run_at": r["run_at"],
            "last_success_at": last_success.get(f"{r['adapter']}/{r['kind']}"),
        }
        for r in latest
    ]
    errors = [
        {
            "adapter": r["adapter"],
            "kind": r["kind"],
            "run_at": r["run_at"],
            # error_message is the exception plus its full traceback -- only the
            # exception line itself is useful for a quick glance here.
            "error_summary": (r["error_message"] or "").split("\n", 1)[0][:200],
        }
        for r in recent_errors
    ]
    return jsonify({"adapters": adapters, "recent_errors": errors})


@app.route("/api/feed-health")
def api_feed_health():
    """Garages flagged by feed_health.py's daily check, grouped by source."""
    conn = get_db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS feed_health (
               place_id TEXT PRIMARY KEY, source_id TEXT, place_name TEXT, city_name TEXT,
               status TEXT NOT NULL, since TEXT, detail TEXT, checked_at TEXT NOT NULL
           )"""
    )
    rows = conn.execute(
        "SELECT place_id, source_id, place_name, city_name, status, since, detail, checked_at FROM feed_health "
        "ORDER BY source_id, status, since"
    ).fetchall()
    conn.close()
    by_source: dict[str, dict] = {}
    for r in rows:
        s = by_source.setdefault(r["source_id"], {"source_id": r["source_id"], "stopped": 0, "frozen": 0,
                                                  "oscillating": 0, "capacity": 0, "garages": []})
        s[r["status"]] = s.get(r["status"], 0) + 1
        s["garages"].append({k: r[k] for k in ("place_id", "place_name", "city_name", "status", "since", "detail")})
    return jsonify({
        "checked_at": rows[0]["checked_at"] if rows else None,
        "sources": sorted(by_source.values(), key=lambda s: -len(s["garages"])),
    })


@app.route("/api/garages")
def api_garages():
    city = request.args.get("city", "")
    operator = request.args.get("operator") or None
    conn = get_db()
    q = "SELECT place_id, place_name, num_all, last_observed_ts FROM lots_meta WHERE city_name = ?"
    params = [city]
    if operator:
        q += " AND source_id = ?"
        params.append(operator)
    # Garages with real observations first (most recent first), then everything
    # else alphabetically -- otherwise a city where only some garages report
    # live data can look entirely empty just because the alphabetically-first
    # garage happens to be a capacity-only one.
    q += " ORDER BY (last_observed_ts IS NULL), last_observed_ts DESC, place_name"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/query")
def api_query():
    scope_type = request.args.get("scope_type", "garage")
    scope_value = request.args.get("scope_value", "")
    operator = request.args.get("operator") or None
    start = request.args.get("start") or None
    end = request.args.get("end") or None
    granularity = int(request.args.get("granularity", 1))
    result, error = compute_slot_of_day(scope_type, scope_value, operator, start, end, granularity)
    meta = None if error else f"{label_for(scope_type, scope_value, operator)} — {result[0]['garages_count']} garage(s)"
    return jsonify({"meta": meta, "result": result, "error": error})


@app.route("/download.csv")
def download_csv():
    if not _downloads_allowed():
        return Response("Downloads are not available.", status=403)
    scope_type = request.args.get("scope_type", "garage")
    scope_value = request.args.get("scope_value", "")
    operator = request.args.get("operator") or None
    start = request.args.get("start") or None
    end = request.args.get("end") or None
    granularity = int(request.args.get("granularity", 1))
    result, error = compute_slot_of_day(scope_type, scope_value, operator, start, end, granularity)
    if error or not result:
        return Response(error or "no data", status=400)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["scope", label_for(scope_type, scope_value, operator)])
    writer.writerow(["date_range", start or "full history", end or "full history"])
    writer.writerow(["granularity_hours", granularity])
    writer.writerow([])
    writer.writerow(["slot", "avg_utilisation_pct", "sample_count", "garages_count"])
    for r in result:
        writer.writerow([r["slot"], r["avg_utilisation_pct"], r["sample_count"], r["garages_count"]])

    filename = f"{scope_value}_{granularity}h_utilisation.csv"
    return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.route("/api/heatmap")
def api_heatmap():
    place_id = request.args.get("place_id", "")
    year = int(request.args.get("year", CURRENT_YEAR))
    granularity = int(request.args.get("granularity", 2))
    meta, grid, error = compute_heatmap(place_id, year, granularity)
    meta_str = f"{meta['place_name']} — {meta['city_name']} — capacity {meta['num_all']}" if meta else None
    return jsonify({"meta": meta_str, "grid": grid, "granularity": granularity, "error": error})


@app.route("/api/compare", methods=["POST"])
def api_compare():
    payload = request.get_json(force=True)
    entities = payload.get("entities", [])
    start = payload.get("start")
    end = payload.get("end")
    series = []
    for e in entities:
        data, error = compute_daily_series(e["scope_type"], e["scope_value"], None, start, end, e.get("country"))
        if error:
            return jsonify({"error": f"{e['scope_value']}: {error}"})
        label = e.get("label") or label_for(e["scope_type"], e["scope_value"], None)
        series.append({"label": label, "data": data})
    return jsonify({"series": series, "error": None})


@app.route("/download_compare.csv")
def download_compare_csv():
    if not _downloads_allowed():
        return Response("Downloads are not available.", status=403)
    payload = json.loads(request.args.get("payload", "{}"))
    entities = payload.get("entities", [])
    start = payload.get("start")
    end = payload.get("end")

    series = []
    for e in entities:
        data, error = compute_daily_series(e["scope_type"], e["scope_value"], None, start, end)
        if error:
            return Response(f"{e['scope_value']}: {error}", status=400)
        label = e.get("label") or label_for(e["scope_type"], e["scope_value"], None)
        series.append((label, {d["date"]: d["avg_utilisation_pct"] for d in data}))

    all_dates = sorted({d for _, s in series for d in s})
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date"] + [label for label, _ in series])
    for d in all_dates:
        writer.writerow([d] + [s.get(d, "") for _, s in series])

    return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=comparison.csv"})


if __name__ == "__main__":
    app.run(debug=True, port=5151)
