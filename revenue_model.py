"""Estimated takings for a garage, allowing for day tickets and contract parkers.

garage_prices.revenue_week() bills every occupied space-hour at the posted
hourly rate. That is an upper bound: a commuter who stays nine hours pays the
day ticket, not nine hours; the cars sitting in the garage at 4 a.m. are
contract or resident parkers paying a monthly rate. Where a day ticket is
cheap relative to the hourly rate (Aachen Tivoli: EUR 1.00/h with a EUR 5.00
day ticket) the difference is several-fold.

This model splits the measured occupancy into the three things that are
actually billed differently:

1. Contract parkers -- the overnight floor (mean occupancy 02:00-05:00, from
   our own 168-hour profile). These spaces are let monthly; with no monthly
   price in the tariff data it is taken as MONTHLY_MULTIPLE x the day ticket,
   spread over the days of the month. Where even the day ticket is missing it
   is taken as IMPLIED_CAP_HOURS hours at the hourly rate.
2. Visitors -- space-hours above that floor, split into stay lengths by what
   the garage serves (garage_types.py). The mixes below are the model's main
   assumption: shares of arrivals, not of space-hours (a nine-hour commuter
   occupies six times the space-hours of a 90-minute shopper, so they are
   converted before use).
3. Leakage -- shopper validation, free first half-hour, staff and permit
   bays, evenings free, unpaid stays. One flat share, LEAKAGE.

Each visitor stay pays min(hours x hourly rate, day ticket), which is where
the day ticket does its work.

The output is a scenario, not a measurement: the occupancy is real, the stay
mix is assumed. Two garages modelled the same way compare fairly; a single
figure should be read as "of this order", which is why estimate() also
returns the low and high variants (SPREAD) and the assumptions it used.

Known bias: the only contract parkers the model can see are those still
there at 4 a.m. Season tickets and residents' permits used through the
working day are billed hourly here, so garages with a high hourly tariff
read high -- across the 104 priced garages with a typical week the median
comes out at about EUR 3,900 per space a year, which is the right order for
a European city-centre garage, but the dearest central Amsterdam sites
model several times that.
"""

from __future__ import annotations

NIGHT_HOURS = range(2, 5)       # contract/resident floor, as in utilisation_report
DAYS_PER_MONTH = 30.4
MONTHLY_MULTIPLE = 12.0         # monthly season ticket ~ 12 day tickets
LEAKAGE = 0.12                  # share of visitor takings never collected
IMPLIED_CAP_HOURS = 5.5         # day ticket, where none is published, as hours at the hourly rate
SPREAD = 0.25                   # low/high variants: mean stay +/- this share

# by garage type (garage_types.classify): (share of arrivals, stay hours)
MIXES: dict[str, list[tuple[float, float]]] = {
    "shopping":   [(.70, 1.5), (.25, 3.0), (.05, 8.0)],
    "city":       [(.45, 1.5), (.35, 3.5), (.20, 9.0)],
    "station":    [(.25, 1.5), (.25, 4.0), (.50, 10.0)],
    "hospital":   [(.40, 1.5), (.45, 3.0), (.15, 8.0)],
    "event":      [(.20, 1.5), (.65, 3.5), (.15, 8.0)],
    "park_ride":  [(.10, 1.5), (.15, 4.0), (.75, 10.0)],
    "university": [(.20, 1.5), (.30, 4.0), (.50, 9.0)],
    "airport":    [(.05, 2.0), (.15, 8.0), (.80, 30.0)],
}
DEFAULT_MIX = MIXES["city"]


def _visitor_take(space_hours: float, mix: list[tuple[float, float]], hourly: float, cap: float | None) -> tuple[float, float]:
    """(takings, mean stay hours) for visitor space-hours under one stay mix."""
    mean_stay = sum(share * hours for share, hours in mix)
    arrivals = space_hours / mean_stay
    take = sum(arrivals * share * min(hours * hourly, cap if cap else float("inf")) for share, hours in mix)
    return take, mean_stay


def estimate(profile: list[float | None], capacity: int, hourly_rate: float | None,
             daily_cap: float | None, garage_type: str = "city") -> dict | None:
    """Weekly takings from a 168-hour occupancy profile in percent.

    Returns the total and its parts, the assumptions used, and a low/high
    range from varying the mean stay by SPREAD. None without a profile, a
    capacity or any price.
    """
    if not capacity or not profile or not (hourly_rate or daily_cap):
        return None
    hours = [(h, v) for h, v in enumerate(profile) if v is not None]
    if len(hours) < 24:
        return None
    if daily_cap is None and hourly_rate:
        daily_cap = round(hourly_rate * IMPLIED_CAP_HOURS, 2)   # see IMPLIED_CAP_HOURS
        implied_cap = True
    else:
        implied_cap = False
    nights = [v for h, v in hours if h % 24 in NIGHT_HOURS]
    floor = min(nights) / 100 if nights else 0.0   # the quietest night hour, so a
    # garage that never empties is not credited with contract parkers it lacks
    scale = 168 / len(hours)                       # scale up a partly-covered week
    visitor_space_hours = sum(max(0.0, v / 100 - floor) for _, v in hours) * capacity * scale
    contract_spaces = floor * capacity

    contract = contract_spaces * MONTHLY_MULTIPLE * (daily_cap or 0) / DAYS_PER_MONTH * 7
    mix = MIXES.get(garage_type, DEFAULT_MIX)
    if hourly_rate:
        visitor, mean_stay = _visitor_take(visitor_space_hours, mix, hourly_rate, daily_cap)
        variants = []
        for factor in (1 - SPREAD, 1 + SPREAD):
            stretched = [(share, hrs * factor) for share, hrs in mix]
            variants.append(_visitor_take(visitor_space_hours, stretched, hourly_rate, daily_cap)[0])
    elif daily_cap:                                 # day ticket only: one ticket per stay
        _, mean_stay = _visitor_take(visitor_space_hours, mix, 0, None)
        visitor = visitor_space_hours / mean_stay * daily_cap
        variants = [visitor / (1 + SPREAD), visitor / (1 - SPREAD)]
    else:
        return None
    net = lambda v: v * (1 - LEAKAGE)
    total = contract + net(visitor)
    return {
        "total": round(total),
        "low": round(contract + net(min(variants))),
        "high": round(contract + net(max(variants))),
        "per_space": round(total / capacity, 2),
        "per_space_year": round(total / capacity * 52),
        "contract": round(contract),
        "visitor": round(net(visitor)),
        "contract_spaces": round(contract_spaces),
        "visitor_space_hours": round(visitor_space_hours),
        "mean_stay_h": round(mean_stay, 1),
        "stays_per_week": round(visitor_space_hours / mean_stay),
        "type": garage_type,
        "daily_cap_implied": implied_cap,
        "assumptions": {"monthly_multiple": MONTHLY_MULTIPLE, "leakage": LEAKAGE, "daily_cap": daily_cap,
                        "mix": [{"hours": h, "share": s} for s, h in mix]},
    }
