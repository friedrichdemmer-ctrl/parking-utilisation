import random
from .geo import garages_within_radius
from .choice import utilities_for_segment, choose_garage
from .models import Session


class Allocator:
    def __init__(self, garages, config, overlay, rng: random.Random):
        self.garages = garages
        self.by_id = {g.id: g for g in garages}
        self.config = config
        self.overlay = overlay
        self.rng = rng
        self.sessions = []
        self.abandoned = 0
        self._departures = {}  # end_hour -> list of garage_ids
        self._price_cache = {}  # (garage id, segment) -> price; fixed for the length of a run

    def free_departures(self, hour):
        for garage_id in self._departures.pop(hour, []):
            g = self.by_id[garage_id]
            g.occupied = max(0, g.occupied - 1)

    def process_cell(self, segment, hour, count, origin_lat, origin_lon):
        candidates = garages_within_radius(origin_lat, origin_lon, self.garages, self.config.search_radius_km)
        for _ in range(count):
            scored = utilities_for_segment(segment, hour, origin_lat, origin_lon, candidates, self.overlay, self._price_cache)
            choice = choose_garage(scored, self.rng)
            if choice is None:
                self.abandoned += 1
                continue
            garage, price, _u = choice
            garage.occupied += 1
            duration = max(0.5, self.rng.gauss(segment.mean_dwell_hours, segment.mean_dwell_hours * 0.25))
            end_hour = hour + max(1, round(duration))
            self._departures.setdefault(end_hour, []).append(garage.id)
            self.sessions.append(Session(
                garage_id=garage.id,
                zone=garage.zone,
                operator=garage.operator,
                segment=segment.name,
                hour=hour,
                duration_hours=round(duration, 2),
                price_paid=price,
            ))
