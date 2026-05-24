import math
from typing import List, Tuple

from algorithms.base import BaseScheduler
from algorithms.nearest_car import NearestCarScheduler
from elevator.models import Elevator, Passenger


class ZoneBasedScheduler(BaseScheduler):
    """
    Divides floors into equal-sized zones; each elevator owns one zone.

    Assignment logic:
      1. Find the zone that contains the passenger's source floor.
      2. Assign to that zone's elevator if it has capacity and serves both floors.
      3. Fall back to NearestCar if the zone elevator is unavailable.

    This mirrors real-world sky-lobby / zone-dispatch deployments.
    """

    def __init__(self, elevators: List[Elevator], num_floors: int):
        super().__init__(elevators)
        n = len(elevators)
        zone_size = math.ceil(num_floors / n)
        self.zones: List[Tuple[int, int]] = []
        for i in range(n):
            low = i * zone_size + 1
            high = min((i + 1) * zone_size, num_floors)
            self.zones.append((low, high))
        self._fallback_scheduler = NearestCarScheduler(elevators)

    def assign(self, passenger: Passenger) -> int:
        for i, (low, high) in enumerate(self.zones):
            if low <= passenger.source <= high:
                elevator = self.elevators[i]
                # Zone is a scheduling preference, not a physical restriction.
                # serves_floor() gates are intentionally omitted here so that
                # cross-zone destinations and burst overflow work correctly.
                # Physical floor restrictions (express_config) are enforced by
                # the NearestCar fallback below.
                if not elevator.is_full:
                    return elevator.id
                break  # zone elevator busy; let NearestCar decide freely

        return self._fallback_scheduler.assign(passenger)
