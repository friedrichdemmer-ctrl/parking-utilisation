"""Regression test: the ported engine must reproduce the archived Dusseldorf results exactly.

    python3 -m simulator.check_parity

Runs the four archived scenarios on the archived asset file and compares revenue,
sessions, abandoned and occupancy with archive/parkingsimulator/outputs/summary.json.
Any difference means the port changed the model, not just its plumbing.
"""

import json
import sys
from pathlib import Path

from .engine import garages_from_assets_csv, run_scenario
from .models import ScenarioOverlay, SimulationConfig

ARCHIVE = Path(__file__).resolve().parent.parent / "archive" / "parkingsimulator"


def scenarios():
    return [
        ScenarioOverlay(name="baseline"),
        ScenarioOverlay(name="price_up_20", price_multiplier=1.2),
        ScenarioOverlay(name="regulation_shock", price_cap_by_zone={"cbd_core": 3.0},
                        segment_demand_multiplier={"ev_driver": 1.8, "commuter": 0.9}),
        ScenarioOverlay(name="capacity_shock_cbd", capacity_multiplier_by_zone={"cbd_core": 0.7}),
    ]


def main():
    expected = {s["scenario"]: s for s in json.loads((ARCHIVE / "outputs" / "summary.json").read_text())["scenarios"]}
    garages = garages_from_assets_csv(ARCHIVE / "data" / "assets.csv")
    config = SimulationConfig(day_type="weekday")
    bad = 0
    for overlay in scenarios():
        got = run_scenario(garages, config, overlay)["kpis"]
        want = expected[overlay.name]
        diffs = {k: (got[k], want[k]) for k in ("revenue", "sessions", "abandoned", "avg_occupancy_pct", "total_capacity")
                 if got[k] != want[k]}
        print(f"  {overlay.name:<20} revenue {got['revenue']:>10,.2f}  sessions {got['sessions']:>6}  "
              f"{'OK' if not diffs else 'DIFFERS ' + str(diffs)}")
        bad += bool(diffs)
    print("parity:", "PASS" if not bad else f"FAIL ({bad} scenarios differ)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
