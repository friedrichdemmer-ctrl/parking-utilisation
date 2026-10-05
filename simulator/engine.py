"""Simulation orchestrator: one weekday, hour by hour, for a list of garages.

The original's run_scenario(), unchanged in what it computes, but taking garages
rather than a CSV path so any city's garages can be passed in (city.py builds them).
"""

import copy
import csv
import random

from .allocation import Allocator
from .demand import generate_hourly_arrivals
from .models import Garage, TariffRule


def garages_from_assets_csv(csv_path):
    """The original Dusseldorf asset file, with its hand-set zones, quality scores
    and app/ANPR flags. Kept so check_parity.py can reproduce the archived results."""
    garages = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            tariff = TariffRule(
                hourly_rate=float(row["hourly_rate"]),
                daily_cap=float(row["daily_cap"]) if row["daily_cap"] else None,
                member_discount_pct=float(row["member_discount_pct"]),
            )
            garages.append(Garage(
                id=row["id"], name=row["name"], operator=row["operator"],
                lat=float(row["lat"]), lon=float(row["lon"]), capacity=int(row["capacity"]),
                zone=row["zone"], tariff=tariff,
                has_app=row["has_app"] == "True", has_anpr=row["has_anpr"] == "True",
                has_ev=row["has_ev"] == "True", quality_score=float(row["quality_score"]),
            ))
    return garages


def _apply_capacity_overlay(garages, overlay):
    for g in garages:
        mult = overlay.capacity_multiplier_by_zone.get(g.zone, 1.0)
        g.capacity = max(0, round(g.capacity * mult))


def run_scenario(garages, config, overlay):
    garages = copy.deepcopy(garages)      # a run mutates occupancy and capacity
    _apply_capacity_overlay(garages, overlay)
    for g in garages:
        g.occupied = round(config.contract_floor * g.capacity)
    rng = random.Random(config.random_seed)
    allocator = Allocator(garages, config, overlay, rng)

    garage_occ_history = {g.id: [] for g in garages}

    hourly_rows = []
    for hour in range(config.start_hour, config.end_hour):
        allocator.free_departures(hour)
        cells = [c for c in generate_hourly_arrivals(config, overlay, rng) if c[1] == hour]
        for segment, h, count in cells:
            origin_lat, origin_lon = _segment_origin(segment.name, garages, rng)
            allocator.process_cell(segment, h, count, origin_lat, origin_lon)

        for g in garages:
            garage_occ_history[g.id].append(g.occupancy_ratio())

        occupied_total = sum(g.occupied for g in garages)
        capacity_total = sum(g.capacity for g in garages)
        hourly_rows.append({
            "hour": hour,
            "occupied": occupied_total,
            "capacity": capacity_total,
            "occupancy_pct": round(100 * occupied_total / capacity_total, 2) if capacity_total else 0,
            "arrivals": sum(c[2] for c in cells),
        })

    total_capacity = sum(g.capacity for g in garages)
    avg_occupancy_pct = round(sum(r["occupancy_pct"] for r in hourly_rows) / len(hourly_rows), 2) if hourly_rows else 0
    revenue = round(sum(s.price_paid for s in allocator.sessions), 2)

    zone_breakdown = {}
    for s in allocator.sessions:
        z = zone_breakdown.setdefault(s.zone, {"revenue": 0.0, "sessions": 0})
        z["revenue"] += s.price_paid
        z["sessions"] += 1
    for z in zone_breakdown.values():
        z["revenue"] = round(z["revenue"], 2)

    sessions_by_garage = {}
    revenue_by_garage = {}
    for s in allocator.sessions:
        sessions_by_garage[s.garage_id] = sessions_by_garage.get(s.garage_id, 0) + 1
        revenue_by_garage[s.garage_id] = revenue_by_garage.get(s.garage_id, 0.0) + s.price_paid

    garage_summary = []
    for g in garages:
        hist = garage_occ_history[g.id]
        avg_occ = round(100 * sum(hist) / len(hist), 2) if hist else 0.0
        garage_summary.append({
            "hourly_occupancy_pct": [round(100 * v, 2) for v in hist],
            "garage_id": g.id, "name": g.name, "operator": g.operator, "zone": g.zone,
            "capacity": g.capacity, "sessions": sessions_by_garage.get(g.id, 0),
            "revenue": round(revenue_by_garage.get(g.id, 0.0), 2), "avg_occupancy_pct": avg_occ,
        })

    kpis = {
        "scenario": overlay.name,
        "revenue": revenue,
        "sessions": len(allocator.sessions),
        "abandoned": allocator.abandoned,
        "avg_occupancy_pct": avg_occupancy_pct,
        "total_capacity": total_capacity,
        "revenue_per_space": round(revenue / total_capacity, 2) if total_capacity else 0,
        "garages": len(garages),
    }
    return {"kpis": kpis, "hourly": hourly_rows, "zone_breakdown": zone_breakdown,
            "sessions": allocator.sessions, "garage_summary": garage_summary}


def _segment_origin(segment_name, garages, rng: random.Random):
    """Approximate a demand origin point, biased toward the zone the segment favours."""
    zone_bias = {
        "commuter": ["cbd_east_station", "cbd_core"],
        "retail": ["cbd_core"],
        "leisure": ["cbd_core", "cbd_east_station"],
        "resident": ["neighbourhood", "fringe"],
        "station_traveller": ["cbd_east_station"],
        "ev_driver": ["cbd_core", "cbd_east_station", "neighbourhood"],
        "event": ["cbd_core", "cbd_east_station"],
        "hotel": ["cbd_core", "cbd_east_station"],
    }
    preferred = zone_bias.get(segment_name, [])
    pool = [g for g in garages if g.zone in preferred] or garages
    anchor = rng.choice(pool)
    jitter_lat = anchor.lat + rng.uniform(-0.01, 0.01)
    jitter_lon = anchor.lon + rng.uniform(-0.01, 0.01)
    return jitter_lat, jitter_lon
