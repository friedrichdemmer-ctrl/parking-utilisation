"""Run every simulatable city and write one result file each.

    python3 -m simulator.run_all [--only Country|City ...] [--jobs 4]

Per city: fit (or transfer) the demand factor, run every scenario over several seeds,
and write simulator/results/<country>_<city>.json plus results/index.json and
results/validation.json (leave-one-city-out test of the transferred factor).
Deterministic: fixed seeds, so a rerun reproduces the files unless the data changed.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from multiprocessing import Pool
from pathlib import Path

import competitive

from . import calibrate as C
from .city import build_city, simulatable
from .scenarios import LABELS, scenarios_for

from .store import RESULTS, slug

SEEDS = (11, 22, 33, 44, 55)


def _mean_sd(values):
    return statistics.mean(values), (statistics.stdev(values) if len(values) > 1 else 0.0)


def run_city(args):
    country, city, factor_in, floor_in = args
    model = build_city(country, city)
    key = f"{country}|{city}"
    mode, target, measure, floor, measured = C.calibration_spec(model, key, C.load_targets(), floor_in)
    factor = factor_in
    calibration = {"method": "transferred", "linked": len(measured)}
    if mode:
        factor, level, reached = C.fit_factor(model, floor, target, measure)
        calibration = {"method": f"fitted-{mode}", "linked": len(measured), "reached_target": reached,
                       "measured_level": round(target, 1), "simulated_level": round(level, 1)}
        if mode == "garage":
            calibration["validation"] = C.validate(model, measured, factor, floor)
    calibration.update({"factor": round(factor, 3), "contract_floor": floor})

    garages = {g.id: g for g in model.garages}
    runs, base_by_garage, base_hours = {}, {}, None
    for overlay in scenarios_for(model):
        results = C.simulate(model, factor, floor, overlay, SEEDS)
        k = {key: [r["kpis"][key] for r in results] for key in ("revenue", "sessions", "avg_occupancy_pct", "total_capacity")}
        rev, rev_sd = _mean_sd(k["revenue"])
        runs[overlay.name] = {
            "label": LABELS[overlay.name],
            "revenue": round(rev), "revenue_sd": round(rev_sd),
            "sessions": round(statistics.mean(k["sessions"])),
            "occupancy_pct": round(statistics.mean(k["avg_occupancy_pct"]), 1),
            "capacity": round(statistics.mean(k["total_capacity"])),
            "revenue_per_space": round(rev / statistics.mean(k["total_capacity"]), 2),
            "zones": {z: round(statistics.mean(r["zone_breakdown"].get(z, {"revenue": 0})["revenue"] for r in results))
                      for z in ("cbd_core", "cbd_east_station", "neighbourhood", "fringe")},
        }
        if overlay.name == "baseline":
            base_hours = [round(statistics.mean(r["hourly"][i]["occupancy_pct"] for r in results), 1)
                          for i in range(len(results[0]["hourly"]))]
            for g in model.garages:
                rows = [next(s for s in r["garage_summary"] if s["garage_id"] == g.id) for r in results]
                base_by_garage[g.id] = {"occupancy_pct": round(statistics.mean(x["avg_occupancy_pct"] for x in rows), 1),
                                        "revenue": round(statistics.mean(x["revenue"] for x in rows)),
                                        "sessions": round(statistics.mean(x["sessions"] for x in rows))}
    base = runs["baseline"]
    for name, r in runs.items():
        r["revenue_change_pct"] = round(100 * (r["revenue"] / base["revenue"] - 1), 1) if base["revenue"] else None
        r["sessions_change_pct"] = round(100 * (r["sessions"] / base["sessions"] - 1), 1) if base["sessions"] else None
        r["significant"] = abs(r["revenue"] - base["revenue"]) > 2 * (r["revenue_sd"] ** 2 + base["revenue_sd"] ** 2) ** 0.5

    out = {
        "country": country, "city": city, "seeds": len(SEEDS), "calibration": calibration,
        "assumptions": model.assumptions, "centre": model.centre, "scenarios": runs, "baseline_hourly": base_hours,
        "garages": [{"id": g.id, "name": g.name, "operator": g.operator, "zone": g.zone, "capacity": g.capacity,
                     "hourly_rate_eur": g.tariff.hourly_rate, "quality": g.quality_score,
                     "imputed": model.imputed.get(g.id, []), "measured": g.id in measured,
                     **base_by_garage[g.id]} for g in model.garages],
    }
    (RESULTS / f"{slug(country, city)}.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    return out


def transfer_parameters(fitted: dict) -> tuple[float, float]:
    """The demand factor and overnight share applied to cities with no measurements."""
    factors = [v["calibration"]["factor"] for v in fitted.values() if v["calibration"].get("reached_target")]
    floors = [v["calibration"]["contract_floor"] for v in fitted.values() if v["calibration"].get("reached_target")]
    return round(statistics.median(factors), 3), round(statistics.median(floors), 3)


def leave_one_out(fitted: dict) -> list[dict]:
    """Predict each fitted city from the median factor and overnight share of all the others,
    and compare with predicting the median measured level of the others (the naive benchmark)."""
    rows, targets = [], C.load_targets()
    for key, v in fitted.items():
        others = {k: o for k, o in fitted.items() if k != key and o["calibration"].get("reached_target")}
        if len(others) < 3 or not v["calibration"].get("reached_target"):
            continue
        factor, floor = transfer_parameters(others)
        country, city = key.split("|")
        model = build_city(country, city)
        mode, target, measure, _, measured = C.calibration_spec(model, key, targets, floor)
        simulated = measure(C.simulate(model, factor, floor))
        naive = statistics.median(o["calibration"]["measured_level"] for o in others.values())
        row = {"city": city, "country": country, "mode": mode, "measured_level": round(target, 1),
               "simulated_level": round(simulated, 1), "level_error_pts": round(simulated - target, 1),
               "naive_level_error_pts": round(naive - target, 1), "factor": factor, "fitted_factor": v["calibration"]["factor"]}
        if mode == "garage":
            val = C.validate(model, measured, factor, floor)
            row.update({k: val[k] for k in ("linked", "garage_r", "garage_mae_pts", "profile_r")})
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="Country|City keys")
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    RESULTS.mkdir(exist_ok=True)
    t0 = time.time()

    targets = C.load_targets()
    cities = [(c, ci) for (c, ci) in sorted(competitive.garages()) if not simulatable(c, ci)]
    skipped = {f"{c}|{ci}": simulatable(c, ci) for (c, ci) in competitive.garages() if simulatable(c, ci)}
    gfloor = C.global_floor(targets)
    measured_keys = [f"{c}|{ci}" for (c, ci) in cities
                     if C.calibration_spec(build_city(c, ci), f"{c}|{ci}", targets, gfloor)[0]]

    # 1. fit the measured cities first, then derive the transfer parameters
    fit_args = [(*k.split("|"), 1.0, gfloor) for k in measured_keys if not args.only or k in args.only]
    with Pool(args.jobs) as pool:
        fitted_list = pool.map(run_city, fit_args)
    fitted = {f"{o['country']}|{o['city']}": o for o in fitted_list}
    factor, floor = transfer_parameters(fitted) if fitted else (1.0, gfloor)
    print(f"fitted {len(fitted)} cities in {time.time() - t0:.0f}s; transfer factor {factor}, overnight share {floor}")

    # 2. everything else with the transferred parameters
    rest = [(c, ci, factor, floor) for (c, ci) in cities if f"{c}|{ci}" not in fitted and (not args.only or f"{c}|{ci}" in args.only)]
    with Pool(args.jobs) as pool:
        done = pool.map(run_city, rest, chunksize=1)
    print(f"transferred {len(done)} cities, total {time.time() - t0:.0f}s")

    index = [{"country": o["country"], "city": o["city"], "garages": o["assumptions"]["garages"],
              "method": o["calibration"]["method"], "linked": o["calibration"]["linked"],
              "capacity": o["scenarios"]["baseline"]["capacity"], "occupancy_pct": o["scenarios"]["baseline"]["occupancy_pct"],
              "file": slug(o["country"], o["city"])} for o in fitted_list + done]
    meta = {"transfer_factor": factor, "transfer_floor": floor, "seeds": list(SEEDS),
            "cities": sorted(index, key=lambda r: (r["country"], r["city"])), "skipped": skipped}
    (RESULTS / "index.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")))
    if len(fitted) >= 4:
        loo = leave_one_out(fitted)
        (RESULTS / "validation.json").write_text(json.dumps(loo, ensure_ascii=False, indent=1))
        print("leave-one-out:", len(loo), "cities; median |level error| model",
              round(statistics.median(abs(r["level_error_pts"]) for r in loo), 1), "pts, naive",
              round(statistics.median(abs(r["naive_level_error_pts"]) for r in loo), 1), "pts")


if __name__ == "__main__":
    main()
