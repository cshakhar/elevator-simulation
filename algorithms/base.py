from abc import ABC, abstractmethod
from typing import List

from elevator.models import Elevator, Passenger


class BaseScheduler(ABC):
    def __init__(self, elevators: List[Elevator]):
        self.elevators = elevators

    @abstractmethod
    def assign(self, passenger: Passenger) -> int:
        """Assign a passenger to an elevator; return the elevator's ID."""

    def _fallback(self, passenger: Passenger) -> int:
        """Last-resort assignment: pick the least loaded eligible elevator."""
        if not self.elevators:
            raise RuntimeError(
                f"Cannot assign passenger {passenger.id!r}: no elevators are configured."
            )
        eligible = [
            e for e in self.elevators
            if e.serves_floor(passenger.source) and e.serves_floor(passenger.dest)
        ]
        candidates = eligible or self.elevators
        return min(candidates, key=lambda e: len(e.passengers)).id
