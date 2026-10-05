"""Measured occupancy to calibrate and validate against.

The utilisation report holds a 168-slot typical week per garage that we measure.
For the garages the competitive set also lists (competitive/links.csv) this takes the
weekday hours the simulator covers (06:00-21:59) and the overnight level, and stores
them compactly in calibration_targets.json:

  {"Germany|Lyon": {"<garage id>": {"hours": [16 weekday means in %], "night": 12.0}}}

    python3 -m simulator.targets <utilisation_report.json>

The report JSON is built on the server (reports_job.py); fetch it as in the memory
note, then run this. Only garages with a full typical week are used.
"""

import json
import statistics
import sys
from pathlib import Path

import competitive

OUT = Path(__file__).resolve().parent / "calibration_targets.json"
HOURS = range(6, 22)
NIGHT = (2, 3, 4)


def build(report_path: str) -> dict:
    report = json.loads(Path(report_path).read_text())
    by_place = {g["id"]: g for g in report["garages"] if g.get("profile")}
    out: dict[str, dict] = {}
    for (country, city, gid), link in competitive.links().items():
        g = by_place.get(link["place_id"])
        if not g:
            continue
        prof = g["profile"]
        hours = []
        for h in HOURS:
            vals = [prof[d * 24 + h] for d in range(5) if prof[d * 24 + h] is not None]
            hours.append(statistics.mean(vals) if vals else None)
        night = [prof[d * 24 + h] for d in range(5) for h in NIGHT if prof[d * 24 + h] is not None]
        if any(v is None for v in hours) or not night:
            continue
        out.setdefault(f"{country}|{city}", {})[gid] = {
            "hours": [round(v, 1) for v in hours], "night": round(statistics.mean(night), 1),
            "place_id": link["place_id"]}
    return {"window": report["window"], "cities": out, "city_levels": city_levels(report)}


def city_levels(report: dict) -> dict:
    """Capacity-weighted weekday 06-21 occupancy over EVERY garage we measure in a city
    (not only the ones the competitive set lists), for cities with at least 3 of them."""
    by: dict[str, list] = {}
    for g in report["garages"]:
        prof, cap = g.get("profile"), g.get("capacity")
        if not prof or not cap:
            continue
        hours = [prof[d * 24 + h] for d in range(5) for h in HOURS if prof[d * 24 + h] is not None]
        night = [prof[d * 24 + h] for d in range(5) for h in NIGHT if prof[d * 24 + h] is not None]
        if len(hours) < 60 or not night:
            continue
        by.setdefault(f"{g['country']}|{g['city']}", []).append((float(cap), statistics.mean(hours), statistics.mean(night)))
    return {k: {"n": len(v), "level": round(sum(c * o for c, o, _ in v) / sum(c for c, _, _ in v), 1),
                "night": round(statistics.median(n for _, _, n in v), 1)}
            for k, v in by.items() if len(v) >= 3}


if __name__ == "__main__":
    data = build(sys.argv[1])
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    sizes = sorted(((len(v), k) for k, v in data["cities"].items()), reverse=True)
    print(f"{sum(s for s, _ in sizes)} garages in {len(sizes)} cities -> {OUT.name}")
    print(", ".join(f"{k.split('|')[1]} {n}" for n, k in sizes))
    print(f"{len(data['city_levels'])} cities with a city-wide measured level")
