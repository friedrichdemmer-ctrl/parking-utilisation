"""Base interface every source adapter implements.

An adapter is scoped to one *source* (a city portal or an operator's site),
not necessarily one city -- some sources cover many. Each adapter declares
its own polling cadence and which fetcher it needs, and returns plain dicts
that storage.py writes into the existing lots_meta / historical_observations
schema. Adapters should not touch sqlite directly -- keeps them testable and
keeps the storage/validation logic (and its lessons learned) in one place.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CapacityRecord:
    place_id: str
    place_name: str
    city_name: str
    num_all: int
    source_id: str
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    place_url: str | None = None
    source_web_url: str | None = None


@dataclass
class OccupancyRecord:
    place_id: str
    ts: str  # ISO 8601, UTC, e.g. "2026-08-13T12:34:56+00:00"
    free: int


class SourceAdapter(ABC):
    #: unique slug, used as source_id in lots_meta and for health tracking
    name: str

    #: "http" for plain HTTP/JSON/HTML sources, "browser" for JS-rendered sites
    fetcher_type: str = "http"

    #: how often fetch_occupancy() should run
    occupancy_interval_seconds: int = 1800

    #: how often fetch_capacity() should run (capacity rarely changes)
    capacity_interval_seconds: int = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        """Return current capacity/metadata for every garage this source covers.

        Default: no-op. Override only if the source publishes capacity itself;
        if capacity is already known (e.g. via capacity_overrides/), an
        occupancy-only adapter can skip this entirely.
        """
        return []

    @abstractmethod
    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        """Return the current free-space reading for every garage this source covers.

        known_garages maps a normalized name (see util.normalize_name) to the
        place_id already on file for this source_id in lots_meta, so adapters
        that match against existing archive entries (rather than discovering
        new ones) don't need their own DB connection.
        """
        raise NotImplementedError
