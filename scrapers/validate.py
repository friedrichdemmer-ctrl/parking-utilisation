"""Sanity checks before anything gets written. We've already hit two real data
quality problems this session (APCOA showing 330 vs 472 for the same garage;
some feeds report free > capacity) -- validate rather than trust blindly.
"""

from __future__ import annotations

from scrapers.base import CapacityRecord, OccupancyRecord

MAX_PLAUSIBLE_CAPACITY = 5000  # generous upper bound; flags obvious garbage, not real large garages
FREE_OVERSHOOT_TOLERANCE = 1.1  # allow up to 10% over capacity (rounding, transient miscounts)


def validate_capacity(rec: CapacityRecord) -> str | None:
    """Return None if valid, else a reason string."""
    if rec.num_all is None or rec.num_all <= 0:
        return f"non-positive capacity ({rec.num_all})"
    if rec.num_all > MAX_PLAUSIBLE_CAPACITY:
        return f"implausibly large capacity ({rec.num_all})"
    if not rec.place_id or not rec.city_name:
        return "missing place_id or city_name"
    return None


def validate_occupancy(rec: OccupancyRecord, known_capacity: int | None) -> str | None:
    """Return None if valid, else a reason string."""
    if rec.free < 0:
        return f"negative free count ({rec.free})"
    if known_capacity and rec.free > known_capacity * FREE_OVERSHOOT_TOLERANCE:
        return f"free ({rec.free}) exceeds capacity ({known_capacity}) by more than {FREE_OVERSHOOT_TOLERANCE}x"
    return None


def filter_valid(occupancy: list[OccupancyRecord], capacities: dict[str, int]) -> tuple[list[OccupancyRecord], list[tuple[OccupancyRecord, str]]]:
    """Split into (valid, [(record, reason), ...]) for rejected ones."""
    valid, rejected = [], []
    for rec in occupancy:
        reason = validate_occupancy(rec, capacities.get(rec.place_id))
        if reason:
            rejected.append((rec, reason))
        else:
            valid.append(rec)
    return valid, rejected
