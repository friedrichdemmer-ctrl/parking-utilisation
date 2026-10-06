"""A city briefing: the numbers we hold for one city, plus the sourced context we have researched.

Computed on request from the latest utilisation and trends reports and the competitive set:

  trend       the city's occupancy index since 2020 against the German index (trends report),
              where the city has at least three garages with a long history;
  operators   one row per operator: how many garages and spaces it has in the city (all garages
              the competitive set lists), its median hourly rate and day ticket, how many have EV
              charging recorded, and -- for the garages we also measure -- weekday occupancy;
  price       within-city correlation of tariff with weekday occupancy, with its sample size;
  ev          how many garages have charging recorded, and how many have no record either way.

Curated context (annotations/cities/<country>_<city>.json) is attached untouched: items with a
date, topic, source and confidence, written from sources only (see annotations/README.md).
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import unicodedata
from pathlib import Path

import competitive
import garage_prices
from garage_types import classify

NOTES_DIR = Path(__file__).resolve().parent / "annotations" / "cities"
MIN_OPERATOR_GARAGES = 2          # smaller operators are pooled into "Other"
LEGAL = re.compile(r"\b(gmbh|mbh|ag|spa|s\.p\.a\.|b\.v\.|bv|kg|& co\.?|co\.|ltd|limited|sas|sa|se)\b\.?", re.I)
ALIASES = [("apcoa", "APCOA"), ("goldbeck", "Goldbeck"), ("contipark", "Contipark"), ("pbg", "PBG"),
           ("q-park", "Q-Park"), ("qpark", "Q-Park"), ("interparking", "Interparking"), ("effia", "Effia"),
           ("indigo", "Indigo"), ("saemark", "Saemark"), ("parkplatz.de", "parkplatz.de"), ("bahnpark", "DB BahnPark"),
           ("db bahnpark", "DB BahnPark"), ("park one", "Park One"), ("ece", "ECE"), ("gemeente amsterdam", "Gemeente Amsterdam"),
           ("stadt dresden", "Stadt Dresden"), ("opg", "OPG"), ("orbe", "ORBE"), ("borchard", "Borchard Group")]


def slug(country: str, city: str) -> str:
    text = unicodedata.normalize("NFKD", f"{country}_{city}").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def canonical_operator(name: str | None) -> str:
    name = (name or "").strip()
    if not name:
        return "Unknown"
    low = name.lower()
    for key, label in ALIASES:
        if low.startswith(key):
            return label
    name = re.sub(r"\s*\(.*$", "", name)          # "X (marketed via Y)" -> "X"
    name = LEGAL.sub("", name)
    return re.sub(r"\s+", " ", name).strip(" ,-/") or "Unknown"


SHOPPING = "Shopping centres (own car parks)"
CHAINS = {label for _, label in ALIASES}


def operator_label(operator: str | None, garage_name: str | None) -> str:
    """The operator, except that a shopping centre's own car park (named after the centre, which is
    listed as its 'operator') goes into one group, so a mall does not read as a competing operator."""
    label = canonical_operator(operator)
    if label not in CHAINS and classify(garage_name) == "shopping":
        return SHOPPING
    return label


def _median(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 2) if values else None


def _pearson(xs, ys):
    n = len(xs)
    if n < 8:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy), 2) if sx and sy else None


def _ev_raw(country: str, city: str) -> dict:
    """EV charging recorded per garage id: True / False / None (nothing recorded either way)."""
    out = {}
    with open(competitive.DIR / "european_parking.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["country"] == country and r["city"] == city:
                v = (r.get("has_ev") or "").strip().lower()
                out[r["id"]] = True if v in ("true", "yes") else False if v in ("false", "no") else None
    return out


def notes(country: str, city: str) -> dict | None:
    """Fact-checked sources (cities/<slug>.json) plus, where written, the briefing prose that cites
    them by item id (cities/narratives/<slug>.json)."""
    path = NOTES_DIR / f"{slug(country, city)}.json"
    if not path.exists():
        return None
    out = json.loads(path.read_text(encoding="utf-8"))
    narrative = NOTES_DIR / "narratives" / f"{slug(country, city)}.json"
    if narrative.exists():
        out["narrative"] = json.loads(narrative.read_text(encoding="utf-8"))
    return out


def build(country: str, city: str, util_garages: list[dict], trends: dict | None) -> dict | None:
    comp = competitive.garages().get((country, city), [])
    links = {gid: v["place_id"] for (c, ci, gid), v in competitive.links().items() if (c, ci) == (country, city)}
    prices = garage_prices.prices()
    measured = [g for g in util_garages if g["country"] == country and g["city"] == city and g.get("weekday_avg") is not None]
    if not comp and not measured:
        return None
    ev = _ev_raw(country, city)

    # ---- operators: the competitive set is the broad view, our measurements the subset
    rows: dict[str, dict] = {}
    for g in comp:
        op = operator_label(g["operator"], g["name"])
        r = rows.setdefault(op, {"operator": op, "garages": 0, "spaces": 0, "rates": [], "tickets": [], "ev": 0, "ev_known": 0,
                                 "measured": 0, "m_spaces": 0, "m_occ": 0.0, "m_peak": 0.0})
        r["garages"] += 1
        r["spaces"] += g["capacity"] or 0
        if g["hourly_rate"] is not None:
            r["rates"].append(g["hourly_rate"])
        if g["daily_cap"] is not None:
            r["tickets"].append(g["daily_cap"])
        e = ev.get(g["id"])
        r["ev_known"] += e is not None
        r["ev"] += bool(e)
    # our own measurements, each assigned to an operator: via the competitive-set link where there
    # is one, else via the researched tariff file, else "Unknown"
    op_of_place = {}
    for gid, pid in links.items():
        cg = next((x for x in comp if x["id"] == gid), None)
        if cg:
            op_of_place[pid] = operator_label(cg["operator"], cg["name"])
    new_row = lambda op: {"operator": op, "garages": 0, "spaces": 0, "rates": [], "tickets": [], "ev": 0, "ev_known": 0,
                          "measured": 0, "m_spaces": 0, "m_occ": 0.0, "m_peak": 0.0}
    unlisted: set[str] = set()
    for g in measured:
        if not g["capacity"]:
            continue
        op = op_of_place.get(g["id"]) or operator_label((prices.get(g["id"]) or {}).get("operator"), g["name"])
        r = rows.get(op)
        if r is None or (op in unlisted):               # an operator the competitive set does not list here
            r = rows[op] = rows.get(op) or new_row(op)
            unlisted.add(op)
            r["garages"] += 1
            r["spaces"] += g["capacity"]                # counted once each: these garages are not in the competitive set
            p = prices.get(g["id"]) or {}
            if p.get("hourly_rate") is not None and not p.get("transit_conditional"):
                r["rates"].append(p["hourly_rate"])
            if p.get("daily_cap") is not None and not p.get("transit_conditional"):
                r["tickets"].append(p["daily_cap"])
        elif not comp:                                  # city with no competitive listing: measured garages ARE the supply
            r["garages"] += 1
            r["spaces"] += g["capacity"]
            p = prices.get(g["id"]) or {}
            if p.get("hourly_rate") is not None and not p.get("transit_conditional"):
                r["rates"].append(p["hourly_rate"])
            if p.get("daily_cap") is not None and not p.get("transit_conditional"):
                r["tickets"].append(p["daily_cap"])
        r["measured"] += 1
        r["m_spaces"] += g["capacity"]
        r["m_occ"] += g["weekday_avg"] * g["capacity"]
        r["m_peak"] += g["peak"]["occ"] * g["capacity"]

    city_spaces = sum(r["spaces"] for r in rows.values()) or 1
    # an operator is pooled only if it is both small in garages and in spaces; a single large garage keeps its name
    keep = lambda r: r["garages"] >= MIN_OPERATOR_GARAGES or r["spaces"] / city_spaces >= 0.03
    big = [r for r in rows.values() if keep(r)]
    small = [r for r in rows.values() if not keep(r)]
    if len(small) == 1:
        big.append(small[0])
    elif small:
        pooled = {"operator": f"Other ({len(small)} operators)", "garages": 0, "spaces": 0, "rates": [], "tickets": [], "ev": 0,
                  "ev_known": 0, "measured": 0, "m_spaces": 0, "m_occ": 0.0, "m_peak": 0.0}
        for r in small:
            for k in ("garages", "spaces", "ev", "ev_known", "measured", "m_spaces", "m_occ", "m_peak"):
                pooled[k] += r[k]
            pooled["rates"] += r["rates"]
            pooled["tickets"] += r["tickets"]
        big.append(pooled)
    total_spaces = sum(r["spaces"] for r in big) or 1
    operators = []
    for r in sorted(big, key=lambda r: -r["spaces"]):
        operators.append({
            "operator": r["operator"], "garages": r["garages"], "spaces": r["spaces"],
            "share_of_spaces": round(100 * r["spaces"] / total_spaces, 1),
            "median_rate": _median(r["rates"]), "priced": len(r["rates"]), "median_day_ticket": _median(r["tickets"]),
            "ev": r["ev"], "ev_known": r["ev_known"],
            "measured": r["measured"],
            "weekday_occupancy": round(100 * r["m_occ"] / r["m_spaces"], 1) if r["m_spaces"] else None,
            "peak_occupancy": round(100 * r["m_peak"] / r["m_spaces"], 1) if r["m_spaces"] else None,
        })

    # ---- price against occupancy among the garages we measure and have a price for
    xs, ys = [], []
    for g in measured:
        pid = g["id"]
        p = prices.get(pid)
        if not p:
            cgid = next((k for k, v in links.items() if v == pid), None)
            cg = next((x for x in comp if x["id"] == cgid), None) if cgid else None
            rate = cg["hourly_rate"] if cg else None
        else:
            rate = None if p.get("transit_conditional") else p.get("hourly_rate")
        if rate is not None:
            xs.append(rate)
            ys.append(g["weekday_avg"] * 100)

    # ---- trend
    trend = None
    if trends:
        c = next((c for c in trends["yoy"]["cities"] if c["city"] == city and c["country"] == country), None)
        if c:
            trend = {"garages": c["garages"], "now": c["now"], "then": c["then"], "change_pts": c["change_pts"],
                     "window": trends["yoy"]["last"], "index": c.get("index"),
                     "germany": trends["index"] if country == "Germany" else None, "months": trends["months"]}

    ev_vals = list(ev.values())
    return {
        "country": country, "city": city,
        "currency": comp[0]["currency"] if comp else next((p["currency"] for g in measured if (p := prices.get(g["id"])) and p.get("currency")), "EUR"),
        "garages": len(comp) or len(measured), "spaces": sum(r["spaces"] for r in rows.values()),
        "research_set": bool(comp),
        "measured": len(measured),
        "operators": operators,
        "price_occupancy": {"r": _pearson(xs, ys), "n": len(xs)},
        "ev": {"with_ev": sum(1 for v in ev_vals if v), "recorded_no": sum(1 for v in ev_vals if v is False),
               "unknown": sum(1 for v in ev_vals if v is None), "total": len(ev_vals)} if ev_vals else None,
        "trend": trend,
        "notes": notes(country, city),
    }
