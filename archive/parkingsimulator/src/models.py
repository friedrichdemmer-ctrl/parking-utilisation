from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TariffRule:
    hourly_rate: float
    daily_cap: Optional[float] = None
    member_discount_pct: float = 0.0


@dataclass
class Garage:
    id: str
    name: str
    operator: str
    lat: float
    lon: float
    capacity: int
    zone: str
    tariff: TariffRule
    has_app: bool = False
    has_anpr: bool = False
    has_ev: bool = False
    quality_score: float = 0.5
    occupied: int = 0

    def available(self) -> int:
        return max(0, self.capacity - self.occupied)

    def occupancy_ratio(self) -> float:
        return self.occupied / self.capacity if self.capacity else 0.0


@dataclass
class DemandSegment:
    name: str
    price_elasticity: float
    mean_dwell_hours: float
    quality_weight: float
    ev_affinity: float = 0.0
    hourly_profile: dict = field(default_factory=dict)


@dataclass
class Session:
    garage_id: str
    zone: str
    operator: str
    segment: str
    hour: int
    duration_hours: float
    price_paid: float


@dataclass
class ScenarioOverlay:
    name: str
    price_multiplier: float = 1.0
    zone_price_multiplier: dict = field(default_factory=dict)
    price_cap_by_zone: dict = field(default_factory=dict)
    capacity_multiplier_by_zone: dict = field(default_factory=dict)
    segment_demand_multiplier: dict = field(default_factory=dict)


@dataclass
class SimulationConfig:
    start_hour: int = 6
    end_hour: int = 22
    day_type: str = "weekday"
    random_seed: int = 42
    base_hourly_arrivals: int = 950
    search_radius_km: float = 2.5
