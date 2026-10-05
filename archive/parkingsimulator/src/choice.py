import math
import random
from .geo import haversine_km
from .tariffs import scenario_hourly_rate, effective_price

DISTANCE_DECAY = 1.8
CAPACITY_PENALTY_EXP = 3.0
DIGITAL_BONUS = 0.15
EV_BONUS = 1.2
NETWORK_BONUS = 0.1


def utilities_for_segment(segment, hour, origin_lat, origin_lon, candidates, overlay):
    """candidates: list of (garage, distance_km). Returns list of (garage, price, utility)."""
    scored = []
    for garage, dist_km in candidates:
        if garage.available() <= 0:
            continue
        hourly_rate = scenario_hourly_rate(garage, overlay)
        price = effective_price(hourly_rate, garage.tariff.daily_cap, segment.mean_dwell_hours)

        u = 0.0
        u += -DISTANCE_DECAY * dist_km
        u += segment.price_elasticity * price
        u += segment.quality_weight * garage.quality_score
        if garage.has_app or garage.has_anpr:
            u += DIGITAL_BONUS
        if segment.ev_affinity and garage.has_ev:
            u += EV_BONUS * segment.ev_affinity
        u += NETWORK_BONUS if garage.operator == "Q-Park" else 0.0
        occ_ratio = garage.occupancy_ratio()
        u -= CAPACITY_PENALTY_EXP * (occ_ratio ** 4)

        scored.append((garage, price, u))
    return scored


def choose_garage(scored, rng: random.Random):
    """Softmax choice over (garage, price, utility) tuples. Returns chosen tuple or None."""
    if not scored:
        return None
    max_u = max(u for _, _, u in scored)
    weights = [math.exp(u - max_u) for _, _, u in scored]
    total = sum(weights)
    if total <= 0:
        return None
    r = rng.random() * total
    acc = 0.0
    for item, w in zip(scored, weights):
        acc += w
        if r <= acc:
            return item
    return scored[-1]
