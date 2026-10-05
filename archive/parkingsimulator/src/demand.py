import random
from .models import DemandSegment

# Hourly arrival-share profiles (weights across hours 6..21, need not sum to 1)
_COMMUTER = {6: 0.10, 7: 0.22, 8: 0.20, 9: 0.08, 10: 0.03, 11: 0.02, 12: 0.02,
             13: 0.02, 14: 0.02, 15: 0.03, 16: 0.05, 17: 0.10, 18: 0.07, 19: 0.02, 20: 0.01, 21: 0.01}
_RETAIL = {6: 0.01, 7: 0.02, 8: 0.03, 9: 0.06, 10: 0.09, 11: 0.11, 12: 0.12,
           13: 0.12, 14: 0.11, 15: 0.10, 16: 0.08, 17: 0.06, 18: 0.05, 19: 0.03, 20: 0.01, 21: 0.00}
_LEISURE = {6: 0.00, 7: 0.00, 8: 0.01, 9: 0.02, 10: 0.04, 11: 0.06, 12: 0.08,
            13: 0.08, 14: 0.08, 15: 0.09, 16: 0.10, 17: 0.10, 18: 0.11, 19: 0.10, 20: 0.08, 21: 0.05}
_RESIDENT = {h: 1 / 16 for h in range(6, 22)}
_STATION = {6: 0.09, 7: 0.14, 8: 0.13, 9: 0.08, 10: 0.06, 11: 0.05, 12: 0.05,
            13: 0.05, 14: 0.05, 15: 0.06, 16: 0.06, 17: 0.09, 18: 0.09, 19: 0.06, 20: 0.03, 21: 0.02}
_EV = {6: 0.03, 7: 0.06, 8: 0.08, 9: 0.07, 10: 0.06, 11: 0.06, 12: 0.06,
       13: 0.06, 14: 0.06, 15: 0.07, 16: 0.08, 17: 0.09, 18: 0.08, 19: 0.05, 20: 0.03, 21: 0.02}
_EVENT = {6: 0.00, 7: 0.00, 8: 0.00, 9: 0.00, 10: 0.00, 11: 0.00, 12: 0.02,
          13: 0.02, 14: 0.03, 15: 0.04, 16: 0.05, 17: 0.10, 18: 0.20, 19: 0.30, 20: 0.20, 21: 0.04}
_HOTEL = {h: 1 / 16 for h in range(6, 22)}

SEGMENTS = [
    DemandSegment("commuter", price_elasticity=-0.10, mean_dwell_hours=9.0, quality_weight=0.4, hourly_profile=_COMMUTER),
    DemandSegment("retail", price_elasticity=-0.45, mean_dwell_hours=1.5, quality_weight=0.7, hourly_profile=_RETAIL),
    DemandSegment("leisure", price_elasticity=-0.50, mean_dwell_hours=3.0, quality_weight=0.6, hourly_profile=_LEISURE),
    DemandSegment("resident", price_elasticity=-0.15, mean_dwell_hours=14.0, quality_weight=0.3, hourly_profile=_RESIDENT),
    DemandSegment("station_traveller", price_elasticity=-0.20, mean_dwell_hours=6.0, quality_weight=0.5, hourly_profile=_STATION),
    DemandSegment("ev_driver", price_elasticity=-0.25, mean_dwell_hours=4.0, quality_weight=0.5, ev_affinity=1.0, hourly_profile=_EV),
    DemandSegment("event", price_elasticity=-0.30, mean_dwell_hours=3.5, quality_weight=0.6, hourly_profile=_EVENT),
    DemandSegment("hotel", price_elasticity=-0.12, mean_dwell_hours=16.0, quality_weight=0.6, hourly_profile=_HOTEL),
]

# Base daily share of total demand contributed by each segment
_SEGMENT_SHARE = {
    "commuter": 0.28, "retail": 0.20, "leisure": 0.15, "resident": 0.10,
    "station_traveller": 0.12, "ev_driver": 0.06, "event": 0.05, "hotel": 0.04,
}

_WEEKEND_SEGMENT_MULT = {
    "commuter": 0.35, "retail": 1.15, "leisure": 1.4, "resident": 1.0,
    "station_traveller": 0.7, "ev_driver": 0.9, "event": 1.6, "hotel": 1.1,
}


def generate_hourly_arrivals(config, overlay, rng: random.Random):
    """Yields (segment, hour, arrival_count) for the configured time window."""
    day_mult = 1.0 if config.day_type == "weekday" else None
    cells = []
    for segment in SEGMENTS:
        share = _SEGMENT_SHARE[segment.name]
        if config.day_type != "weekday":
            share *= _WEEKEND_SEGMENT_MULT[segment.name]
        share *= overlay.segment_demand_multiplier.get(segment.name, 1.0)
        daily_total = config.base_hourly_arrivals * (config.end_hour - config.start_hour) * share
        profile_total = sum(
            w for h, w in segment.hourly_profile.items() if config.start_hour <= h < config.end_hour
        ) or 1.0
        for hour in range(config.start_hour, config.end_hour):
            weight = segment.hourly_profile.get(hour, 0.0)
            if weight <= 0:
                continue
            expected = daily_total * (weight / profile_total)
            count = _poisson(expected, rng)
            if count > 0:
                cells.append((segment, hour, count))
    return cells


def _poisson(lam, rng: random.Random):
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, round(rng.gauss(lam, lam ** 0.5)))
    l = pow(2.718281828, -lam)
    k, p = 0, 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= l:
            return k - 1
