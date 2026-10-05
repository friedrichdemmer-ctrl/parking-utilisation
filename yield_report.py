#!/usr/bin/env python3
"""Revenue and yield: what a parking space earns, and what that depends on.

Joins the occupancy we measure (utilisation_report.py) to the tariffs we
hold (garage_prices.py) and the revenue model (revenue_model.py), for every
garage that has all three. Answers three questions the separate reports
cannot:

- What does a space earn in a year, and how much does that vary?
- Does charging more empty a garage? (Measured, not assumed.)
- Where is there pricing headroom: garages that are busy and cheap?

Correlations are reported twice: once per garage and once per distinct
published tariff, because a dozen garages on one operator's city-wide price
are one price observation. Quote the per-tariff figure.

Left out: free sites and transit-inclusive park-and-ride, whose posted fee
is not what the site takes; garages without a published hourly rate; and
anything the revenue model cannot estimate. Garages above
revenue_model.HIGH_TARIFF an hour are kept but counted separately, since
the model overstates them (see its calibration note).

Prices are converted to euros at RATES below so cities can be compared;
the rate used is reported so a reader can undo it.

Writes JSON (default: <db dir>/reports/yield_<date>.json);
`--html <yield.json> <page.html>` renders it via yield_template.html.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("PARKING_DB_PATH", Path(__file__).parent / "data" / "parking.db"))
REPORTS_DIR = DB_PATH.parent / "reports"

# indicative, for comparability only; October 2026
RATES = {"EUR": 1.0, "CHF": 1.07, "GBP": 1.15, "DKK": 0.134}
MIN_CITY = 8          # garages before a city gets its own row
MIN_TYPE = 8
RATE_BANDS = [(0, 1.5), (1.5, 2.5), (2.5, 3.5), (3.5, 5.0), (5.0, 99.0)]


def _corr(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 10:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy), 3) if sx and sy else None


def _med(vals: list[float]) -> float | None:
    return round(statistics.median(vals), 1) if vals else None


def build(report_path: Path | None = None) -> dict:
    import garage_prices as gp
    import revenue_model as rm
    from garage_types import LABELS, classify

    path = report_path or sorted(REPORTS_DIR.glob("utilisation_*.json"), key=lambda p: p.stat().st_mtime)[-1]
    util = json.loads(path.read_text(encoding="utf-8"))
    prices = gp.prices()
    garages, skipped = [], defaultdict(int)
    for g in util["garages"]:
        p = prices.get(g["id"])
        if not p:
            skipped["no tariff on file"] += 1
            continue
        if p.get("free") or p.get("transit_conditional"):
            skipped["free or transit-inclusive park-and-ride"] += 1
            continue
        if not p.get("hourly_rate"):
            skipped["no published hourly rate"] += 1
            continue
        m = gp.modelled_revenue(g["profile"], g["capacity"], p, g["name"])
        if not m or not m.get("visitor"):
            skipped["takings could not be estimated"] += 1
            continue
        cur = p.get("currency") or "EUR"
        fx = RATES.get(cur, 1.0)
        garages.append({
            "id": g["id"], "name": g["name"], "city": g["city"], "country": g["country"],
            "capacity": g["capacity"], "type": classify(g["name"]), "type_label": LABELS[classify(g["name"])],
            "currency": cur, "rate": p["hourly_rate"], "rate_eur": round(p["hourly_rate"] * fx, 2),
            "daily_cap": p.get("daily_cap"), "operator": p.get("operator"),
            "occ": round(g["avg"] * 100, 1), "peak": round(g["peak"]["occ"] * 100, 1),
            "full_hours": g["full_hours"],
            "yield_eur": round(m["per_space_year"] * fx), "week_eur": round(m["total"] * fx),
            "contract_share": round(m["contract"] / (m["contract"] + m["visitor"]), 3) if m["contract"] + m["visitor"] else None,
            "high_tariff": bool(m.get("high_tariff")),
        })
    ok = [g for g in garages if not g["high_tariff"]]          # the reliable set

    def group(key, min_n):
        out = []
        buckets = defaultdict(list)
        for g in ok:
            buckets[key(g)].append(g)
        for k, b in buckets.items():
            if len(b) < min_n:
                continue
            out.append({"key": k, "garages": len(b), "spaces": sum(x["capacity"] for x in b),
                        "rate": _med([x["rate_eur"] for x in b]), "occ": _med([x["occ"] for x in b]),
                        "peak": _med([x["peak"] for x in b]), "yield": _med([x["yield_eur"] for x in b]),
                        "currency": b[0]["currency"] if len({x["currency"] for x in b}) == 1 else "EUR"})
        return sorted(out, key=lambda r: -(r["yield"] or 0))

    bands = []
    for lo, hi in RATE_BANDS:
        b = [g for g in ok if lo <= g["rate_eur"] < hi]
        if len(b) >= 5:
            bands.append({"from": lo, "to": hi, "garages": len(b), "occ": _med([x["occ"] for x in b]),
                          "peak": _med([x["peak"] for x in b]), "yield": _med([x["yield_eur"] for x in b])})

    # Garages under one operator in one city often share a single published
    # tariff -- 12 Turin sites at EUR 1.00, 10 in Bochum at EUR 1.90. They are
    # one price observation, not twelve, so the correlations are computed over
    # clusters as well, and the cluster figure is the one to quote.
    clusters = defaultdict(list)
    for g in ok:
        clusters[(g["city"], g["operator"] or "?", g["rate_eur"])].append(g)
    cl = [{"rate": k[2], "occ": statistics.median([x["occ"] for x in b]),
           "yield": statistics.median([x["yield_eur"] for x in b]), "n": len(b)}
          for k, b in clusters.items()]

    rates = [g["rate_eur"] for g in ok]
    occs = [g["occ"] for g in ok]
    yields = [g["yield_eur"] for g in ok]
    med_rate, med_occ = statistics.median(rates), statistics.median(occs)
    # busy and cheap: both sides of the median, ranked by how far from it
    headroom = sorted(
        [g for g in ok if g["occ"] > med_occ and g["rate_eur"] < med_rate and g["capacity"] >= 100],
        key=lambda g: -((g["occ"] / med_occ) * (med_rate / g["rate_eur"])))[:25]
    quiet_dear = sorted(
        [g for g in ok if g["occ"] < med_occ and g["rate_eur"] > med_rate and g["capacity"] >= 100],
        key=lambda g: -((med_occ / max(g["occ"], 1)) * (g["rate_eur"] / med_rate)))[:15]

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": util["window"],
        "garages": len(garages), "reliable": len(ok), "high_tariff": len(garages) - len(ok),
        "spaces": sum(g["capacity"] for g in ok),
        "cities": len({(g["country"], g["city"]) for g in ok}),
        "countries": len({g["country"] for g in ok}),
        "skipped": dict(sorted(skipped.items(), key=lambda kv: -kv[1])),
        "median": {"rate": round(med_rate, 2), "occ": round(med_occ, 1), "yield": round(statistics.median(yields))},
        "spread": {"p10": round(sorted(yields)[len(yields) // 10]), "p90": round(sorted(yields)[9 * len(yields) // 10])},
        "correlations": {
            "rate_vs_occupancy": _corr(rates, occs),
            "rate_vs_yield": _corr(rates, yields),
            "occupancy_vs_yield": _corr(occs, yields),
            "rate_vs_peak": _corr(rates, [g["peak"] for g in ok]),
        },
        "correlations_by_tariff": {
            "groups": len(cl),
            "rate_vs_occupancy": _corr([c["rate"] for c in cl], [c["occ"] for c in cl]),
            "rate_vs_yield": _corr([c["rate"] for c in cl], [c["yield"] for c in cl]),
            "largest_group": max(c["n"] for c in cl),
        },
        "bands": bands,
        "cities_table": group(lambda g: g["city"], MIN_CITY),
        "countries_table": group(lambda g: g["country"], MIN_CITY),
        "types_table": group(lambda g: g["type_label"], MIN_TYPE),
        "headroom": headroom, "quiet_dear": quiet_dear,
        "scatter": [{"r": g["rate_eur"], "o": g["occ"], "c": g["capacity"], "y": g["yield_eur"],
                     "n": g["name"], "t": g["city"], "k": g["type"]} for g in ok],
        "fx": RATES, "high_tariff_from": rm.HIGH_TARIFF,
        "calibration": {"qpark_reported": 2297, "qpark_modelled": 2285},
    }


def render_html(report: dict) -> str:
    data = f"const Y={json.dumps(report, ensure_ascii=False, separators=(',', ':'))};\n"
    return (Path(__file__).parent / "yield_template.html").read_text(encoding="utf-8").replace("/*DATA*/", data)


def main() -> None:
    if sys.argv[1:2] == ["--html"]:
        Path(sys.argv[3]).write_text(render_html(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))), encoding="utf-8")
        print(sys.argv[3])
        return
    report = build()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"yield_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{out}: {report['reliable']} garages, median EUR {report['median']['yield']:,}/space/year")


if __name__ == "__main__":
    main()
