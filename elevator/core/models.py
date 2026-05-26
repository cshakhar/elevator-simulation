from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set

from elevator.core.constants import DEFAULT_START_FLOOR, STOP_DROPOFF, STOP_PICKUP


class Direction(Enum):
    UP = "UP"
    DOWN = "DOWN"
    IDLE = "IDLE"


@dataclass
class Passenger:
    id: str
    request_time: int
    source: int
    dest: int
    assigned_elevator: Optional[int] = None
    pickup_time: Optional[int] = None
    dropoff_time: Optional[int] = None
    request_id: Optional[str] = None  # trace token linking all log lines for this passenger

    @property
    def travel_direction(self) -> Direction:
        return Direction.UP if self.dest > self.source else Direction.DOWN

    @property
    def wait_time(self) -> Optional[int]:
        if self.pickup_time is not None:
            return self.pickup_time - self.request_time
        return None

    @property
    def travel_time(self) -> Optional[int]:
        if self.dropoff_time is not None and self.pickup_time is not None:
            return self.dropoff_time - self.pickup_time
        return None

    @property
    def total_time(self) -> Optional[int]:
        if self.dropoff_time is not None:
            return self.dropoff_time - self.request_time
        return None

    @property
    def is_served(self) -> bool:
        return self.dropoff_time is not None

    @property
    def is_waiting(self) -> bool:
        return self.pickup_time is None

    @property
    def is_riding(self) -> bool:
        return self.pickup_time is not None and self.dropoff_time is None


class Elevator:
    def __init__(
        self,
        elevator_id: int,
        num_floors: int,
        capacity: int,
        express_floors: Optional[Set[int]] = None,
        start_floor: int = DEFAULT_START_FLOOR,
    ):
        self.id = elevator_id
        self.current_floor = start_floor
        self.direction = Direction.IDLE
        self.capacity = capacity
        self.num_floors = num_floors
        self.passengers: List[str] = []
        # floor -> {"pickup": [passenger_ids], "dropoff": [passenger_ids]}
        self.stops: Dict[int, Dict[str, List[str]]] = {}
        self.express_floors = express_floors  # None means all floors served

    @property
    def is_full(self) -> bool:
        return len(self.passengers) >= self.capacity

    @property
    def available_capacity(self) -> int:
        return self.capacity - len(self.passengers)

    @property
    def has_stops(self) -> bool:
        return bool(self.stops)

    @property
    def highest_stop(self) -> Optional[int]:
        return max(self.stops) if self.stops else None

    @property
    def lowest_stop(self) -> Optional[int]:
        return min(self.stops) if self.stops else None

    def serves_floor(self, floor: int) -> bool:
        return self.express_floors is None or floor in self.express_floors

    def add_pickup(self, floor: int, passenger_id: str) -> None:
        if floor not in self.stops:
            self.stops[floor] = {STOP_PICKUP: [], STOP_DROPOFF: []}
        if passenger_id not in self.stops[floor][STOP_PICKUP]:
            self.stops[floor][STOP_PICKUP].append(passenger_id)

    def add_dropoff(self, floor: int, passenger_id: str) -> None:
        if floor not in self.stops:
            self.stops[floor] = {STOP_PICKUP: [], STOP_DROPOFF: []}
        if passenger_id not in self.stops[floor][STOP_DROPOFF]:
            self.stops[floor][STOP_DROPOFF].append(passenger_id)

    def remove_stop_if_empty(self, floor: int) -> None:
        if floor in self.stops:
            s = self.stops[floor]
            if not s[STOP_PICKUP] and not s[STOP_DROPOFF]:
                del self.stops[floor]

    def get_next_stop(self) -> Optional[int]:
        """SCAN/LOOK: return the next floor to move toward."""
        if not self.stops:
            return None

        if self.direction == Direction.UP:
            above = [f for f in self.stops if f > self.current_floor]
            if above:
                return min(above)
            below = [f for f in self.stops if f < self.current_floor]
            if below:
                return max(below)
            # Only remaining stop is the current floor (e.g. leftover pickups after
            # capacity was exceeded); serve it rather than spinning indefinitely.
            if self.current_floor in self.stops:
                return self.current_floor

        elif self.direction == Direction.DOWN:
            below = [f for f in self.stops if f < self.current_floor]
            if below:
                return max(below)
            above = [f for f in self.stops if f > self.current_floor]
            if above:
                return min(above)
            # Same edge case as UP branch above.
            if self.current_floor in self.stops:
                return self.current_floor

        else:  # IDLE: go to nearest stop, preferring other floors over the current one
            # The current floor was just processed this tick; remaining stops there
            # (e.g. pickups left over from a full elevator) should not trap the elevator.
            other = [f for f in self.stops if f != self.current_floor]
            candidates = other if other else list(self.stops)
            return min(candidates, key=lambda f: abs(f - self.current_floor))

        return None

    def update_direction(self) -> None:
        next_stop = self.get_next_stop()
        if next_stop is None:
            self.direction = Direction.IDLE
        elif next_stop > self.current_floor:
            self.direction = Direction.UP
        elif next_stop < self.current_floor:
            self.direction = Direction.DOWN
        else:
            # Already at the stop floor; stay idle until it's processed
            self.direction = Direction.IDLE

    def move(self) -> None:
        self.update_direction()
        if self.direction == Direction.UP:
            self.current_floor += 1
        elif self.direction == Direction.DOWN:
            self.current_floor -= 1

    def estimate_pickup_time(self, source: int) -> int:
        """Estimate ticks to reach source floor, accounting for direction and turnaround."""
        if self.direction == Direction.IDLE:
            return abs(self.current_floor - source)

        if self.direction == Direction.UP:
            if source >= self.current_floor:
                return source - self.current_floor
            # Must continue up to highest stop, then reverse down to source
            highest = self.highest_stop or self.current_floor
            return (highest - self.current_floor) + (highest - source)

        else:  # DOWN
            if source <= self.current_floor:
                return self.current_floor - source
            # Must continue down to lowest stop, then reverse up to source
            lowest = self.lowest_stop or self.current_floor
            return (self.current_floor - lowest) + (source - lowest)

    def reset(self) -> None:
        self.current_floor = DEFAULT_START_FLOOR
        self.direction = Direction.IDLE
        self.passengers.clear()
        self.stops.clear()
