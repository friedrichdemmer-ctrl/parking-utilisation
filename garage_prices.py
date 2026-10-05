"""Posted tariffs for the garages we also have occupancy for.

Prices come from the sibling project parkingsimulator
(github.com/friedrichdemmer-ctrl/parkingsimulator), which collects operator
tariffs city by city: 3,839 garages in 7 countries, 3,123 of them with both
a price and coordinates.

garage_prices/*.csv holds the matched pairs: a priced garage is matched to
one of ours when they are within 250 m, their names agree once operator and
"Parkhaus"/"car park" wording is stripped (the closer they are, the less
name agreement is required), and their capacities are within 40% where both
are known. Each side is used at most once, best pair first -- without that,
a 2,340-space centre and the 66-space hotel deck beside it swap places. 687
matched, 155 of them still reporting. Rows are reviewed before they are added.

Revenue here is deliberately crude: occupancy x capacity x the posted hourly
rate, which is gross takings if every occupied space paid the hourly tariff.
Real takings are lower -- day tickets, season parkers, residents, shopper
validation and staff bays all pay less -- so treat it as an upper bound for
comparing garages, not as a forecast. See revenue_week().
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

PRICES_DIR = Path(__file__).resolve().parent / "garage_prices"
SOURCE = "parkingsimulator (operator tariff pages)"


@lru_cache(maxsize=1)
def prices() -> dict[str, dict]:
    """{place_id: {hourly_rate, daily_cap, operator, country, source_url, ...}}"""
    out: dict[str, dict] = {}
    for path in sorted(PRICES_DIR.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rate = (row.get("hourly_rate") or "").strip()
                cap = (row.get("daily_cap") or "").strip()
                if not rate and not cap:
                    continue
                free = (row.get("free") or "").strip() == "yes"
                transit = (row.get("transit_conditional") or "").strip() == "yes"
                out[row["place_id"]] = {
                    "hourly_rate": float(rate) if rate else None,
                    "daily_cap": float(cap) if cap else None,
                    "operator": (row.get("operator") or "").strip() or None,
                    "country": (row.get("country") or "").strip() or None,
                    "source_url": (row.get("source_url") or "").strip() or None,
                    "matched_name": (row.get("priced_name") or "").strip() or None,
                    "match_distance_m": int(row["dist_m"]) if (row.get("dist_m") or "").strip().isdigit() else None,
                    "currency": (row.get("currency") or "").strip() or None,
                    "free": free,
                    "transit_conditional": transit,
                    "note": (row.get("note") or "").strip() or None,
                }
    return out


def modelled_revenue(profile, capacity: int, price: dict | None, name: str | None) -> dict | None:
    """revenue_model.estimate() for a garage: day tickets, contract parkers
    and a stay mix by type, rather than billing every hour at the hourly rate."""
    from garage_types import classify
    from revenue_model import estimate

    if not price or price.get("transit_conditional"):
        return None            # a transit authority sets this fee, not the operator
    if price.get("free"):
        return {"total": 0, "low": 0, "high": 0, "per_space": 0, "per_space_year": 0,
                "contract": 0, "visitor": 0, "free": True}
    return estimate(profile, capacity, price["hourly_rate"], price["daily_cap"], classify(name))


def revenue_week(profile: list[float | None], capacity: int, hourly_rate: float | None) -> float | None:
    """Gross takings over a typical week at the posted hourly rate, from a
    168-hour occupancy profile in percent (utilisation_report.py). None when
    there is no rate or no profile. An upper bound -- see the module docstring."""
    if not hourly_rate or not capacity or not profile:
        return None
    hours = [v for v in profile if v is not None]
    if not hours:
        return None
    # scale up if part of the week is missing, so a patchy profile is not
    # reported as a quieter garage
    occupied_space_hours = sum(hours) / 100 * capacity * (168 / len(hours))
    return round(occupied_space_hours * hourly_rate)
