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
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, Response, jsonify, render_template_string, request

DB_PATH = Path(os.environ.get("PARKING_DB_PATH", Path(__file__).parent / "data" / "parking.db"))
BERLIN = ZoneInfo("Europe/Berlin")
CURRENT_YEAR = datetime.now().year

# lots_meta has no country column -- these are the only non-German sources
# so far, everything else defaults to Germany. Every new non-German adapter
# needs an entry here, or it silently gets counted as Germany on /api/coverage.
SOURCE_COUNTRY = {
    "npr-qpark-nl": "Netherlands",
    "npr-other-nl": "Netherlands",
    "bnls-qpark-fr": "France",
    "bnls-other-fr": "France",
}

app = Flask(__name__)


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


def resolve_scope_lots(conn: sqlite3.Connection, scope_type: str, scope_value: str, operator: str | None):
    """Return list of (place_id, num_all, place_name) for the given scope, capacity known only."""
    if scope_type == "garage":
        row = conn.execute(
            "SELECT place_id, num_all, place_name FROM lots_meta WHERE place_id = ? AND num_all IS NOT NULL",
            (scope_value,),
        ).fetchone()
        return [(row["place_id"], row["num_all"], row["place_name"])] if row else []
    else:  # 'city'
        q = "SELECT place_id, num_all, place_name FROM lots_meta WHERE city_name = ? AND num_all IS NOT NULL"
        params = [scope_value]
        if operator:
            q += " AND source_id = ?"
            params.append(operator)
        return [(r["place_id"], r["num_all"], r["place_name"]) for r in conn.execute(q, params).fetchall()]


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
    """Grid keyed by week-of-year (0-based, Jan 1 = week 0) x weekday (0=Mon..6=Sun) x slot-of-day."""
    conn = get_db()
    meta = conn.execute(
        "SELECT place_name, city_name, num_all FROM lots_meta WHERE place_id = ?", (place_id,)
    ).fetchone()
    if meta is None or not meta["num_all"]:
        conn.close()
        return None, None, "This garage has no known capacity in the archive."
    num_all = meta["num_all"]
    rows = conn.execute(
        "SELECT ts, free FROM historical_observations WHERE place_id = ? AND ts >= ? AND ts <= ?",
        (place_id, f"{year}-01-01T00:00:00", f"{year}-12-31T23:59:59"),
    ).fetchall()
    conn.close()

    cells = defaultdict(list)
    for row in rows:
        dt = local_dt(row["ts"])
        week_idx = (dt.timetuple().tm_yday - 1) // 7
        weekday = dt.weekday()  # 0=Mon .. 6=Sun
        slot = (dt.hour // granularity) * granularity
        util = max(0.0, min(100.0, (num_all - row["free"]) / num_all * 100))
        cells[(week_idx, weekday, slot)].append(util)

    grid: dict = {}
    for (week_idx, weekday, slot), vals in cells.items():
        grid.setdefault(str(week_idx), {}).setdefault(str(weekday), {})[str(slot)] = round(sum(vals) / len(vals), 1)

    return meta, grid, None


def compute_daily_series(scope_type: str, scope_value: str, operator: str | None, start: str | None, end: str | None):
    conn = get_db()
    lots = resolve_scope_lots(conn, scope_type, scope_value, operator)
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


PAGE = """
<!doctype html>
<title>Parking Garage Utilisation</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 900px; margin: 2rem auto; color: #222; }
  select, input, button { font-size: 1rem; padding: 0.3rem; margin: 0.2rem 0; }
  .row select { width: 100%; max-width: 100%; box-sizing: border-box; }
  label { display: block; margin-top: 0.8rem; font-weight: 600; }
  table { border-collapse: collapse; margin-top: 1rem; width: 100%; }
  td, th { border: 1px solid #ddd; padding: 4px 8px; text-align: right; }
  th { background: #f4f4f4; }
  .bar-bg { fill: #eee; }
  .bar { fill: #3b6fd6; }
  #error, .error { color: #b00; margin-top: 1rem; }
  .meta { color: #555; margin-top: 0.5rem; }
  a.download { display: inline-block; margin-top: 1rem; }
  .tabs { margin-bottom: 1.5rem; border-bottom: 2px solid #ddd; }
  .tab-btn { background: none; border: none; padding: 0.6rem 1rem; cursor: pointer; font-size: 1rem; border-bottom: 3px solid transparent; }
  .tab-btn.active { border-bottom-color: #3b6fd6; font-weight: 600; }
  .tab-panel { display: none; }
  .tab-panel.active { display: block; }
  .row { display: flex; gap: 1rem; flex-wrap: wrap; }
  .row > div { flex: 1; min-width: 180px; }
  fieldset { margin-top: 0.8rem; border: 1px solid #ddd; }
  .entity-row { display: flex; gap: 0.5rem; align-items: center; margin-top: 0.4rem; }
  .legend-line { display: inline-block; width: 14px; height: 3px; margin-right: 4px; vertical-align: middle; }
  #heatmap-tooltip { position: fixed; background: #222; color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 12px; pointer-events: none; display: none; z-index: 10; }
  .cov-stats { display: flex; gap: 1rem; flex-wrap: wrap; margin: 1rem 0; }
  .cov-stat { background: #f4f4f4; border-radius: 6px; padding: 0.8rem 1.2rem; min-width: 140px; }
  .cov-stat .n { font-size: 1.6rem; font-weight: 700; display: block; }
  .cov-stat .l { color: #555; font-size: 0.85rem; }
  #cov-country-table, #cov-source-table { font-size: 0.92rem; }
  .status-live { color: #1a7a1a; font-weight: 600; }
  .status-static { color: #888; }
</style>
<h1>Parking Garage Utilisation</h1>

<div class="tabs">
  <button class="tab-btn active" data-tab="query">Query &amp; Download</button>
  <button class="tab-btn" data-tab="heatmap">Year Heatmap</button>
  <button class="tab-btn" data-tab="compare">Daily Comparison</button>
  <button class="tab-btn" data-tab="coverage">Coverage</button>
</div>

<!-- ============ QUERY TAB ============ -->
<div class="tab-panel active" id="tab-query">
  <label>Scope</label>
  <select id="q-scope">
    <option value="garage">Single garage</option>
    <option value="city">Whole town (all garages, capacity-weighted)</option>
  </select>

  <div class="row">
    <div>
      <label>Town</label>
      <select id="q-city"><option value="">-- select town --</option></select>
    </div>
    <div id="q-garage-wrap">
      <label>Garage</label>
      <select id="q-garage" disabled><option value="">-- select town first --</option></select>
    </div>
    <div>
      <label>Operator (optional)</label>
      <select id="q-operator"><option value="">-- any --</option></select>
    </div>
  </div>

  <div class="row">
    <div>
      <label>Start date (optional)</label>
      <input type="date" id="q-start">
    </div>
    <div>
      <label>End date (optional)</label>
      <input type="date" id="q-end">
    </div>
    <div>
      <label>Granularity</label>
      <select id="q-granularity">
        <option value="1">Hourly</option>
        <option value="2">2-hour slots</option>
        <option value="4">4-hour slots</option>
      </select>
    </div>
  </div>

  <button id="q-go">Show utilisation</button>

  <div class="meta" id="q-meta"></div>
  <div class="error" id="q-error"></div>
  <div id="q-chart"></div>
  <table id="q-table"></table>
  <a class="download" id="q-dl" style="display:none">Download CSV</a>
</div>

<!-- ============ HEATMAP TAB ============ -->
<div class="tab-panel" id="tab-heatmap">
  <div class="row">
    <div>
      <label>Town</label>
      <select id="h-city"><option value="">-- select town --</option></select>
    </div>
    <div>
      <label>Garage</label>
      <select id="h-garage" disabled><option value="">-- select town first --</option></select>
    </div>
    <div>
      <label>Year</label>
      <select id="h-year"></select>
    </div>
    <div>
      <label>Time slot</label>
      <select id="h-granularity">
        <option value="1">Hourly</option>
        <option value="2" selected>2-hour slots</option>
        <option value="4">4-hour slots</option>
      </select>
    </div>
  </div>
  <button id="h-go" disabled>Show heatmap</button>
  <div class="meta" id="h-meta"></div>
  <div class="error" id="h-error"></div>
  <p style="color:#555; font-size:0.9rem;">Rows are weeks of the year (Jan 1 starts week 1); each row is split into 7 day-blocks (Mon–Sun), and each day-block into time slots.</p>
  <div id="h-chart" style="overflow-x:auto; margin-top:1rem;"></div>
  <div id="heatmap-tooltip"></div>
</div>

<!-- ============ COMPARE TAB ============ -->
<div class="tab-panel" id="tab-compare">
  <p>Add towns and/or specific garages to compare their daily average utilisation over the same period.</p>
  <div id="c-entities"></div>
  <button id="c-add" type="button">+ Add entity</button>

  <div class="row">
    <div>
      <label>Start date (optional)</label>
      <input type="date" id="c-start">
    </div>
    <div>
      <label>End date (optional)</label>
      <input type="date" id="c-end">
    </div>
  </div>
  <button id="c-go">Compare</button>

  <div class="error" id="c-error"></div>
  <div id="c-chart"></div>
  <a class="download" id="c-dl" style="display:none">Download comparison CSV</a>
</div>

<!-- ============ COVERAGE TAB ============ -->
<div class="tab-panel" id="tab-coverage">
  <p class="meta">What's currently in the archive, and where it comes from. "Live" means a source has reported an observation this year; "capacity only" means we have the garage's total spaces but no ongoing occupancy feed.</p>
  <div id="cov-totals" class="cov-stats"></div>
  <h3>By country</h3>
  <table id="cov-country-table"><thead><tr><th style="text-align:left">Country</th><th>Garages</th><th>Cities</th><th>Sources</th></tr></thead><tbody></tbody></table>
  <h3>By source</h3>
  <table id="cov-source-table"><thead><tr><th style="text-align:left">Source</th><th style="text-align:left">Country</th><th>Cities</th><th>Garages</th><th>With capacity</th><th>Status</th></tr></thead><tbody></tbody></table>
</div>

<script>
let CITIES = [];
let OPERATORS = [];

fetch('/api/cities').then(r => r.json()).then(cities => {
  CITIES = cities;
  for (const sel of [document.getElementById('q-city'), document.getElementById('h-city')]) {
    for (const c of cities) {
      const opt = document.createElement('option');
      opt.value = c; opt.textContent = c;
      sel.appendChild(opt);
    }
  }
  addEntityRow();
  addEntityRow();
});
fetch('/api/operators').then(r => r.json()).then(ops => {
  OPERATORS = ops;
  const sel = document.getElementById('q-operator');
  for (const o of ops) {
    const opt = document.createElement('option');
    opt.value = o.source_id; opt.textContent = o.source_id + ' (' + o.ncities + (o.ncities===1?' town':' towns') + ')';
    sel.appendChild(opt);
  }
});

// ---- coverage ----
function sourceStatus(hasObs, lastTs) {
  if (!hasObs || !lastTs) return { label: 'capacity only', cls: 'status-static' };
  const year = parseInt(lastTs.slice(0, 4), 10);
  if (year >= CURRENT_YEAR_JS) return { label: 'live (last: ' + lastTs.slice(0, 10) + ')', cls: 'status-live' };
  return { label: 'stale, last seen ' + lastTs.slice(0, 10), cls: 'status-static' };
}
fetch('/api/coverage').then(r => r.json()).then(cov => {
  const t = cov.totals;
  document.getElementById('cov-totals').innerHTML = [
    ['Garages', t.garages],
    ['Cities', t.cities],
    ['With known capacity', t.with_capacity],
    ['Countries', cov.countries.length],
  ].map(([l, n]) => `<div class="cov-stat"><span class="n">${n}</span><span class="l">${l}</span></div>`).join('');

  const ctbody = document.querySelector('#cov-country-table tbody');
  ctbody.innerHTML = cov.countries.map(c =>
    `<tr><td style="text-align:left">${c.country}</td><td>${c.garages}</td><td>${c.cities}</td><td>${c.sources}</td></tr>`
  ).join('');

  const stbody = document.querySelector('#cov-source-table tbody');
  stbody.innerHTML = cov.sources.map(s => {
    const st = sourceStatus(s.has_obs, s.last_ts);
    return `<tr><td style="text-align:left">${s.source_id}</td><td style="text-align:left">${s.country}</td>` +
      `<td>${s.ncities}</td><td>${s.total}</td><td>${s.has_cap}</td>` +
      `<td class="${st.cls}">${st.label}</td></tr>`;
  }).join('');
});

// ---- tabs ----
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  });
});

const CURRENT_YEAR_JS = new Date().getFullYear();
function freshnessTag(last_observed_ts) {
  if (!last_observed_ts) return ' — never reported';
  const year = parseInt(last_observed_ts.slice(0, 4), 10);
  if (year >= CURRENT_YEAR_JS) return ' — live (' + last_observed_ts.slice(0, 10) + ')';
  return ' — stale, last seen ' + last_observed_ts.slice(0, 10);
}
function garageLabel(g) {
  const cap = g.num_all ? g.num_all + ' spaces' : 'no capacity data';
  return g.place_name + ' (' + cap + ')' + freshnessTag(g.last_observed_ts);
}

function loadGarages(citySelectId, garageSelectId, cb) {
  const city = document.getElementById(citySelectId).value;
  const garageSel = document.getElementById(garageSelectId);
  garageSel.innerHTML = '<option value="">-- loading --</option>';
  garageSel.disabled = true;
  if (!city) { garageSel.innerHTML = '<option value="">-- select town first --</option>'; if (cb) cb(); return; }
  fetch('/api/garages?city=' + encodeURIComponent(city)).then(r => r.json()).then(garages => {
    garageSel.innerHTML = '<option value="">-- select garage --</option>';
    for (const g of garages) {
      const opt = document.createElement('option');
      opt.value = g.place_id;
      opt.textContent = garageLabel(g);
      garageSel.appendChild(opt);
    }
    garageSel.disabled = false;
    if (cb) cb();
  });
}

// ---- QUERY TAB ----
const qScope = document.getElementById('q-scope');
const qGarageWrap = document.getElementById('q-garage-wrap');
qScope.addEventListener('change', () => {
  qGarageWrap.style.display = qScope.value === 'garage' ? '' : 'none';
});
document.getElementById('q-city').addEventListener('change', () => loadGarages('q-city', 'q-garage'));

document.getElementById('q-go').addEventListener('click', () => {
  const scope = qScope.value;
  const city = document.getElementById('q-city').value;
  const garage = document.getElementById('q-garage').value;
  const operator = document.getElementById('q-operator').value;
  const start = document.getElementById('q-start').value;
  const end = document.getElementById('q-end').value;
  const granularity = document.getElementById('q-granularity').value;
  const errorEl = document.getElementById('q-error');
  errorEl.textContent = '';

  if (scope === 'garage' && !garage) { errorEl.textContent = 'Pick a garage.'; return; }
  if (scope === 'city' && !city) { errorEl.textContent = 'Pick a town.'; return; }

  const params = new URLSearchParams({
    scope_type: scope,
    scope_value: scope === 'garage' ? garage : city,
    granularity,
  });
  if (operator) params.set('operator', operator);
  if (start) params.set('start', start);
  if (end) params.set('end', end);

  document.getElementById('q-go').disabled = true;
  fetch('/api/query?' + params.toString()).then(r => r.json()).then(data => {
    document.getElementById('q-go').disabled = false;
    errorEl.textContent = data.error || '';
    document.getElementById('q-meta').textContent = data.meta || '';
    const dl = document.getElementById('q-dl');
    if (data.result) {
      dl.href = '/download.csv?' + params.toString();
      dl.style.display = 'inline-block';
    } else {
      dl.style.display = 'none';
    }
    renderQTable(data.result || []);
    renderQChart(data.result || []);
  });
});

function renderQTable(rows) {
  const table = document.getElementById('q-table');
  if (!rows.length) { table.innerHTML = ''; return; }
  let html = '<tr><th>Slot</th><th>Avg utilisation %</th><th>Samples</th><th>Garages</th></tr>';
  for (const r of rows) {
    html += `<tr><td>${r.slot}</td><td>${r.avg_utilisation_pct ?? '-'}</td><td>${r.sample_count}</td><td>${r.garages_count}</td></tr>`;
  }
  table.innerHTML = html;
}

function renderQChart(rows) {
  const chart = document.getElementById('q-chart');
  if (!rows.length) { chart.innerHTML = ''; return; }
  const w = 840, h = 220, barW = w / rows.length;
  let svg = `<svg width="${w}" height="${h+20}" xmlns="http://www.w3.org/2000/svg">`;
  rows.forEach((r, i) => {
    const val = r.avg_utilisation_pct || 0;
    const barH = (val / 100) * h;
    svg += `<rect class="bar-bg" x="${i*barW+2}" y="0" width="${barW-4}" height="${h}"></rect>`;
    svg += `<rect class="bar" x="${i*barW+2}" y="${h-barH}" width="${barW-4}" height="${barH}"></rect>`;
    svg += `<text x="${i*barW+barW/2}" y="${h+15}" font-size="10" text-anchor="middle">${r.slot.split('-')[0]}</text>`;
  });
  svg += '</svg>';
  chart.innerHTML = svg;
}

// ---- HEATMAP TAB ----
const hYear = document.getElementById('h-year');
for (let y = new Date().getFullYear(); y >= 2020; y--) {
  const opt = document.createElement('option');
  opt.value = y; opt.textContent = y;
  hYear.appendChild(opt);
}
document.getElementById('h-city').addEventListener('change', () => {
  loadGarages('h-city', 'h-garage', () => {
    document.getElementById('h-go').disabled = true;
  });
});
document.getElementById('h-garage').addEventListener('change', () => {
  document.getElementById('h-go').disabled = !document.getElementById('h-garage').value;
});

function utilToColor(pct) {
  // blue (low) -> yellow -> red (high), simple HSL interpolation
  const hue = 220 - (pct / 100) * 220; // 220 (blue) at 0% -> 0 (red) at 100%
  return `hsl(${hue}, 75%, 50%)`;
}

document.getElementById('h-go').addEventListener('click', () => {
  const place_id = document.getElementById('h-garage').value;
  const year = parseInt(hYear.value, 10);
  const granularity = parseInt(document.getElementById('h-granularity').value, 10);
  document.getElementById('h-error').textContent = '';
  document.getElementById('h-meta').textContent = '';
  document.getElementById('h-chart').innerHTML = 'Loading…';

  fetch('/api/heatmap?place_id=' + encodeURIComponent(place_id) + '&year=' + year + '&granularity=' + granularity)
    .then(r => r.json()).then(data => {
      document.getElementById('h-error').textContent = data.error || '';
      document.getElementById('h-meta').textContent = data.meta || '';
      document.getElementById('h-chart').innerHTML = '';
      if (data.grid) renderHeatmap(data.grid, year, granularity);
    });
});

const WEEKDAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function renderHeatmap(grid, year, granularity) {
  const slotsPerDay = 24 / granularity;
  const numWeeks = Math.ceil(366 / 7); // fixed 53 rows regardless of leap year, extra rows just stay empty
  const cellW = granularity === 1 ? 3 : granularity === 2 ? 5 : 9;
  const cellH = 10;
  const dayGap = 6;
  const leftPad = 34, topPad = 28;

  const dayBlockW = slotsPerDay * cellW;
  const w = leftPad + 7 * dayBlockW + 6 * dayGap + 4;
  const h = topPad + numWeeks * cellH + 4;

  const canvas = document.createElement('canvas');
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, w, h);
  ctx.font = '10px sans-serif';
  ctx.fillStyle = '#333';

  // weekday headers
  for (let wd = 0; wd < 7; wd++) {
    const x = leftPad + wd * (dayBlockW + dayGap);
    ctx.fillText(WEEKDAY_LABELS[wd], x, topPad - 8);
  }

  // week row labels: date of the Monday-ish start of that week (Jan 1 + week*7 days)
  const jan1 = new Date(year, 0, 1);
  function weekStartLabel(week) {
    const d = new Date(jan1);
    d.setDate(d.getDate() + week * 7);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }
  ctx.fillStyle = '#555';
  for (let week = 0; week < numWeeks; week += 4) {
    ctx.fillText(weekStartLabel(week), 0, topPad + week * cellH + cellH);
  }

  const cellMeta = []; // for hit-testing on hover
  for (let week = 0; week < numWeeks; week++) {
    const weekGrid = grid[String(week)];
    for (let wd = 0; wd < 7; wd++) {
      const wdGrid = weekGrid ? weekGrid[String(wd)] : undefined;
      for (let s = 0; s < slotsPerDay; s++) {
        const slotStart = s * granularity;
        const val = wdGrid ? wdGrid[String(slotStart)] : undefined;
        const x = leftPad + wd * (dayBlockW + dayGap) + s * cellW;
        const y = topPad + week * cellH;
        ctx.fillStyle = (val === undefined || val === null) ? '#eee' : utilToColor(val);
        ctx.fillRect(x, y, cellW - 0.5, cellH - 0.5);
        cellMeta.push({ x, y, week, wd, slotStart, val });
      }
    }
  }

  const wrap = document.getElementById('h-chart');
  wrap.appendChild(canvas);
  const tooltip = document.getElementById('heatmap-tooltip');
  canvas.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const week = Math.floor((my - topPad) / cellH);
    if (week < 0 || week >= numWeeks || my < topPad) { tooltip.style.display = 'none'; return; }
    let found = null;
    for (let wd = 0; wd < 7; wd++) {
      const blockX = leftPad + wd * (dayBlockW + dayGap);
      if (mx >= blockX && mx < blockX + dayBlockW) {
        const s = Math.floor((mx - blockX) / cellW);
        const slotStart = s * granularity;
        const weekGrid = grid[String(week)];
        const val = weekGrid && weekGrid[String(wd)] ? weekGrid[String(wd)][String(slotStart)] : undefined;
        found = { wd, slotStart, val };
        break;
      }
    }
    if (!found) { tooltip.style.display = 'none'; return; }
    const label = `week of ${weekStartLabel(week)} — ${WEEKDAY_LABELS[found.wd]} ${String(found.slotStart).padStart(2,'0')}:00-${String(found.slotStart+granularity).padStart(2,'0')}:00 — ${found.val === undefined ? 'no data' : found.val + '%'}`;
    tooltip.textContent = label;
    tooltip.style.left = (e.clientX + 12) + 'px';
    tooltip.style.top = (e.clientY + 12) + 'px';
    tooltip.style.display = 'block';
  });
  canvas.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });
}

// ---- COMPARE TAB ----
let entityCount = 0;
function addEntityRow() {
  const id = entityCount++;
  const wrap = document.getElementById('c-entities');
  const row = document.createElement('div');
  row.className = 'entity-row';
  row.dataset.id = id;
  row.innerHTML = `
    <select class="c-scope">
      <option value="city">Whole town</option>
      <option value="garage">Single garage</option>
    </select>
    <select class="c-city"><option value="">-- town --</option>${CITIES.map(c=>`<option value="${c}">${c}</option>`).join('')}</select>
    <select class="c-garage" disabled><option value="">-- select town first --</option></select>
    <button type="button" class="c-remove">remove</button>
  `;
  wrap.appendChild(row);
  const scopeSel = row.querySelector('.c-scope');
  const citySel = row.querySelector('.c-city');
  const garageSel = row.querySelector('.c-garage');
  scopeSel.addEventListener('change', () => {
    garageSel.style.display = scopeSel.value === 'garage' ? '' : 'none';
  });
  citySel.addEventListener('change', () => {
    const city = citySel.value;
    garageSel.innerHTML = '<option value="">-- loading --</option>';
    garageSel.disabled = true;
    if (!city) return;
    fetch('/api/garages?city=' + encodeURIComponent(city)).then(r => r.json()).then(garages => {
      garageSel.innerHTML = '<option value="">-- select garage --</option>';
      for (const g of garages) {
        const opt = document.createElement('option');
        opt.value = g.place_id; opt.textContent = garageLabel(g);
        opt.dataset.name = g.place_name;
        garageSel.appendChild(opt);
      }
      garageSel.disabled = false;
    });
  });
  row.querySelector('.c-remove').addEventListener('click', () => row.remove());
}
document.getElementById('c-add').addEventListener('click', addEntityRow);

const COLORS = ['#3b6fd6', '#d63b3b', '#2ea36b', '#c98a1c', '#8a3bd6', '#3bc9c9'];

document.getElementById('c-go').addEventListener('click', () => {
  const start = document.getElementById('c-start').value;
  const end = document.getElementById('c-end').value;
  const errorEl = document.getElementById('c-error');
  errorEl.textContent = '';

  const entities = [];
  document.querySelectorAll('#c-entities .entity-row').forEach(row => {
    const scope = row.querySelector('.c-scope').value;
    const city = row.querySelector('.c-city').value;
    const garage = row.querySelector('.c-garage').value;
    if (scope === 'city' && city) entities.push({scope_type: 'city', scope_value: city});
    if (scope === 'garage' && garage) entities.push({scope_type: 'garage', scope_value: garage, label: row.querySelector('.c-garage option:checked').dataset.name});
  });
  if (!entities.length) { errorEl.textContent = 'Add at least one town or garage.'; return; }

  const body = {entities, start: start || null, end: end || null};
  document.getElementById('c-go').disabled = true;
  fetch('/api/compare', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
    .then(r => r.json()).then(data => {
      document.getElementById('c-go').disabled = false;
      if (data.error) { errorEl.textContent = data.error; return; }
      renderCompareChart(data.series);
      const dl = document.getElementById('c-dl');
      dl.href = '/download_compare.csv?payload=' + encodeURIComponent(JSON.stringify(body));
      dl.style.display = 'inline-block';
    });
});

function renderCompareChart(series) {
  const chart = document.getElementById('c-chart');
  if (!series.length) { chart.innerHTML = 'No data.'; return; }
  const allDates = [...new Set(series.flatMap(s => s.data.map(d => d.date)))].sort();
  if (!allDates.length) { chart.innerHTML = 'No data in range.'; return; }
  const w = 840, h = 300, padL = 40, padB = 20;
  const xStep = (w - padL) / Math.max(1, allDates.length - 1);
  let svg = `<svg width="${w}" height="${h+40}" xmlns="http://www.w3.org/2000/svg">`;
  for (let pct = 0; pct <= 100; pct += 25) {
    const y = h - (pct/100)*h;
    svg += `<line x1="${padL}" y1="${y}" x2="${w}" y2="${y}" stroke="#eee"></line>`;
    svg += `<text x="0" y="${y+4}" font-size="10">${pct}%</text>`;
  }
  series.forEach((s, si) => {
    const color = COLORS[si % COLORS.length];
    const byDate = Object.fromEntries(s.data.map(d => [d.date, d.avg_utilisation_pct]));
    let points = [];
    allDates.forEach((d, i) => {
      const v = byDate[d];
      if (v === undefined) return;
      const x = padL + i * xStep, y = h - (v/100)*h;
      points.push(x + ',' + y);
    });
    svg += `<polyline points="${points.join(' ')}" fill="none" stroke="${color}" stroke-width="2"></polyline>`;
  });
  const step = Math.max(1, Math.floor(allDates.length / 10));
  allDates.forEach((d, i) => {
    if (i % step === 0) svg += `<text x="${padL+i*xStep}" y="${h+15}" font-size="9" text-anchor="middle">${d.slice(5)}</text>`;
  });
  svg += '</svg>';
  let legend = '<div>' + series.map((s,si) => `<span class="legend-line" style="background:${COLORS[si%COLORS.length]}"></span>${s.label}`).join('&nbsp;&nbsp;') + '</div>';
  chart.innerHTML = legend + svg;
}
</script>
"""


@app.route("/")
def index():
    return render_template_string(PAGE)


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
        "SUM(CASE WHEN num_all IS NOT NULL THEN 1 ELSE 0 END) FROM lots_meta"
    ).fetchone()
    sources = conn.execute(
        """SELECT source_id,
                  COUNT(DISTINCT city_name) ncities,
                  COUNT(*) total,
                  SUM(CASE WHEN num_all IS NOT NULL THEN 1 ELSE 0 END) has_cap,
                  SUM(CASE WHEN last_observed_ts IS NOT NULL THEN 1 ELSE 0 END) has_obs,
                  MAX(last_observed_ts) last_ts
           FROM lots_meta WHERE source_id IS NOT NULL
           GROUP BY source_id ORDER BY total DESC"""
    ).fetchall()
    conn.close()

    source_list = [dict(r) for r in sources]
    for s in source_list:
        s["country"] = SOURCE_COUNTRY.get(s["source_id"], "Germany")

    by_country: dict[str, dict] = defaultdict(lambda: {"garages": 0, "cities": set(), "sources": 0})
    for s in source_list:
        c = by_country[s["country"]]
        c["garages"] += s["total"]
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
        {"country": name, "garages": v["garages"], "cities": len(v["cities"]), "sources": v["sources"]}
        for name, v in sorted(by_country.items(), key=lambda kv: -kv[1]["garages"])
    ]

    return jsonify(
        {
            "totals": {"cities": totals[0], "garages": totals[1], "with_capacity": totals[2]},
            "countries": countries,
            "sources": source_list,
        }
    )


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
    q += " ORDER BY place_name"
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
        data, error = compute_daily_series(e["scope_type"], e["scope_value"], None, start, end)
        if error:
            return jsonify({"error": f"{e['scope_value']}: {error}"})
        label = e.get("label") or label_for(e["scope_type"], e["scope_value"], None)
        series.append({"label": label, "data": data})
    return jsonify({"series": series, "error": None})


@app.route("/download_compare.csv")
def download_compare_csv():
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
