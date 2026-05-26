import logging
from abc import ABC, abstractmethod
from typing import List

from elevator.core.constants import SIMULATION_LOGGER_NAME
from elevator.core.models import Elevator, Passenger

logger = logging.getLogger(SIMULATION_LOGGER_NAME)


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
        chosen = min(candidates, key=lambda e: len(e.passengers))
        logger.info(
            "All elevators full — fallback assigned %r to E%d (least loaded, %d passengers)",
            passenger.id, chosen.id, len(chosen.passengers),
        )
        return chosen.id
