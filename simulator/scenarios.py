"""Scenarios that make sense in any city.

The original four were written for Dusseldorf (a EUR 3.00 cap on its core, which is
about its median tariff). Here the cap is the city's own median rate, so "core price cap"
means the same thing everywhere.
"""

import statistics

from .models import ScenarioOverlay


def scenarios_for(model) -> list[ScenarioOverlay]:
    median_rate = round(statistics.median(g.tariff.hourly_rate for g in model.garages), 2)
    return [
        ScenarioOverlay(name="baseline"),
        ScenarioOverlay(name="price_down_20", price_multiplier=0.8),
        ScenarioOverlay(name="price_up_20", price_multiplier=1.2),
        ScenarioOverlay(name="price_up_50", price_multiplier=1.5),
        ScenarioOverlay(name="core_price_cap", price_cap_by_zone={"cbd_core": median_rate}),
        ScenarioOverlay(name="capacity_shock_core", capacity_multiplier_by_zone={"cbd_core": 0.7}),
        ScenarioOverlay(name="ev_surge", segment_demand_multiplier={"ev_driver": 1.8, "commuter": 0.9}),
    ]


LABELS = {
    "baseline": "Today's prices and capacity",
    "price_down_20": "All tariffs 20% lower",
    "price_up_20": "All tariffs 20% higher",
    "price_up_50": "All tariffs 50% higher",
    "core_price_cap": "Core tariffs capped at the city median",
    "capacity_shock_core": "30% of core spaces closed",
    "ev_surge": "EV drivers +80%, commuters -10%",
}
