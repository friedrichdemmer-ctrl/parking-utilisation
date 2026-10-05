"""The competitive set: every garage the former parkingsimulator project researched
(3,881 garages, 302 cities, 7 countries), with operator, location, capacity and
published price. See competitive/README.md.

Loaded from competitive/european_parking.csv; competitive/links.csv says which of
these garages is also one of ours (so a map point can show live occupancy and
link to the garage's page). Operator colours are the old app's, ported
unchanged so every operator keeps the colour it had.
"""

from __future__ import annotations

import csv
import hashlib
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).resolve().parent / "competitive"

# country -> the file prefix of its research log
NOTE_FILES = {"Germany": "de", "Netherlands": "nl", "Ireland": "ie", "Belgium": "be",
              "UK": "uk", "Denmark": "dk", "France": "fr"}

BASE_OPERATOR_COLORS = {
    "Q-Park": "#3366CC",
    "APCOA": "#8FB8F0",
    "Contipark": "#E0574A",
    "B+B Parkhaus": "#F2A7A0",
}
FALLBACK_PALETTE = [
    "#2CA02C", "#9467BD", "#8C564B", "#17BECF", "#BCBD22", "#FF7F0E", "#E377C2",
    "#1A9850", "#6A3D9A", "#B15928", "#A6CEE3", "#FDBF6F",
    "#66C2A5", "#FC8D62", "#8DA0CB", "#E78AC3", "#A6D854", "#FFD92F",
    "#7FC97F", "#BEAED4", "#FDC086", "#386CB0", "#F0027F", "#BF5B17",
]


def _stable_index(name: str, n: int) -> int:
    """Same operator, same colour in every city and every run (Python's hash() is
    randomised per process, so it is not used)."""
    return int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % n


def operator_colors(operators) -> dict[str, str]:
    """Each operator's hash-stable colour; a collision between two operators in the
    same city is resolved by probing to the next free slot, so no two operators on
    one map share a colour."""
    colors, used = {}, set()
    n = len(FALLBACK_PALETTE)
    for op in operators:
        if op in BASE_OPERATOR_COLORS:
            colors[op] = BASE_OPERATOR_COLORS[op]
    for op in sorted(op for op in operators if op not in BASE_OPERATOR_COLORS):
        idx, offset = _stable_index(op, n), 0
        while idx in used and offset < n:
            offset += 1
            idx = (idx + 1) % n
        used.add(idx)
        colors[op] = FALLBACK_PALETTE[idx]
    return colors


def _num(v: str | None) -> float | None:
    v = (v or "").strip()
    try:
        return float(v)
    except ValueError:
        return None


@lru_cache(maxsize=1)
def garages() -> dict[tuple[str, str], list[dict]]:
    """{(country, city): [garage, ...]} in file order."""
    out: dict[tuple[str, str], list[dict]] = {}
    with open(DIR / "european_parking.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cap = _num(r["capacity"])
            out.setdefault((r["country"], r["city"]), []).append({
                "id": r["id"], "name": r["name"], "operator": r["operator"],
                "lat": float(r["lat"]), "lon": float(r["lon"]),
                "capacity": int(cap) if cap is not None else None,
                "hourly_rate": _num(r["hourly_rate"]), "daily_cap": _num(r["daily_cap"]),
                "has_ev": (r.get("has_ev") or "").strip().lower() == "true",
                "address": r["address"] or None, "source_url": r["source_url"] or None,
                "currency": r["currency"] or "EUR",
            })
    return out


@lru_cache(maxsize=1)
def links() -> dict[tuple[str, str, str], dict]:
    """{(country, city, id): {"place_id", "dist_m"}} -- the garages that are also ours."""
    path = DIR / "links.csv"
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {(r["country"], r["city"], r["id"]): {"place_id": r["place_id"], "dist_m": int(r["dist_m"] or 0)}
                for r in csv.DictReader(f)}


@lru_cache(maxsize=1)
def _notes() -> dict[tuple[str, str], str]:
    out = {}
    for country, cc in NOTE_FILES.items():
        path = DIR / "notes" / f"{cc}_progress.csv"
        if path.exists():
            with open(path, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    out[(country, r["city"])] = r.get("notes") or ""
    return out


def note(country: str, city: str) -> str | None:
    return _notes().get((country, city)) or None


def countries() -> list[dict]:
    by: dict[str, list[list[dict]]] = {}
    for (country, _), gs in garages().items():
        by.setdefault(country, []).append(gs)
    return sorted(({"country": c, "cities": len(cs), "garages": sum(len(g) for g in cs)} for c, cs in by.items()),
                  key=lambda r: -r["garages"])


def cities(country: str) -> list[dict]:
    lk = links()
    return sorted(
        ({"city": city, "garages": len(gs), "operators": len({g["operator"] for g in gs}),
          "linked": sum(1 for g in gs if (c, city, g["id"]) in lk)}
         for (c, city), gs in garages().items() if c == country),
        key=lambda r: r["city"].lower())


def city_map(country: str, city: str) -> dict | None:
    gs = garages().get((country, city))
    if gs is None:
        return None
    lk = links()
    ops = sorted({g["operator"] for g in gs})
    colors = operator_colors(ops)
    return {
        "country": country, "city": city, "currency": gs[0]["currency"],
        "operators": [{"name": o, "color": colors[o], "garages": sum(1 for g in gs if g["operator"] == o)} for o in ops],
        "garages": [dict(g, color=colors[g["operator"]], place_id=(lk.get((country, city, g["id"])) or {}).get("place_id"))
                    for g in gs],
        "notes": note(country, city),
    }
