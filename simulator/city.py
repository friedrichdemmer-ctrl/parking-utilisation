"""Build the simulator's inputs for any city of the competitive set.

The original model was fed a hand-made Dusseldorf file: coordinates, capacity and
tariff per garage (researched) plus a zone, a quality score and app/ANPR flags
(judged by hand). The first three exist for every city in competitive/; the last
three have to be derived, and where capacity or tariff is missing it has to be
imputed. Everything derived or imputed is recorded in `assumptions` and flagged
per garage, so a result can always be traced to what was measured and what was not.

Derivation rules (all deliberately simple; the Dusseldorf file they were fitted
against is compared in check_parity.py's second test):

  zone      distance from the city centre (median of garage coordinates):
              cbd_core <= 0.8 km, neighbourhood <= 2.2 km, fringe beyond;
              a station garage within 2.0 km is cbd_east_station.
  quality   falls with distance from the centre: 0.9 - 0.2 x km, bounded 0.4-0.9
            (Dusseldorf's hand-set scores were 0.86 core, 0.75 station, 0.57
            neighbourhood, 0.48 fringe).
  digital   garages of an operator with 3 or more garages in the dataset get
            has_app (the chains all have one; independents mostly do not).
  EV        as researched where recorded, otherwise absent.
  missing capacity / price / day ticket: the city median, else the country
            median, else a fixed default.
Prices are converted to EUR at fixed rates so the choice model's price terms mean
the same everywhere.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field

import competitive
from garage_types import classify

from .geo import haversine_km
from .models import Garage, TariffRule

TO_EUR = {"EUR": 1.0, "GBP": 1.17, "DKK": 0.134}
MIN_GARAGES = 5          # below this a "market" is too thin to simulate
MIN_KNOWN = 3            # garages with a recorded capacity / tariff needed to trust the imputation
CORE_KM, NEIGHBOURHOOD_KM, STATION_KM = 0.8, 2.2, 2.0
DEFAULT_CAPACITY, DEFAULT_RATE, DEFAULT_CAP_HOURS = 250, 2.5, 7.0
CHAIN_MIN_GARAGES = 3


@dataclass
class CityModel:
    country: str
    city: str
    garages: list[Garage]
    centre: tuple[float, float]
    place_ids: dict[str, str]                 # garage id -> our place_id, where we measure it
    imputed: dict[str, list[str]]             # garage id -> fields filled in
    assumptions: dict = field(default_factory=dict)


def _median(values, default=None):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else default


def _chain_operators() -> set[str]:
    counts = Counter(g["operator"] for gs in competitive.garages().values() for g in gs)
    return {op for op, n in counts.items() if n >= CHAIN_MIN_GARAGES and op}


def _country_medians(country: str) -> dict:
    gs = [g for (c, _), v in competitive.garages().items() if c == country for g in v]
    to = lambda g, k: g[k] * TO_EUR.get(g["currency"], 1.0) if g[k] is not None else None
    rates = [to(g, "hourly_rate") for g in gs]
    ratios = [g["daily_cap"] / g["hourly_rate"] for g in gs if g["daily_cap"] and g["hourly_rate"]]
    return {"capacity": _median(g["capacity"] for g in gs), "rate": _median(rates),
            "cap_hours": _median(ratios)}


def simulatable(country: str, city: str) -> str | None:
    """None if the city can be simulated, else the reason it cannot."""
    gs = competitive.garages().get((country, city), [])
    if len(gs) < MIN_GARAGES:
        return f"only {len(gs)} garages"
    if sum(1 for g in gs if g["capacity"]) < MIN_KNOWN:
        return "fewer than 3 garages with a recorded capacity"
    if sum(1 for g in gs if g["hourly_rate"]) < MIN_KNOWN:
        return "fewer than 3 garages with a recorded tariff"
    return None


def centre_of(gs) -> tuple[float, float]:
    return statistics.median(g["lat"] for g in gs), statistics.median(g["lon"] for g in gs)


def zone_for(dist_km: float, is_station: bool) -> str:
    if is_station and dist_km <= STATION_KM:
        return "cbd_east_station"
    if dist_km <= CORE_KM:
        return "cbd_core"
    if dist_km <= NEIGHBOURHOOD_KM:
        return "neighbourhood"
    return "fringe"


def quality_for(dist_km: float) -> float:
    return round(min(0.9, max(0.4, 0.9 - 0.2 * dist_km)), 2)


def build_city(country: str, city: str) -> CityModel:
    gs = competitive.garages()[(country, city)]
    cc = _country_medians(country)
    chains = _chain_operators()
    fx = TO_EUR.get(gs[0]["currency"], 1.0)

    cap_city = _median(g["capacity"] for g in gs)
    rate_city = _median(g["hourly_rate"] * fx for g in gs if g["hourly_rate"])
    ratio_city = _median(g["daily_cap"] / g["hourly_rate"] for g in gs if g["daily_cap"] and g["hourly_rate"])
    cap_fill = cap_city or cc["capacity"] or DEFAULT_CAPACITY
    rate_fill = rate_city or cc["rate"] or DEFAULT_RATE
    ratio_fill = ratio_city or cc["cap_hours"] or DEFAULT_CAP_HOURS

    clat, clon = centre_of(gs)
    place_of = {gid: v["place_id"] for (c, ci, gid), v in competitive.links().items() if (c, ci) == (country, city)}
    garages, imputed = [], {}
    for g in gs:
        miss = []
        capacity = g["capacity"]
        if not capacity:
            capacity, _ = round(cap_fill), miss.append("capacity")
        if g["hourly_rate"]:
            rate = g["hourly_rate"] * fx
            cap = g["daily_cap"] * fx if g["daily_cap"] else round(rate * ratio_fill, 2)
            if not g["daily_cap"]:
                miss.append("daily_cap")
        else:
            rate = rate_fill
            cap = g["daily_cap"] * fx if g["daily_cap"] else round(rate * ratio_fill, 2)
            miss.append("tariff")
        dist = haversine_km(clat, clon, g["lat"], g["lon"])
        garages.append(Garage(
            id=g["id"], name=g["name"], operator=g["operator"] or "Independent",
            lat=g["lat"], lon=g["lon"], capacity=int(capacity),
            zone=zone_for(dist, classify(g["name"]) == "station"),
            tariff=TariffRule(hourly_rate=round(rate, 2), daily_cap=round(cap, 2)),
            has_app=g["operator"] in chains, has_anpr=False, has_ev=g["has_ev"],
            quality_score=quality_for(dist)))
        if miss:
            imputed[g["id"]] = miss

    n = len(gs)
    return CityModel(
        country=country, city=city, garages=garages, centre=(clat, clon),
        place_ids={gid: pid for gid, pid in place_of.items()}, imputed=imputed,
        assumptions={
            "garages": n,
            "capacity_imputed": sum(1 for m in imputed.values() if "capacity" in m),
            "tariff_imputed": sum(1 for m in imputed.values() if "tariff" in m),
            "day_ticket_imputed": sum(1 for m in imputed.values() if "daily_cap" in m),
            "fill_capacity": round(cap_fill), "fill_rate_eur": round(rate_fill, 2),
            "currency": gs[0]["currency"], "to_eur": fx,
            "zones": dict(Counter(g.zone for g in garages)),
        })
