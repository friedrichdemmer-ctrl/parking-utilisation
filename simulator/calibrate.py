"""Set a city's demand from measured occupancy, and test how well that transfers.

The original set one number by hand for Dusseldorf (base_hourly_arrivals = 950 on 15,468
spaces, i.e. 0.0614 arrivals per space per hour, summed over segments). For a city with
measured garages the number is fitted instead: demand is scaled until the simulated mean
weekday 06-21 occupancy of the garages we measure equals what we measured, and the
overnight share is set to the measured 02-05 level (the simulator otherwise starts empty).

Only the LEVEL is fitted. How well the simulator then reproduces what it was not told --
which garages are busy (spatial pattern) and when (daily profile) -- is reported as
validation, and for cities without measurements a transferred factor is used, tested by
leaving each measured city out and predicting it from the others.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from .city import CityModel
from .engine import run_scenario
from .models import ScenarioOverlay, SimulationConfig

BASE_PER_SPACE = 950 / 15468        # the original's demand per space
SEEDS = (11, 22, 33)
MIN_LINKED = 3                       # measured garages needed to fit a city on its own
FACTOR_RANGE = (0.15, 8.0)
TARGETS_PATH = Path(__file__).resolve().parent / "calibration_targets.json"


def load_targets() -> dict:
    return json.loads(TARGETS_PATH.read_text()) if TARGETS_PATH.exists() else {"cities": {}, "city_levels": {}}


def config_for(model: CityModel, factor: float, floor: float, seed: int, day_type: str = "weekday") -> SimulationConfig:
    total = sum(g.capacity for g in model.garages)
    return SimulationConfig(day_type=day_type, random_seed=seed, contract_floor=floor,
                            base_hourly_arrivals=max(1, round(BASE_PER_SPACE * total * factor)))


def simulate(model: CityModel, factor: float, floor: float, overlay: ScenarioOverlay | None = None, seeds=SEEDS):
    """One run per seed; returns the list of results."""
    overlay = overlay or ScenarioOverlay(name="baseline")
    return [run_scenario(model.garages, config_for(model, factor, floor, s), overlay) for s in seeds]


def _measured(model: CityModel, targets: dict) -> dict:
    return {gid: t for gid, t in targets.items() if gid in {g.id for g in model.garages}}


def _linked_mean(results, measured: dict, weights: dict) -> float:
    """Capacity-weighted mean simulated occupancy (%) over the measured garages, averaged across seeds."""
    vals = []
    for r in results:
        by = {s["garage_id"]: s for s in r["garage_summary"]}
        num = sum(by[g]["avg_occupancy_pct"] * weights[g] for g in measured)
        vals.append(num / sum(weights[g] for g in measured))
    return statistics.mean(vals)


def measured_level(measured: dict, weights: dict) -> float:
    num = sum(statistics.mean(t["hours"]) * weights[g] for g, t in measured.items())
    return num / sum(weights[g] for g in measured)


def fit_factor(model: CityModel, floor: float, target: float, measure, iterations: int = 11):
    """Bisect (in log space) on the demand factor until measure(results) == target.
    measure maps a list of per-seed results to a mean occupancy in %. Returns
    (factor, simulated level, reached target)."""
    level = lambda f: measure(simulate(model, f, floor))
    lo, hi = FACTOR_RANGE
    if level(hi) < target:
        return hi, level(hi), False
    if level(lo) > target:
        return lo, level(lo), False
    for _ in range(iterations):
        mid = (lo * hi) ** 0.5
        if level(mid) < target:
            lo = mid
        else:
            hi = mid
    f = (lo * hi) ** 0.5
    return f, level(f), True


def citywide_level(results) -> float:
    return statistics.mean(r["kpis"]["avg_occupancy_pct"] for r in results)


def calibration_spec(model: CityModel, key: str, targets: dict, fallback_floor: float):
    """What to fit this city to, best evidence first:
      garage  - 3+ garages the competitive set lists that we also measure: the simulated
                occupancy of exactly those garages is matched to what we measured there;
      city    - 3+ measured garages in the city (not necessarily the listed ones): the
                simulated city-wide level is matched to the measured city-wide level;
      None    - nothing measured: the transferred factor is used.
    Returns (mode, target %, measure function, overnight share, measured-garages dict)."""
    measured = _measured(model, targets["cities"].get(key, {}))
    if len(measured) >= MIN_LINKED:
        weights = {g.id: g.capacity for g in model.garages}
        return ("garage", measured_level(measured, weights), lambda res: _linked_mean(res, measured, weights),
                city_floor(measured, fallback_floor), measured)
    cl = targets.get("city_levels", {}).get(key)
    if cl:
        return "city", cl["level"], citywide_level, round(min(0.6, cl["night"] / 100), 3), measured
    return None, None, None, fallback_floor, measured


def pearson(a, b):
    if len(a) < 3:
        return None
    ma, mb = statistics.mean(a), statistics.mean(b)
    sa = sum((x - ma) ** 2 for x in a) ** 0.5
    sb = sum((y - mb) ** 2 for y in b) ** 0.5
    if not sa or not sb:
        return None
    return round(sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb), 3)


def validate(model: CityModel, measured: dict, factor: float, floor: float) -> dict:
    """How well a run at `factor` reproduces what it was not fitted to."""
    results = simulate(model, factor, floor)
    weights = {g.id: g.capacity for g in model.garages}
    ids = list(measured)
    sim_garage = {g: statistics.mean(
        next(s for s in r["garage_summary"] if s["garage_id"] == g)["avg_occupancy_pct"] for r in results) for g in ids}
    meas_garage = {g: statistics.mean(measured[g]["hours"]) for g in ids}
    sim_hours = [statistics.mean(
        sum(next(s for s in r["garage_summary"] if s["garage_id"] == g)["hourly_occupancy_pct"][i] * weights[g] for g in ids)
        / sum(weights[g] for g in ids) for r in results) for i in range(16)]
    meas_hours = [sum(measured[g]["hours"][i] * weights[g] for g in ids) / sum(weights[g] for g in ids) for i in range(16)]
    errs = [abs(sim_garage[g] - meas_garage[g]) for g in ids]
    return {
        "linked": len(ids),
        "measured_level": round(sum(meas_garage[g] * weights[g] for g in ids) / sum(weights[g] for g in ids), 1),
        "simulated_level": round(sum(sim_garage[g] * weights[g] for g in ids) / sum(weights[g] for g in ids), 1),
        "garage_r": pearson([sim_garage[g] for g in ids], [meas_garage[g] for g in ids]),
        "garage_mae_pts": round(statistics.mean(errs), 1),
        "profile_r": pearson(sim_hours, meas_hours),
        "sim_hours": [round(v, 1) for v in sim_hours],
        "measured_hours": [round(v, 1) for v in meas_hours],
    }


def global_floor(targets: dict) -> float:
    nights = [t["night"] for city in targets["cities"].values() for t in city.values()]
    nights += [c["night"] for c in targets.get("city_levels", {}).values()]
    return round(min(0.6, statistics.median(nights) / 100), 3) if nights else 0.0


def city_floor(measured: dict, fallback: float) -> float:
    if len(measured) < MIN_LINKED:
        return fallback
    return round(min(0.6, statistics.median(t["night"] for t in measured.values()) / 100), 3)
