import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import SimulationConfig, ScenarioOverlay
from src.simulation import run_scenario, load_garages

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data", "assets.csv")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")


def build_scenarios():
    baseline = ScenarioOverlay(name="baseline")

    price_up = ScenarioOverlay(name="price_up_20", price_multiplier=1.2)

    regulation_shock = ScenarioOverlay(
        name="regulation_shock",
        price_cap_by_zone={"cbd_core": 3.0},
        segment_demand_multiplier={"ev_driver": 1.8, "commuter": 0.9},
    )

    capacity_shock_cbd = ScenarioOverlay(
        name="capacity_shock_cbd",
        capacity_multiplier_by_zone={"cbd_core": 0.7},
    )

    return [baseline, price_up, regulation_shock, capacity_shock_cbd]


def print_kpis(kpis):
    print(
        f"  {kpis['scenario']:<20} "
        f"revenue=EUR{kpis['revenue']:>10,.0f}  "
        f"occupancy={kpis['avg_occupancy_pct']:>5.1f}%  "
        f"sessions={kpis['sessions']:>6}  "
        f"abandoned={kpis['abandoned']:>5}"
    )


def main():
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    garages = load_garages(DATA_PATH)
    total_capacity = sum(g.capacity for g in garages)
    print(f"Loading {len(garages)} garages, {total_capacity:,} spaces")

    config = SimulationConfig(day_type="weekday")
    scenarios = build_scenarios()
    print(f"Running {len(scenarios)} scenarios ({', '.join(s.name for s in scenarios)})\n")

    results = []
    for overlay in scenarios:
        result = run_scenario(DATA_PATH, config, overlay)
        results.append(result)
        print_kpis(result["kpis"])

    # kpi_comparison.csv
    kpi_path = os.path.join(OUTPUTS_DIR, "kpi_comparison.csv")
    with open(kpi_path, "w", newline="") as f:
        fields = list(results[0]["kpis"].keys())
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow(r["kpis"])

    # timeseries_<scenario>.csv
    for r in results:
        ts_path = os.path.join(OUTPUTS_DIR, f"timeseries_{r['kpis']['scenario']}.csv")
        with open(ts_path, "w", newline="") as f:
            fields = list(r["hourly"][0].keys())
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for row in r["hourly"]:
                w.writerow(row)

    # garage_kpis_<scenario>.csv
    for r in results:
        gk_path = os.path.join(OUTPUTS_DIR, f"garage_kpis_{r['kpis']['scenario']}.csv")
        with open(gk_path, "w", newline="") as f:
            fields = list(r["garage_summary"][0].keys())
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for row in r["garage_summary"]:
                w.writerow(row)

    # summary.json
    summary = {
        "garages": len(garages),
        "total_capacity": total_capacity,
        "day_type": config.day_type,
        "scenarios": [r["kpis"] for r in results],
        "zone_breakdown": {r["kpis"]["scenario"]: r["zone_breakdown"] for r in results},
    }
    with open(os.path.join(OUTPUTS_DIR, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nExported results to {OUTPUTS_DIR}/")
    print("  - kpi_comparison.csv")
    for r in results:
        print(f"  - timeseries_{r['kpis']['scenario']}.csv")
    for r in results:
        print(f"  - garage_kpis_{r['kpis']['scenario']}.csv")
    print("  - summary.json")


if __name__ == "__main__":
    main()
